"""Golden snapshots that guard the decoupling of the simulation platforms (plan, phase F0).

Moving the platform code out of YSocial must not change what the application exposes. These snapshots
record, before anything moves, the surface that has to survive:

``url_map``
    every core route (rule, endpoint, methods); routes of installed plugin suites are left out because
    they depend on what is installed.
``db_schema``
    tables and columns of every bind (admin and experiment databases).
``platform_tables``
    the launch table of the HPC platforms and the labels/icons of the known platforms.
``templates``
    the template files shipped by the core.
``i18n_it``
    a digest of every Italian message (msgid -> translation), so that no translated string gets lost.

The budgets work the other way round: they count, per source file, how often the core names a platform. The
counts may only go down (phases F1-F8 replace the names with calls to the platform registry); a budget is
lowered with ``--ratchet``.

``platform_branches``
    comparisons of ``platform_type`` with a platform name.
``platform_names``
    every mention of a platform (``forum``, ``dating``, ``YForum``, ...) in the core code, not counting the
    modules that belong to one platform and are the ones that will move to its repository.

A snapshot only *forbids losing or changing* what it recorded: new routes, columns or templates are allowed.
After an intended change, regenerate the files with::

    python -m y_web.tests._platform_baseline --update
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parents[1]
DATA_DIR = TESTS_DIR / "data" / "platform_baseline"
TEMPLATES_DIR = ROOT / "y_web" / "templates"
IT_CATALOG = ROOT / "y_web" / "translations" / "it" / "LC_MESSAGES" / "messages.po"

_IGNORED_METHODS = {"HEAD", "OPTIONS"}
_PLATFORM_BRANCH = re.compile(r"platform_type\s*(?:==|!=|\bnot\s+in\b|\bin\b)")
_PLATFORM_NAME = re.compile(
    r"\b(?:dating|instant_messaging|photo_sharing|forum|reddit|microblogging)\b"
    r"|\bY(?:Dating|Forum|PhotoSharing|InstantMessaging)\b",
    re.IGNORECASE,
)
# Modules that belong to a single platform: they move to its repository, so their own mentions do not count.
PLATFORM_OWNED = (
    "y_web/src/dating/",
    "y_web/src/im/",
    "y_web/src/forum/",
    "y_web/routes/social/",
    "y_web/routes/interactions/",
    "y_web/routes/api/",
    "y_web/routes/admin/sub/clients/_dating.py",
    "y_web/routes/admin/sub/clients/_im.py",
    "y_web/routes/admin/sub/clients/_forum_hpc.py",
    "y_web/routes/admin/sub/experiments/_dating",
    "y_web/routes/admin/sub/experiments/_im",
    "y_web/platforms/",
)


def _digest(text: str, size: int) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:size]


def collect_url_map(app) -> Dict[str, List[str]]:
    """``"<rule> -> <endpoint>"`` mapped to the sorted methods, for the core blueprints only."""
    from y_web.src.external_runtime import backend_plugins

    plugin_blueprints = set(backend_plugins._BLUEPRINT_OWNERS)
    routes = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint.split(".", 1)[0] in plugin_blueprints:
            continue
        routes[f"{rule.rule} -> {rule.endpoint}"] = sorted(
            (rule.methods or set()) - _IGNORED_METHODS
        )
    return dict(sorted(routes.items()))


def collect_db_schema() -> Dict[str, Dict[str, Dict[str, str]]]:
    """``{bind: {table: {column: "<type> [NOT NULL] [PK]"}}}`` of the declared models."""
    from y_web import db

    schema = {}
    for bind, metadata in db.metadatas.items():
        tables = {}
        for table in metadata.sorted_tables:
            tables[table.name] = {
                column.name: " ".join(
                    part
                    for part in (
                        str(column.type),
                        "" if column.nullable else "NOT NULL",
                        "PK" if column.primary_key else "",
                    )
                    if part
                )
                for column in table.columns
            }
        schema[str(bind)] = dict(sorted(tables.items()))
    return dict(sorted(schema.items()))


def collect_platform_tables() -> Dict[str, dict]:
    from y_web.platforms import registry
    from y_web.src.hpc.platforms import HPC_PLATFORMS

    return {
        "hpc_platforms": {
            key: dataclasses.asdict(platform) for key, platform in HPC_PLATFORMS.items()
        },
        "known_platforms": {
            provider.key: {"label": str(provider.label), "icon": provider.icon}
            for provider in registry.providers()
        },
    }


def collect_templates() -> List[str]:
    return sorted(
        path.relative_to(TEMPLATES_DIR).as_posix()
        for path in TEMPLATES_DIR.rglob("*.html")
    )


def collect_i18n_it() -> Dict[str, str]:
    """``md5(msgid)`` -> ``md5(translation)``: short digests keep the file small, a lost or changed string shows up."""
    from babel.messages.pofile import read_po

    with IT_CATALOG.open("rb") as handle:
        catalog = read_po(handle)
    return {
        _digest(str(message.id), 10): _digest(str(message.string), 8)
        for message in catalog
        if message.id and message.string
    }


def _count_in_core(pattern, skip_owned: bool) -> Dict[str, int]:
    counts = {}
    for path in sorted((ROOT / "y_web").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if "/tests/" in relative or (
            skip_owned and relative.startswith(PLATFORM_OWNED)
        ):
            continue
        found = len(pattern.findall(path.read_text(encoding="utf-8")))
        if found:
            counts[relative] = found
    return counts


def collect_platform_branches() -> Dict[str, int]:
    """``{file: number of platform_type comparisons}`` for the application code (tests excluded)."""
    return _count_in_core(_PLATFORM_BRANCH, skip_owned=False)


def collect_platform_names() -> Dict[str, int]:
    """``{file: number of platform mentions}`` for the core code, platform-owned modules and tests excluded."""
    return _count_in_core(_PLATFORM_NAME, skip_owned=True)


BUDGETS: Dict[str, Callable[[], Dict[str, int]]] = {
    "platform_branches": collect_platform_branches,
    "platform_names": collect_platform_names,
}


def budget_path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def load_budget(name: str) -> Dict[str, int]:
    return json.loads(budget_path(name).read_text("utf-8"))


def budget_excess(budget: Dict[str, int], current: Dict[str, int]) -> List[str]:
    """Files whose count grew over the budget (a file not in the budget has budget 0)."""
    return [
        f"{path}: {count} mentions, budget {budget.get(path, 0)}"
        for path, count in sorted(current.items())
        if count > budget.get(path, 0)
    ]


def collect(name: str, app=None):
    collectors: Dict[str, Callable[[], object]] = {
        "url_map": lambda: collect_url_map(app),
        "db_schema": collect_db_schema,
        "platform_tables": collect_platform_tables,
        "templates": collect_templates,
        "i18n_it": collect_i18n_it,
    }
    return collectors[name]()


SNAPSHOT_NAMES = ("url_map", "db_schema", "platform_tables", "templates", "i18n_it")


def snapshot_path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def load_snapshot(name: str):
    return json.loads(snapshot_path(name).read_text("utf-8"))


def lost_or_changed(baseline, current, path: str = "") -> List[str]:
    """What the baseline recorded that the current state no longer has (or has differently).

    Dicts are compared key by key (extra keys in *current* are fine), lists as sets of items.
    """
    if isinstance(baseline, dict):
        if not isinstance(current, dict):
            return [f"{path or '<root>'}: no longer a mapping"]
        problems = []
        for key, expected in baseline.items():
            where = f"{path}/{key}"
            if key not in current:
                problems.append(f"{where}: removed")
            else:
                problems.extend(lost_or_changed(expected, current[key], where))
        return problems
    if isinstance(baseline, list):
        if not isinstance(current, list):
            return [f"{path or '<root>'}: no longer a list"]
        remaining = [item for item in baseline if item not in current]
        return [f"{path}: {item!r} removed" for item in remaining]
    return [] if baseline == current else [f"{path}: {baseline!r} -> {current!r}"]


def _write_budget(name: str, counts: Dict[str, int]) -> None:
    budget_path(name).write_text(
        json.dumps(counts, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def _ratchet() -> None:
    """Lower every budget to the current counts; refuse to raise one."""
    for name, collector in BUDGETS.items():
        current = collector()
        budget = load_budget(name)
        excess = budget_excess(budget, current)
        if excess:
            sys.exit(f"the {name} budget cannot grow:\n" + "\n".join(excess))
        _write_budget(name, current)
        print(f"{name}: {sum(budget.values())} -> {sum(current.values())}")


def _update() -> None:
    from y_web import create_app

    app = create_app(db_type="sqlite")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, collector in BUDGETS.items():
        _write_budget(name, collector())
    for name in SNAPSHOT_NAMES:
        snapshot_path(name).write_text(
            json.dumps(collect(name, app), indent=1, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        print(f"written {snapshot_path(name).relative_to(ROOT)}")


if __name__ == "__main__":
    option = sys.argv[1] if len(sys.argv) == 2 else ""
    if option == "--update":
        _update()
    elif option == "--ratchet":
        _ratchet()
    else:
        sys.exit("usage: python -m y_web.tests._platform_baseline --update | --ratchet")
