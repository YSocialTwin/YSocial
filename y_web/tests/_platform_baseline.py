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

A snapshot only *forbids losing or changing* what it recorded: new routes, columns or templates are allowed.
After an intended change, regenerate the files with::

    python -m y_web.tests._platform_baseline --update
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parents[1]
DATA_DIR = TESTS_DIR / "data" / "platform_baseline"
TEMPLATES_DIR = ROOT / "y_web" / "templates"
IT_CATALOG = ROOT / "y_web" / "translations" / "it" / "LC_MESSAGES" / "messages.po"

_IGNORED_METHODS = {"HEAD", "OPTIONS"}


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
    from y_web.src.experiment.platform_labels import KNOWN_PLATFORMS
    from y_web.src.hpc.platforms import HPC_PLATFORMS

    return {
        "hpc_platforms": {
            key: dataclasses.asdict(platform) for key, platform in HPC_PLATFORMS.items()
        },
        "known_platforms": {
            key: {"label": str(entry["label"]), "icon": entry["icon"]}
            for key, entry in KNOWN_PLATFORMS.items()
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


def _update() -> None:
    from y_web import create_app

    app = create_app(db_type="sqlite")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in SNAPSHOT_NAMES:
        snapshot_path(name).write_text(
            json.dumps(collect(name, app), indent=1, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        print(f"written {snapshot_path(name).relative_to(ROOT)}")


if __name__ == "__main__":
    if "--update" not in sys.argv[1:]:
        sys.exit("usage: python -m y_web.tests._platform_baseline --update")
    _update()
