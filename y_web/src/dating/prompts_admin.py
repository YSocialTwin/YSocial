"""Prompts of a dating experiment: what the admin page shows and how an edit is stored (plan S5, IR-D-13).

The runtime builds its prompts from the English pack, the pack of the language and, over both,
``prompts_dating.json`` (``prompts_dating.<lang>.json`` for another language) in the experiment folder
(``YDating.prompt_overrides``). The page edits the last layer and writes **only the keys that differ from the
package**, so a prompt left alone keeps following the package when it is improved. A template may drop a field
but never name one the package prompt does not offer. Each prompt is shown with the first characters of the
SHA-256 of its effective text, the value the runtime records for every client (``prompt_hashes_<client>.json``).
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PREFIX = "p."
PACK = os.path.join("YDating", "prompts_internal.json")
BASENAME = "prompts_dating"


def N_(message):
    return message


GROUPS: List[Tuple[str, str, str, List[str]]] = [
    (
        "persona",
        N_("Agents"),
        N_("Who the model is told it is and how the profile of the agent is worded."),
        [
            "persona",
            "persona_personality_line",
            "persona_bio_line",
            "intent_serious",
            "intent_casual",
            "intent_friendship",
            "intent_unsure",
            "unspecified",
        ],
    ),
    (
        "swipe",
        N_("Swipes and ranking"),
        N_("What the model reads to decide on a card and to order candidates."),
        [
            "swipe_decision",
            "swipe_seen_before",
            "swipe_options_plain",
            "swipe_options_superlike",
            "history_me",
            "history_empty",
            "rerank_candidates",
            "rerank_candidate_line",
        ],
    ),
    (
        "conversation",
        N_("Conversations and dates"),
        N_("First messages, replies, unmatching and date proposals."),
        [
            "opener",
            "reply",
            "reply_variety_hint",
            "unmatch_decision",
            "date_proposal",
            "date_response",
            "template_opener_1",
            "template_opener_2",
            "template_opener_3",
            "template_reply_1",
            "template_reply_2",
            "template_reply_3",
            "template_date_proposal",
            "template_date_accept",
            "template_date_decline",
        ],
    ),
    (
        "profile",
        N_("Profiles"),
        N_(
            "Bio, profile questions and photo captions written when the run starts and refreshed by the lifecycle."
        ),
        [
            "bio_generation",
            "prompt_answer",
            "profile_question_1",
            "profile_question_2",
            "profile_question_3",
            "profile_photo_caption",
            "profile_update",
            "template_bio",
        ],
    ),
    (
        "annotations",
        N_("Annotations and stress/reward"),
        N_(
            "Emotion extraction and the tone of a message, when annotations or stress/reward are on."
        ),
        ["extract_emotions", "message_tone"],
    ),
]

# the field syntax of the runtime's prompt store (kept in step by a test)
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_PATH = (
    rf"(?P<root>{_NAME})(?P<steps>(?:\.{_NAME}|\[(?:'[^'\n]*'|\"[^\"\n]*\"|\d+)\])*)"
)
_JOIN = rf"(?:'(?P<sq>[^'\n]*)'|\"(?P<dq>[^\"\n]*)\")\.join\((?P<jroot>{_NAME})\)"
_SPEC = r"(?::(?P<spec>[<>^]?\d*(?:\.\d+)?[sdf]?))?"
FIELD = re.compile(rf"\{{(?:{_PATH}|{_JOIN}){_SPEC}\}}")


def fields_of(text: str) -> set:
    return {m.group("root") or m.group("jroot") for m in FIELD.finditer(text or "")}


def _repo(repo_dir: Optional[str] = None) -> str:
    if repo_dir:
        return repo_dir
    from y_web.src.system.path_utils import get_external_repo_dir

    return get_external_repo_dir("YDating")


def _load(path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def languages(repo_dir: Optional[str] = None) -> List[str]:
    """The prompt languages the package ships (English plus every ``prompts_internal.<lang>.json``)."""
    folder = Path(_repo(repo_dir)) / "YDating"
    langs = ["en"]
    for p in sorted(folder.glob("prompts_internal.*.json")):
        langs.append(p.name.split(".")[1])
    return langs


def language_of(
    experiment, wanted: Optional[str], repo_dir: Optional[str] = None
) -> str:
    available = languages(repo_dir)
    for candidate in (wanted, getattr(experiment, "prompt_language", None), "en"):
        if candidate in available:
            return candidate
    return "en"


def prompt_file(folder: str, language: str) -> Path:
    return Path(folder) / (
        f"{BASENAME}.json" if language == "en" else f"{BASENAME}.{language}.json"
    )


def base_templates(language: str, repo_dir: Optional[str] = None) -> Dict[str, str]:
    """The package prompts of ``language`` (English underneath, as the runtime layers them)."""
    folder = Path(_repo(repo_dir)) / "YDating"
    base = _load(folder / "prompts_internal.json")
    if language != "en":
        base.update(_load(folder / f"prompts_internal.{language}.json"))
    return base


def custom_templates(folder: str, language: str) -> Dict[str, Any]:
    return _load(prompt_file(folder, language))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sections(base: Dict[str, str], custom: Dict[str, Any]) -> List[Dict[str, Any]]:
    placed, out = set(), []
    for gid, title, descr, keys in GROUPS:
        items = [_item(k, base, custom) for k in keys if k in base]
        placed.update(keys)
        if items:
            out.append({"id": gid, "title": title, "descr": descr, "items": items})
    rest = [_item(k, base, custom) for k in base if k not in placed]
    if rest:
        out.append(
            {
                "id": "other",
                "title": N_("Other"),
                "descr": N_("Prompts that belong to no section above."),
                "items": rest,
            }
        )
    return out


def _item(key: str, base: Dict[str, str], custom: Dict[str, Any]) -> Dict[str, Any]:
    default = base[key]
    value = custom.get(key)
    value = value if isinstance(value, str) and value.strip() else default
    return {
        "key": key,
        "value": value,
        "modified": value != default,
        "fields": sorted(fields_of(default)),
        "hash": digest(value)[:12],
        "rows": min(10, max(2, value.count("\n") + 1 + len(value) // 90)),
    }


def parse_form(form, base: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """``(override, errors)``: the keys whose submitted value differs from the package, validated."""
    override: Dict[str, str] = {}
    errors: List[str] = []
    for key, default in base.items():
        raw = form.get(f"{PREFIX}{key}")
        if raw is None:
            continue
        new = raw.replace("\r\n", "\n")
        if new == default:
            continue
        if not new.strip():
            errors.append(f"{key}: the prompt cannot be empty")
            continue
        extra = fields_of(new) - fields_of(default)
        if extra:
            errors.append(f"{key}: unknown field {{{sorted(extra)[0]}}}")
            continue
        override[key] = new
    return override, errors


def save(folder: str, language: str, override: Dict[str, str]) -> None:
    path = prompt_file(folder, language)
    if not override:
        if path.exists():
            os.remove(path)
        return
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(override, indent=4, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
