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
``front_branches`` / ``front_names``
    the same two counts for the templates and the scripts of the core (``.html`` and ``.js``), with the
    translatable texts and the comments taken out: a sentence that mentions a platform is copy, not a decision.

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
# a branch on the platform: ``platform_type`` (or a platform key) compared with a literal; comparing it with another
# value (a declared list, the platform of another experiment) is how the core stays generic and does not count
_PLATFORM_BRANCH = re.compile(
    r"(?:platform_type|platform_key|\.key)\s*(?:==|!=|\bnot\s+in\b|\bin\b)\s*[\(\[\{]?\s*[\"']"
)
_PLATFORM_NAME = re.compile(
    r"\b(?:dating|instant_messaging|photo_sharing|forum|reddit|microblogging)\b"
    r"|\b(?:rfeed|rsearch|rnotifications)\b|/photo/"
    r"|\bY(?:Dating|Forum|PhotoSharing|InstantMessaging)\b",
    re.IGNORECASE,
)
# The only places that may still name a platform (gate G8): historical migrations, which describe the schema of
# the day and must keep reading as they did, and the process entry point that runs before the registry exists.
DECLARED_EXCEPTIONS = (
    "y_web/alembic/versions/",
    "y_web/db_init/migrations.py",
    "y_web/migrations/",
    # Reddit as a place feeds come from (a host and an address layout), not as a platform of the simulation;
    # and the hash salt of the Hot ranking, which is part of the data it ranked
    "y_web/src/commons/reddit_feeds.py",
    # the descriptions of the built-in plugin catalogue, which names the repositories it installs
)
# Modules that belong to a single platform: they move to its repository, so their own mentions do not count.
PLATFORM_OWNED = (
    "y_web/src/dating/",
    "y_web/src/im/",
    "y_web/src/forum/",
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


# The pages and scripts of the core: a platform is named here only in the descriptive copy of the tutorials and in the
# pages of the feed resources (forum feeds come from Reddit and RSS), which are not a platform of the simulation.
FRONT_EXCEPTIONS = (
    "y_web/static/assets/js/admin-pages-tutorial.js",
    "y_web/static/assets/js/external-runtimes-tutorial.js",
    "y_web/static/assets/js/external-runtime-detail-tutorial.js",
    "y_web/static/assets/js/experiments-tutorial.js",
    "y_web/static/assets/js/admin-feeds.js",
    "y_web/templates/admin/rss_feeds.html",
    "y_web/templates/admin/feed_limits.html",
    "y_web/templates/admin/image_feeds.html",
)
_FRONT_BRANCH = re.compile(
    r"(?:platform_type|platform_key|platformType|platform|variant|ws_v|\.key)\s*(?:===?|!==?|\bnot\s+in\b|\bin\b)\s*"
    r"[\(\[\{]?\s*[\"'](?:microblogging|forum|photo_sharing|photo|instant_messaging|im|dating|hpc)[\"']"
)
_COPY = re.compile(
    r"\{#.*?#\}|<!--.*?-->|/\*.*?\*/|(?<![:\"'])//[^\n]*"
    r"|(?:\b_|\bYI18n\.t|\bgettext|\bngettext)\(\s*(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")",
    re.DOTALL,
)
_FRONT_DIRS = ("templates", "static/assets/js")


def _front_files():
    for sub in _FRONT_DIRS:
        for path in sorted((ROOT / "y_web" / sub).rglob("*")):
            relative = path.relative_to(ROOT).as_posix()
            if path.suffix not in (".html", ".js") or ".min." in path.name:
                continue
            if "/vendor/" in relative or path.name == "app.js":
                continue
            yield path, relative


def _count_front(pattern) -> Dict[str, int]:
    counts = {}
    for path, relative in _front_files():
        found = len(pattern.findall(_COPY.sub("", path.read_text(encoding="utf-8"))))
        if found:
            counts[relative] = found
    return counts


def collect_front_branches() -> Dict[str, int]:
    """``{file: comparisons of a platform with a literal}`` in the templates and scripts of the core."""
    return _count_front(_FRONT_BRANCH)


def collect_front_names() -> Dict[str, int]:
    """``{file: mentions of a platform}`` in the templates and scripts of the core (copy and comments excluded)."""
    return _count_front(_PLATFORM_NAME)


# Identifiers (variables, functions, classes, attributes) that carry the name of a platform or of an engine, which
# the word-bounded name patterns above do not see (``ForumChatSession``, ``is_photo_sharing``, ``toggleForumMemory``).
# Strings, comments and the copy of the pages are left out: those are the names gate's business.
_PLATFORM_IDENTIFIER = re.compile(
    r"forum|reddit|photo_?sharing|instant_?messag|micro_?blog|(?<![A-Za-z])y_?(?:simulator|server|client)(?!_memory)"
    r"|(?<![A-Za-z])dating|(?-i:[a-z]Dating)|rfeed|rsearch|rnotifications",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z_$][\w$]*")


def _python_identifiers(source: str):
    import io
    import tokenize

    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NAME:
                yield token.string
    except (tokenize.TokenError, IndentationError):
        return


# The only places of the core whose identifiers may still carry such a name, and why.
IDENTIFIER_EXCEPTIONS = (
    # Reddit and RSS as the places feeds come from (a subreddit, a listing), and the facade the SDK gives them
    "y_web/src/content/feeds.py",
    "y_web/src/content/text_utils.py",
    # the SDK keeps the former names of what it renamed (ForumChatSession...), for plugins written against it
    "y_web/sdk/",
    # the persisted ``subreddit`` column of the feed resources
    "y_web/src/models/admin.py",
    "y_web/src/models/experiment.py",
    # the Python packages of the engines (``y_server``, ``y_client``): the contract the core runs them through
    "y_web/src/simulation/process_runner.py",
    "y_web/src/simulation/federation_hooks.py",
)


_CSS_PLATFORM = re.compile(
    r"dating|\.is-photo\b|chip-photo|photo-?sharing|forum|reddit|instant|microblog|\.is-im\b|\.im-|ws-also--(?!default)",
    re.IGNORECASE,
)
_CSS_FILES = (
    "admin-clients.css",
    "admin-components.css",
    "admin-layout.css",
    "admin-miscellanea.css",
    "admin-responsive.css",
    "admin-settings.css",
    "admin-tutorials.css",
    "admin-world-simulation.css",
    "social-components.css",
)


def collect_css_selectors() -> Dict[str, int]:
    """``{file: rules of the core stylesheets whose selector names a platform}`` (the theme files are not the core's)."""
    counts = {}
    for name in _CSS_FILES:
        path = ROOT / "y_web" / "static" / "assets" / "css" / name
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        found = sum(
            1
            for selector in re.findall(r"([^{};]+)\{", text)
            if not selector.strip().startswith("@") and _CSS_PLATFORM.search(selector)
        )
        if found:
            counts[f"y_web/static/assets/css/{name}"] = found
    return counts


def collect_platform_identifiers() -> Dict[str, int]:
    """``{file: identifiers naming a platform or an engine}`` for the core code (strings and comments excluded)."""
    counts = {}
    for path in sorted((ROOT / "y_web").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if "/tests/" in relative or relative.startswith(
            PLATFORM_OWNED + DECLARED_EXCEPTIONS
        ):
            continue
        found = sum(
            1
            for name in _python_identifiers(path.read_text(encoding="utf-8"))
            if _PLATFORM_IDENTIFIER.search(name)
        )
        if found:
            counts[relative] = found
    return counts


_QUOTED = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'")


def collect_front_identifiers() -> Dict[str, int]:
    """``{file: identifiers naming a platform}`` in the scripts of the core (strings, comments and copy excluded)."""
    counts = {}
    for path, relative in _front_files():
        if path.suffix != ".js":
            continue
        code = _QUOTED.sub('""', _COPY.sub("", path.read_text(encoding="utf-8")))
        found = sum(
            1 for word in _WORD.findall(code) if _PLATFORM_IDENTIFIER.search(word)
        )
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
    "front_branches": collect_front_branches,
    "front_names": collect_front_names,
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


def load_moved() -> Dict[str, Dict[str, Dict[str, str]]]:
    """What left the core for the repository of a platform: ``{"templates": {core path: {"to", "repo"}}}``."""
    return json.loads((DATA_DIR / "moved.json").read_text("utf-8"))


def repository_templates(spec: Dict[str, str]) -> Path:
    """The templates folder of the repository a template moved to (it exists only where that repository is installed)."""
    return (
        Path(__file__).resolve().parents[2]
        / "external"
        / spec["repo"]
        / "ysocial_platform"
        / "templates"
    )


def moved_template_in_repository(spec: Dict[str, str]) -> Path:
    """Where a moved template is in the checkout of its repository (``@<platform>/<path>``)."""
    return repository_templates(spec) / spec["to"].split("/", 1)[1]


def repository_installed(repo: str) -> bool:
    """Whether the checkout of a platform repository (with its ``ysocial_platform/`` folder) is installed."""
    return (
        Path(__file__).resolve().parents[2] / "external" / repo / "ysocial_platform"
    ).is_dir()


def without_moved(name: str, baseline):
    """The baseline minus what was deliberately moved out of the core.

    Templates are checked separately in their repository. What a repository adds at run time (endpoints, the known
    platform) is expected only where that repository is installed.
    """
    moved = load_moved()
    if name == "templates":
        renamed = moved.get("renamed_templates", {})
        return [
            path
            for path in baseline
            if path not in moved["templates"] and path not in renamed
        ]
    if name == "url_map":
        absent = {
            rule
            for repo, rules in moved.get("url_map", {}).items()
            if not repository_installed(repo)
            for rule in rules
        }
        return {k: v for k, v in baseline.items() if k not in absent}
    if name == "platform_tables":
        absent = {
            key
            for repo, keys in moved.get("known_platforms", {}).items()
            if not repository_installed(repo)
            for key in keys
        }
        known = baseline.get("known_platforms")
        if absent and isinstance(known, dict):
            baseline = {
                **baseline,
                "known_platforms": {k: v for k, v in known.items() if k not in absent},
            }
        hpc = baseline.get("hpc_platforms")
        if isinstance(hpc, dict):  # a row is declared by its runtime's repository
            baseline = {
                **baseline,
                "hpc_platforms": {
                    k: v
                    for k, v in hpc.items()
                    if repository_installed(v.get("runtime_repo"))
                },
            }
        return baseline
    return baseline


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
