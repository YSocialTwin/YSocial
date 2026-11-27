#!/usr/bin/env python3
"""Misura del decoupling core <-> piattaforme/estensioni (stampa JSON).

(a) menzioni dei nomi di piattaforma nel codice di y_web (test e traduzioni esclusi);
(b) import di y_web fuori da y_web.sdk per ogni repository di piattaforma;
(c) import interni del core (y_web) per ogni estensione.

Uso: python scripts/metrics/decoupling.py [--root <core>] [--external <dir>]
"""

import argparse
import json
import re
from pathlib import Path

PLATFORM_NAMES = [
    "reddit",
    "dating",
    "forum",
    "photo_sharing",
    "instant_messaging",
    "y_server",
    "y_client",
]
PLATFORM_REPOS = [
    "YServer",
    "YSimulator",
    "YServerReddit",
    "YForum",
    "YPhotoSharing",
    "YInstantMessaging",
    "YDating",
    "YCreator",
]
EXTENSION_REPOS = [
    "ScenarioDesign",
    "TrainingModules",
    "frontend_adds-on",
    "reactive_agents",
]
# Estensioni di file considerate codice/testo sorgente di y_web
SOURCE_SUFFIXES = {".py", ".html", ".js", ".css", ".json"}
# esclusi: test, traduzioni, dati degli esperimenti, librerie di terze parti
EXCLUDED_DIRS = {
    "tests",
    "translations",
    "__pycache__",
    "node_modules",
    ".git",
    "experiments",
    "vendor",
}
IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(y_web[\w.]*)\s+import|import\s+(y_web[\w.]*))", re.M
)
NAME_RE = re.compile("|".join(PLATFORM_NAMES), re.I)
# v2: whole-word names (no "updating", "memory_server_unavailable"), plus the ``subreddit`` column,
# history of migrations and the generated plugin catalogue left out. v1 stays as the historical ceiling.
NAME_V2_RE = re.compile(
    r"(?<![A-Za-z])(?:reddit|subreddit|dating|forums?|photo_sharing|instant_messaging|y_server|y_client)(?![a-z])",
    re.I,
)
V2_EXCLUDED_SUFFIXES = (
    "db_init/migrations.py",
    "external_runtime/builtin_plugins.json",
)
V2_EXCLUDED_FRAGMENTS = ("alembic/versions/", "/migrations/")
ALLOWLIST_PATH = Path(__file__).with_name("decoupling_allowlist.json")


# the extension API mirrors names of the core by construction (e.g. ``memory_server_unavailable`` contains "y_server")
EXCLUDED_PATHS = {("sdk", "extensions")}


def _is_excluded(path: Path, base: Path) -> bool:
    parts = path.relative_to(base).parts
    if any(p in EXCLUDED_DIRS for p in parts):
        return True
    return any(parts[: len(prefix)] == prefix for prefix in EXCLUDED_PATHS)


def count_mentions(core: Path) -> dict:
    base = core / "y_web"
    total = 0
    files = 0
    for p in base.rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_SUFFIXES or _is_excluded(p, base):
            continue
        try:
            n = len(NAME_RE.findall(p.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
        if n:
            total += n
            files += 1
    return {"mentions": total, "files": files}


def load_allowlist() -> list:
    """Declared exceptions of the zero-dependency goal: ``[{"path": ..., "reason": ...}]``."""
    if not ALLOWLIST_PATH.is_file():
        return []
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8")).get("exceptions", [])


def _v2_skipped(rel: str, allowed: set) -> bool:
    if rel in allowed or rel.endswith(V2_EXCLUDED_SUFFIXES):
        return True
    return any(f in rel for f in V2_EXCLUDED_FRAGMENTS)


def count_mentions_v2(core: Path) -> dict:
    """Whole-word platform names in y_web, minus history and declared exceptions."""
    base = core / "y_web"
    entries = load_allowlist()
    allowed = {e["path"] for e in entries if not e.get("ignore")}
    # an entry with ``ignore`` exempts only the text that regular expression matches
    ignored = {e["path"]: re.compile(e["ignore"]) for e in entries if e.get("ignore")}
    total = 0
    files = {}
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.suffix not in SOURCE_SUFFIXES or _is_excluded(p, base):
            continue
        rel = p.relative_to(core).as_posix()
        if _v2_skipped(rel, allowed):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if rel in ignored:
            text = ignored[rel].sub("", text)
        n = len(NAME_V2_RE.findall(text))
        if n:
            total += n
            files[rel] = n
    return {"mentions": total, "files": len(files), "by_file": files}


def _imports(repo: Path, tests: bool):
    out = []
    for p in repo.rglob("*.py"):
        rel = p.relative_to(repo).parts
        if any(x in {".git", "__pycache__", "node_modules"} for x in rel):
            continue
        if not tests and any(
            x in {"tests", "test"} or x.startswith("test_") for x in rel
        ):
            continue
        for m in IMPORT_RE.finditer(p.read_text(encoding="utf-8", errors="ignore")):
            out.append((m.group(1) or m.group(2), str(Path(*rel))))
    return out


def _outside_sdk(mod: str) -> bool:
    return not (mod == "y_web.sdk" or mod.startswith("y_web.sdk."))


def platform_imports(ext: Path) -> dict:
    res = {}
    for name in PLATFORM_REPOS:
        repo = ext / name
        if not repo.is_dir():
            continue
        outside = [
            {"module": mod, "file": f}
            for mod, f in _imports(repo, tests=False)
            if _outside_sdk(mod)
        ]
        res[name] = {"outside_sdk": len(outside), "items": outside}
    return res


def extension_imports(ext: Path) -> dict:
    res = {}
    for name in EXTENSION_REPOS:
        repo = ext / name
        if not repo.is_dir():
            continue
        items = _imports(repo, tests=False)
        res[name] = {
            "internal_imports": len(items),
            "outside_sdk": sum(1 for mod, _f in items if _outside_sdk(mod)),
        }
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--external", default=None)
    a = ap.parse_args()
    root = Path(a.root)
    ext = Path(a.external) if a.external else root / "external"
    out = {
        "platform_mentions_in_core": count_mentions(root),
        "platform_mentions_in_core_v2": count_mentions_v2(root),
        "platform_imports_outside_sdk": platform_imports(ext),
        "extension_internal_imports": extension_imports(ext),
    }
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
