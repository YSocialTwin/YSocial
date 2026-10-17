#!/usr/bin/env python3
"""Pilot of the multilingual prompts: does a model follow the protocol and write in the right language?

For every model x language x seed the script builds ``--agents`` synthetic agents and, for each of ``--days``
days, sends them the decision prompts the clients send (action, reaction, follow, vote, post, comment), rendered
from the language packs exactly as a client does (closed-list renderer, profile values in the prompt language).
Replies are stored as JSON lines; ``analyze`` turns them into per-language metrics and writes
``docs/prompt-pilot-report.md``.

  python scripts/prompts/pilot.py run --models llama3 qwen2 --base-url http://localhost:11434/v1 \
      --languages en it --agents 50 --days 3 --seeds 1 2 3 --out pilot_runs
  python scripts/prompts/pilot.py run --simulate --models fake --out /tmp/pilot      # no LLM, for a dry run
  python scripts/prompts/pilot.py analyze --out pilot_runs --report docs/prompt-pilot-report.md

Nothing here changes a pack or a simulation: it only reads the packs and calls the model you point it at.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKS = ROOT / "data_schema" / "prompts"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ps = _load("pilot_prompt_store", ROOT / "y_web" / "prompt_store.py")
tokens = _load("pilot_protocol_tokens", ROOT / "external" / "YClient" / "y_client" / "protocol_tokens.py")

# --- what the agents are shown (same meaning in every language, written once per language) ------------------------
STIMULI = {
    "en": [
        "Public transport in our city is getting more expensive and less reliable every year.",
        "I just finished a long hike in the mountains and the view was incredible.",
        "The new tax proposal will hurt small businesses more than big companies.",
        "Does anyone else think remote work is making teams less creative?",
        "Our local football team finally won after ten matches without a victory!",
        "Schools should spend more time teaching students how to spot fake news.",
    ],
    "it": [
        "I trasporti pubblici della nostra città diventano ogni anno più cari e meno affidabili.",
        "Ho appena finito una lunga camminata in montagna e il panorama era incredibile.",
        "La nuova proposta fiscale danneggerà le piccole imprese più delle grandi aziende.",
        "Qualcun altro pensa che il lavoro da remoto renda i team meno creativi?",
        "La nostra squadra di calcio ha finalmente vinto dopo dieci partite senza una vittoria!",
        "Le scuole dovrebbero dedicare più tempo a insegnare agli studenti a riconoscere le notizie false.",
    ],
}
STOPWORDS = {
    "en": {"the", "and", "is", "are", "to", "of", "in", "that", "it", "for", "with", "this", "but", "not", "you", "have", "just", "our", "more"},
    "it": {"il", "lo", "la", "le", "gli", "di", "che", "e", "è", "un", "una", "per", "con", "non", "in", "del", "della", "sono", "ma", "più", "mi", "ho"},
}
TASKS = {  # task -> (prompt key, allowed protocol tokens or None for free text)
    "action": ("handler_action", tokens.ACTIONS),
    "reaction": ("handler_reactions", ("YES", "NO", "NEUTRAL")),
    "follow": ("handler_follow", tokens.YES_NO),
    "vote": ("handler_cast", tokens.VOTES),
    "post": ("handler_post", None),
    "comment": ("handler_comment", None),
}
NAMES = ["Alex", "Maria", "John", "Giulia", "Sam", "Elena", "Pablo", "Chiara", "Omar", "Sofia", "Luca", "Nina"]


def pack(language, name):
    """A prompt file of ``language``, English filling what it lacks (as ``prompt_packs.load_pack`` does)."""

    def merge(base, over):
        if isinstance(base, dict):
            over = over if isinstance(over, dict) else {}
            return {k: merge(v, over.get(k)) for k, v in base.items()}
        return over if isinstance(over, type(base)) and over not in (None, "") else base

    english = json.loads((PACKS / "en" / name).read_text(encoding="utf-8"))
    path = PACKS / language / name
    if language == "en" or not path.exists():
        return english
    return merge(english, json.loads(path.read_text(encoding="utf-8")))


class Agent:
    def __init__(self, rng, values, language):
        pick = lambda cat: rng.choice(sorted(values[cat])) if values.get(cat) else ""
        self.name = rng.choice(NAMES)
        self.age = rng.randint(18, 70)
        self.gender, self.nationality, self.profession = pick("gender"), pick("nationality"), pick("profession")
        self.leaning, self.education_level, self.toxicity = pick("leaning"), pick("education_level"), pick("toxicity")
        self.oe, self.co, self.ex, self.ag, self.ne = (pick("big_five") for _ in range(5))
        self.language = {"en": "English", "it": "Italian"}.get(language, "English")
        self.topics_opinions = self.topics_sentiment = ""


def use_language(language, folder):
    """Make the prompt store speak ``language`` with its profile values, like a client started by YWeb."""
    for name in (ps.ENV_VAR, ps.FOLDER_VAR):
        os.environ.pop(name, None)
    ps._language, ps._values = None, {}
    if language != "en":
        table = pack(language, "profile_values.json")
        (Path(folder) / f"profile_values.{language}.json").write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    (Path(folder) / ps.RECORD_FILE).write_text(json.dumps({"experiment": language}), encoding="utf-8")
    ps.use_language_from_folder(folder)


def build_messages(task, agent, prompts, rng, language):
    key, _ = TASKS[task]
    stim = rng.choice(STIMULI.get(language, STIMULI["en"]))
    view = ps.localize(agent)
    system = ps.render(prompts["agent_roleplay"], self=view, interest=["music", "politics"], interests=["music", "politics"])
    fields = {"self": view, "post_text": stim, "action": ps.localize_value("action", "follow"),
              "actions": ", ".join(tokens.ACTIONS), "conv": f"@maria - {stim}\n@luca - {rng.choice(STIMULI.get(language, STIMULI['en']))}"}
    user = ps.render(prompts[key], **{k: v for k, v in fields.items() if k in ps.fields_of(prompts[key])})
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# --- models ------------------------------------------------------------------------------------------------------
def call_model(args, messages, rng, task, language):
    if args.simulate:
        return simulate(task, language, rng)
    body = json.dumps({"model": args.model, "messages": messages, "temperature": args.temperature, "max_tokens": args.max_tokens}).encode()
    request = urllib.request.Request(args.base_url.rstrip("/") + "/chat/completions", body, {"Content-Type": "application/json", **(
        {"Authorization": "Bearer " + os.environ[args.api_key_env]} if args.api_key_env and os.environ.get(args.api_key_env) else {})})
    with urllib.request.urlopen(request, timeout=args.timeout) as response:
        return json.loads(response.read())["choices"][0]["message"]["content"] or ""


def simulate(task, language, rng):
    """A stand-in model: mostly obeys the protocol, sometimes chats, writes in the language it is asked."""
    allowed = TASKS[task][1]
    if allowed:
        roll = rng.random()
        if roll < 0.85:
            return rng.choice(allowed)
        return f"I think my answer would be {rng.choice(allowed)}, because it fits me." if roll < 0.95 else "Hmm, hard to say."
    words = ("la città è davvero cambiata e non sono d'accordo con questo" if language == "it" else "the city has really changed and I do not agree with this")
    return f"@maria {words}" if task == "comment" else f"{words} #opinion"


# --- run ---------------------------------------------------------------------------------------------------------
def run(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for model in args.models:
        for language in args.languages:
            for seed in args.seeds:
                target = out / safe_name(model) / language / f"seed{seed}.jsonl"
                if target.exists() and not args.force:
                    print(f"skip {target} (exists)")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                args.model = model
                rng = random.Random(f"{seed}")  # same agents for every model AND every language: only the language varies
                with tempfile.TemporaryDirectory() as folder:
                    use_language(language, folder)
                    prompts = pack(language, "prompts.json")
                    values = pack(language, "profile_values.json") if language != "en" else pack("en", "profile_values.json")
                    agents = [Agent(rng, pack("en", "profile_values.json"), language) for _ in range(args.agents)]
                    rows, started = [], time.time()
                    for day in range(1, args.days + 1):
                        for index, agent in enumerate(agents):
                            for task in TASKS:
                                messages = build_messages(task, agent, prompts, rng, language)
                                row = {"model": model, "language": language, "seed": seed, "agent": index, "day": day, "task": task,
                                       "prompt_sha": hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:12]}
                                t0 = time.time()
                                try:
                                    row["reply"] = call_model(args, messages, random.Random(f"{seed}{model}{language}{index}{day}{task}"), task, language)
                                except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as error:
                                    row["error"] = f"{type(error).__name__}: {error}"
                                row["seconds"] = round(time.time() - t0, 3)
                                rows.append(row)
                target.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
                print(f"{target}: {len(rows)} calls in {time.time() - started:.0f}s")


# --- metrics -----------------------------------------------------------------------------------------------------
def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p, d = k / n, 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def language_match(text, language):
    words = re.findall(r"[a-zàèéìòù']+", text.lower())
    if len(words) < 4:
        return None
    scores = {code: sum(w in stop for w in words) / len(words) for code, stop in STOPWORDS.items()}
    return max(scores, key=scores.get) == language


def score(row):
    task, reply = row["task"], row.get("reply")
    allowed = TASKS[task][1]
    if reply is None:
        return {"ok": False, "error": True}
    if allowed:
        token = tokens.first_token(reply, allowed)
        return {"ok": token is not None, "exact": reply.strip().strip(".!").upper() in allowed, "choice": token}
    return {"ok": bool(reply.strip()), "words": len(reply.split()), "lang": language_match(reply, row["language"]),
            "meta": bool(re.match(r"\s*(sure|here is|here's|certo|ecco)\b", reply.lower()))}


def load(out):
    rows = []
    for path in sorted(Path(out).rglob("seed*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def summarize(rows):
    cells = defaultdict(lambda: defaultdict(list))
    for row in rows:
        cells[(row["model"], row["language"], row["task"])]["rows"].append(score(row))
    table = []
    for (model, language, task), data in sorted(cells.items()):
        scored = data["rows"]
        n = len(scored)
        ok = sum(s["ok"] for s in scored)
        entry = {"model": model, "language": language, "task": task, "n": n, "ok": ok, "ci": wilson(ok, n), "errors": sum(bool(s.get("error")) for s in scored)}
        if TASKS[task][1]:
            entry["exact"] = sum(bool(s.get("exact")) for s in scored) / n
            counts = defaultdict(int)
            for s in scored:
                counts[s.get("choice")] += 1
            entry["choices"] = dict(sorted(counts.items(), key=lambda kv: -kv[1]))
        else:
            langs = [s["lang"] for s in scored if s.get("lang") is not None]
            entry["words"] = sum(s.get("words", 0) for s in scored) / n
            entry["lang_match"] = (sum(langs) / len(langs)) if langs else float("nan")
            entry["meta"] = sum(s.get("meta", False) for s in scored) / n
        table.append(entry)
    return table


def pct(x):
    return "n/a" if x != x else f"{100 * x:.1f}%"


def report(rows, planned):
    lines = ["# Prompt pilot report (EN vs IT)", "",
             "Generated by `scripts/prompts/pilot.py analyze`. Do not edit by hand: re-run the analysis.", "",
             "## Setup", "", f"- Planned design: {planned}",
             "- Each agent-day sends six prompts (action, reaction, follow, vote, post, comment) rendered from the language pack, "
             "with profile values shown in the prompt language and protocol tokens in English.",
             "- Same agents and stimuli order for every model (seeded); only the prompt language changes.", ""]
    if not rows:
        lines += ["## Results", "", "_No runs yet. Run `pilot.py run` where the models are available, then `pilot.py analyze`._", "",
                  "| Model | Language | Task | N | Parsed | 95% CI | Exact | Language match | Meta text |", "|---|---|---|---|---|---|---|---|---|",
                  "| — | — | — | — | — | — | — | — | — |", ""]
    else:
        table = summarize(rows)
        lines += ["## Results by model, language and task", "",
                  "| Model | Language | Task | N | Parsed / valid | 95% CI | Exact token | Language match | Meta text | Errors |", "|---|---|---|---|---|---|---|---|---|---|"]
        for e in table:
            lo, hi = e["ci"]
            exact = pct(e["exact"]) if "exact" in e else "—"
            match = pct(e["lang_match"]) if "lang_match" in e else "—"
            meta = pct(e["meta"]) if "meta" in e else "—"
            lines.append(f"| {e['model']} | {e['language']} | {e['task']} | {e['n']} | {pct(e['ok'] / e['n'])} | {pct(lo)}–{pct(hi)} | {exact} | {match} | {meta} | {e['errors']} |")
        lines += ["", "## Italian versus English (per model and task)", "",
                  "A difference is flagged when the 95% intervals of the parsed rate do not overlap.", "",
                  "| Model | Task | EN parsed | IT parsed | Flag |", "|---|---|---|---|---|"]
        index = {(e["model"], e["language"], e["task"]): e for e in table}
        for (model, language, task), e in sorted(index.items()):
            if language != "en" or (model, "it", task) not in index:
                continue
            it = index[(model, "it", task)]
            overlap = not (e["ci"][1] < it["ci"][0] or it["ci"][1] < e["ci"][0])
            lines.append(f"| {model} | {task} | {pct(e['ok'] / e['n'])} | {pct(it['ok'] / it['n'])} | {'' if overlap else '**check**'} |")
        lines += ["", "## Choices made (action, reaction, follow, vote)", ""]
        for e in table:
            if "choices" in e:
                lines.append(f"- {e['model']} / {e['language']} / {e['task']}: " + ", ".join(f"{k or 'unparsed'}={v}" for k, v in e["choices"].items()))
    lines += ["", "## Reading the numbers", "",
              "- *Parsed / valid*: a protocol token was found by the client's parser (tasks with tokens) or the reply is non-empty (free text).",
              "- *Exact token*: the reply is only the token. Lower values are tolerated by the parsers but show chattier models.",
              "- *Language match*: a stop-word heuristic, meaningful only for free text of four words or more.",
              "- *Meta text*: replies that start with an introduction instead of the post (\"Sure\", \"Ecco\").", "",
              "## Limits", "", "- Prompt-level pilot: it does not run the platform, so recommendation, memory and network effects are not tested.",
              "- Synthetic agents and a short list of stimuli; fine for a protocol check, not for behavioural claims.",
              "- Italian prompt text is still a draft pending native-speaker review (manifest status `draft`).", "",
              "## Decision", "", "_To fill in after the runs: keep, adjust the Italian pack, or change the protocol instructions._", ""]
    return "\n".join(lines)


def analyze(args):
    rows = load(args.out)
    planned = f"{len(args.models_planned or [])} models" if args.models_planned else "2 models x 2 languages x 50 agents x 3 days x 3 seeds (default)"
    text = report(rows, planned)
    Path(args.report).write_text(text, encoding="utf-8")
    print(f"{args.report}: {len(rows)} calls analysed")


def safe_name(model):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--models", nargs="+", required=True)
    r.add_argument("--languages", nargs="+", default=["en", "it"])
    r.add_argument("--agents", type=int, default=50)
    r.add_argument("--days", type=int, default=3)
    r.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    r.add_argument("--base-url", default="http://localhost:11434/v1")
    r.add_argument("--api-key-env")
    r.add_argument("--temperature", type=float, default=0.7)
    r.add_argument("--max-tokens", type=int, default=300)
    r.add_argument("--timeout", type=float, default=120)
    r.add_argument("--out", default="pilot_runs")
    r.add_argument("--simulate", action="store_true", help="use a stand-in model (dry run, no network)")
    r.add_argument("--force", action="store_true", help="overwrite runs that already exist")
    a = sub.add_parser("analyze")
    a.add_argument("--out", default="pilot_runs")
    a.add_argument("--report", default=str(ROOT / "docs" / "prompt-pilot-report.md"))
    a.add_argument("--models-planned", nargs="*")
    args = parser.parse_args(argv)
    (run if args.command == "run" else analyze)(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
