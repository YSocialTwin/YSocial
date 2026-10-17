#!/usr/bin/env python3
"""English baseline for gate G0: how often does a model answer in a way the client parsers accept?

It renders the microblogging prompts that decide an action (action choice, follow, reaction, vote)
exactly as ``YClient/y_client/classes/base_agent.py`` does, sends them to an OpenAI-compatible
chat endpoint, and applies the same token tests as the client (uppercase, ``!`` removed, split on
whitespace). Only the standard library is needed.

    python scripts/prompts/baseline_parse.py --endpoint http://127.0.0.1:11434/v1 --model llama3.1 \
        --n 50 --seed 1 --out docs/baseline_llama3.1.json
    python scripts/prompts/baseline_parse.py --simulate        # no network, checks the script itself

Results (JSON) feed docs/prompt-baseline.md. Gate G0 asks for at least 95% parsing success on both models.
"""

import argparse
import json
import random
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "data_schema" / "prompts.json"

POSTS = [
    "The city council approved the new bike lanes today, finally some good news for commuters.",
    "I can't believe the price of groceries this month. Something has to change.",
    "Just finished reading a great paper on network science, highly recommend it!",
    "Politicians keep promising and never delivering. Tired of it.",
    "Our team won the regional championship last night, what a game!",
    "New study suggests remote work increases productivity in small teams.",
    "Does anyone know a good recipe for gluten free bread?",
    "The election results are in and the margin is razor thin.",
    "Climate policy needs bold action, not more committees.",
    "Taxes should be lower for small businesses, period.",
]
ACTIONS = ["COMMENT", "POST", "READ", "SEARCH", "FOLLOW", "SHARE", "NONE"]
SYSTEM = "You are role-playing a social media user. Act as requested."
SYSTEM_HANDLER = "You are the Handler that specify the actions to be taken."


def clean(text, upper=False):
    text = (text or "").replace("!", "")
    return text.upper() if upper else text


def parse_action(answer):
    words = clean(answer, upper=True).split()
    return next((a for a in ACTIONS if a in words), None)


def parse_follow(answer):
    words = clean(answer).split()
    return "YES" if "YES" in words else ("NO" if "NO" in words else None)


def parse_reaction(answer):
    words = clean(answer).split()
    for token in ("YES", "NO", "NEUTRAL"):
        if token in words:
            return token
    return None


def parse_vote(answer):
    words = clean(answer, upper=True).split()
    return next((t for t in ("RIGHT", "LEFT", "NONE") if t in words), None)


def cases(prompts, rng, n):
    for _ in range(n):
        post = rng.choice(POSTS)
        acts = ACTIONS[:]
        rng.shuffle(acts)
        yield "action", prompts["handler_action"].format(actions=",".join(acts)), parse_action
        yield "follow", prompts["handler_follow"].format(action="following", post_text=post), parse_follow
        yield "reaction", prompts["handler_reactions"].format(post_text=post), parse_reaction
        yield "vote", prompts["handler_cast"].format(post_text=post), parse_vote


def ask(endpoint, model, user, timeout):
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM + " " + SYSTEM_HANDLER},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
            "max_tokens": 64,
        }
    ).encode()
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer none"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    usage = data.get("usage") or {}
    return (
        data["choices"][0]["message"]["content"] or "",
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        time.time() - t0,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint")
    ap.add_argument("--model")
    ap.add_argument("--n", type=int, default=50, help="rounds; each round asks four questions")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--prompts", default=str(PROMPTS))
    ap.add_argument("--out")
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args()
    if not args.simulate and not (args.endpoint and args.model):
        ap.error("--endpoint and --model are required (or use --simulate)")

    prompts = json.loads(Path(args.prompts).read_text(encoding="utf-8"))
    rng = random.Random(args.seed)
    stats = {}
    errors = 0
    for kind, user, parser in cases(prompts, rng, args.n):
        row = stats.setdefault(kind, {"ok": 0, "bad": 0, "empty": 0, "ptok": [], "ctok": [], "secs": []})
        try:
            if args.simulate:
                answer = {"action": "comment!", "follow": "YES", "reaction": "NEUTRAL", "vote": "none"}[kind]
                ptok = ctok = secs = None
            else:
                answer, ptok, ctok, secs = ask(args.endpoint, args.model, user, args.timeout)
        except Exception as exc:  # network or server problem: not a parsing failure
            errors += 1
            print(f"request failed: {exc}", file=sys.stderr)
            continue
        if not answer.strip():
            row["empty"] += 1
        row["ok" if parser(answer) else "bad"] += 1
        for key, val in (("ptok", ptok), ("ctok", ctok), ("secs", secs)):
            if val is not None:
                row[key].append(val)

    total_ok = sum(r["ok"] for r in stats.values())
    total = sum(r["ok"] + r["bad"] for r in stats.values())
    report = {
        "model": args.model or "simulated",
        "seed": args.seed,
        "rounds": args.n,
        "request_errors": errors,
        "parsing_success": round(total_ok / total, 4) if total else None,
        "by_prompt": {
            k: {
                "ok": r["ok"],
                "bad": r["bad"],
                "empty": r["empty"],
                "success": round(r["ok"] / (r["ok"] + r["bad"]), 4) if r["ok"] + r["bad"] else None,
                "mean_prompt_tokens": round(statistics.mean(r["ptok"]), 1) if r["ptok"] else None,
                "mean_completion_tokens": round(statistics.mean(r["ctok"]), 1) if r["ctok"] else None,
                "mean_seconds": round(statistics.mean(r["secs"]), 2) if r["secs"] else None,
            }
            for k, r in stats.items()
        },
    }
    text = json.dumps(report, indent=1)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
