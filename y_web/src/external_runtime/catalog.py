"""Client of the public YSocial plugin registry.

The registry (https://github.com/YSocialTwin/plugin-registry) is a JSON file that
lists plugins and the GitHub repository each one lives in. It lets a new plugin
show up in the plugin page of an already installed YSocial without releasing a new
YSocial (or installer) version.

Safety model -- what a registry entry can and cannot do:

* It names a GitHub ``owner/name`` repository; the clone URL is always built here
  (``https://github.com/<owner>/<name>.git``), never taken from the file.
* It picks an install *recipe* by name from the fixed ``RECIPES`` below. It cannot
  carry commands of its own.
* ``trust: official`` is honoured only for repositories of ``OFFICIAL_OWNERS``;
  anything else is shown as ``community`` (with a warning and a confirmation).
* A malformed entry is skipped, never partially applied; built-in plugins always
  win on a key collision.

Fetched once per start-up (background), cached on disk for offline use.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from y_web.src.external_runtime.registry import (
    EXTERNAL_DIR,
    SUPPORTED_EXTERNAL_REPOS,
    ExternalRuntimeSpec,
    set_catalog_specs,
)

DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/YSocialTwin/plugin-registry/main/registry.json"
)
REGISTRY_URL_ENV = "YSOCIAL_PLUGIN_REGISTRY_URL"  # URL, local path, or "off"
SCHEMA_VERSION = 1
MAX_REGISTRY_BYTES = 1_000_000
MAX_PLUGINS = 500
FETCH_TIMEOUT = 5.0

OFFICIAL_OWNERS = frozenset({"ysocialtwin"})
TRUST_LEVELS = ("official", "community")

# name -> install commands. ``auto`` lets the manager detect requirements.txt /
# pyproject.toml / setup.py (and install nothing when there is none).
RECIPES: dict[str, tuple[tuple[str, ...], ...]] = {
    "auto": (),
    "requirements": (
        ("python", "-m", "pip", "install", "-r", "requirements.txt"),
    ),
    "pip-editable": (("python", "-m", "pip", "install", "-e", "."),),
}
RECIPE_ENTRYPOINTS: dict[str, tuple[str, ...]] = {
    "auto": (),
    "requirements": ("requirements.txt",),
    "pip-editable": (),
}

# registry category -> (group, group_label, category_label); these are the groups
# the rest of the app already knows how to handle.
CATEGORIES: dict[str, tuple[str, str, str]] = {
    "agent_extensions": ("frontend_plugins", "Frontend Plugins", "Agent Extensions"),
    "frontend_extensions": (
        "frontend_plugins",
        "Frontend Plugins",
        "Frontend Extensions",
    ),
    "backend_extensions": (
        "backend_settings",
        "Backend Settings",
        "Backend Extensions",
    ),
}

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
_DIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")

_REPORT: dict = {"source": None, "loaded": 0, "problems": [], "fetched_at": None}
_LOCK = threading.Lock()


def registry_url() -> str | None:
    """The configured registry location, or ``None`` when disabled."""
    value = os.environ.get(REGISTRY_URL_ENV)
    if value is None:
        return DEFAULT_REGISTRY_URL
    value = value.strip()
    if value.lower() in {"", "off", "none", "0", "false"}:
        return None
    return value


def cache_path() -> Path:
    return EXTERNAL_DIR / "plugin_registry_cache.json"


def catalog_report() -> dict:
    """Diagnostics of the last load (source, number of plugins, skipped entries)."""
    with _LOCK:
        return {
            "source": _REPORT["source"],
            "loaded": _REPORT["loaded"],
            "problems": list(_REPORT["problems"]),
            "fetched_at": _REPORT["fetched_at"],
        }


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(p) for p in str(value).split(".") if p.isdigit()) or (0,)


def _app_version() -> str | None:
    from y_web.src.external_runtime.backend_plugins import _app_version as app_version

    return app_version()


def _text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def parse_registry(
    payload, app_version: str | None = None
) -> tuple[dict[str, ExternalRuntimeSpec], list[str]]:
    """Validate a decoded registry file. Returns ``(specs, problems)``.

    Never raises: a bad file yields no specs and a problem, a bad entry is skipped.
    """
    problems: list[str] = []
    if not isinstance(payload, dict):
        return {}, ["registry root must be a JSON object"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        return {}, [
            f"unsupported schema_version {payload.get('schema_version')!r} "
            f"(this YSocial reads {SCHEMA_VERSION})"
        ]
    entries = payload.get("plugins")
    if not isinstance(entries, list):
        return {}, ["'plugins' must be a list"]

    specs: dict[str, ExternalRuntimeSpec] = {}
    used_dirs = {spec.path.name.lower() for spec in SUPPORTED_EXTERNAL_REPOS.values()}
    used_repos = {spec.github_repo.lower() for spec in SUPPORTED_EXTERNAL_REPOS.values()}
    for index, entry in enumerate(entries[:MAX_PLUGINS]):
        where = f"entry #{index}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: not an object")
            continue
        key = _text(entry.get("id"), 64)
        where = f"entry {key or index!r}"
        if not _ID_RE.match(key):
            problems.append(f"{where}: invalid id (lowercase letters, digits, _)")
            continue
        if key in SUPPORTED_EXTERNAL_REPOS or key in specs:
            problems.append(f"{where}: id already in use")
            continue

        repo = _text(entry.get("repo"), 140)
        if not _REPO_RE.match(repo):
            problems.append(f"{where}: repo must look like 'owner/name'")
            continue
        branch = _text(entry.get("branch") or "main", 100)
        if not _BRANCH_RE.match(branch) or ".." in branch:
            problems.append(f"{where}: invalid branch")
            continue
        directory = _text(entry.get("directory") or repo.split("/", 1)[1], 64)
        if not _DIR_RE.match(directory) or directory in {".", ".."}:
            problems.append(f"{where}: invalid directory")
            continue
        if directory.lower() in used_dirs or repo.lower() in used_repos:
            problems.append(f"{where}: directory or repo already used")
            continue

        recipe = _text(entry.get("recipe") or "auto", 32)
        if recipe not in RECIPES:
            problems.append(f"{where}: unknown recipe {recipe!r}")
            continue
        category = _text(entry.get("category"), 40)
        if category not in CATEGORIES:
            problems.append(f"{where}: unknown category {category!r}")
            continue
        label = _text(entry.get("name"), 80)
        if not label:
            problems.append(f"{where}: missing name")
            continue

        import_name = entry.get("import_name")
        if import_name is not None and not (
            isinstance(import_name, str) and _MODULE_RE.match(import_name)
        ):
            problems.append(f"{where}: invalid import_name")
            continue

        min_version = entry.get("min_ysocial_version")
        if min_version is not None and not (
            isinstance(min_version, str) and _VERSION_RE.match(min_version)
        ):
            problems.append(f"{where}: invalid min_ysocial_version")
            continue
        if (
            min_version
            and app_version
            and _version_tuple(app_version) < _version_tuple(min_version)
        ):
            problems.append(f"{where}: needs YSocial >= {min_version} (skipped)")
            continue

        trust = _text(entry.get("trust") or "community", 16).lower()
        if trust not in TRUST_LEVELS:
            trust = "community"
        if trust == "official" and repo.split("/", 1)[0].lower() not in OFFICIAL_OWNERS:
            trust = "community"  # the file cannot grant itself official status

        authors = entry.get("authors") or []
        if not isinstance(authors, list):
            authors = []
        group, group_label, category_label = CATEGORIES[category]
        used_dirs.add(directory.lower())
        used_repos.add(repo.lower())
        specs[key] = ExternalRuntimeSpec(
            key=key,
            group=group,
            group_label=group_label,
            category=category,
            category_label=category_label,
            label=label,
            path=EXTERNAL_DIR / directory,
            github_repo=repo,
            repo_url=f"https://github.com/{repo}.git",
            default_branch=branch,
            install_commands=RECIPES[recipe],
            validate_entrypoints=RECIPE_ENTRYPOINTS[recipe],
            validate_import=import_name,
            is_private=bool(entry.get("private", False)),
            trust=trust,
            source="registry",
            description=_text(entry.get("description"), 400),
            authors=tuple(_text(a, 80) for a in authors[:10] if _text(a, 80)),
            min_ysocial_version=min_version,
        )
    if len(entries) > MAX_PLUGINS:
        problems.append(f"only the first {MAX_PLUGINS} entries are read")
    return specs, problems


def _apply(payload, source: str, fetched_at: float | None) -> bool:
    specs, problems = parse_registry(payload, _app_version())
    schema_ok = isinstance(payload, dict) and payload.get("schema_version") == (
        SCHEMA_VERSION
    )
    if not schema_ok:
        with _LOCK:
            _REPORT["problems"] = problems  # keep the previous plugins in place
        return False
    set_catalog_specs(specs)
    with _LOCK:
        _REPORT.update(
            source=source, loaded=len(specs), problems=problems, fetched_at=fetched_at
        )
    return True


def load_cached_catalog() -> bool:
    """Apply the last fetched registry from disk (fast, no network)."""
    try:
        wrapper = json.loads(cache_path().read_text(encoding="utf-8"))
        return _apply(wrapper["registry"], "cache", float(wrapper.get("fetched_at")))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _read_remote(url: str, timeout: float):
    import requests

    if not url.lower().startswith(("http://", "https://")):
        path = Path(url)
        if path.stat().st_size > MAX_REGISTRY_BYTES:
            raise ValueError("registry file too large")
        return json.loads(path.read_text(encoding="utf-8"))
    with requests.get(url, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        raw = response.raw.read(MAX_REGISTRY_BYTES + 1, decode_content=True)
    if len(raw) > MAX_REGISTRY_BYTES:
        raise ValueError("registry file too large")
    return json.loads(raw.decode("utf-8"))


def refresh_catalog(*, timeout: float = FETCH_TIMEOUT) -> bool:
    """Fetch the registry and apply it; any failure keeps what is loaded now."""
    try:
        from flask import current_app, has_app_context

        if has_app_context() and current_app.config.get("TESTING"):
            return False
    except RuntimeError:
        pass
    url = registry_url()
    if not url:
        return False
    try:
        payload = _read_remote(url, timeout)
    except Exception as exc:  # offline, 404, bad JSON ...: keep the cached one
        with _LOCK:
            _REPORT["problems"] = [f"could not fetch the plugin registry: {exc}"]
        return False
    now = time.time()
    if not _apply(payload, "remote", now):
        return False
    try:
        path = cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"fetched_at": now, "registry": payload}), encoding="utf-8"
        )
    except OSError:
        pass
    return True


def start_catalog_refresh() -> None:
    """At start-up: cached registry right away, fresh copy in the background."""
    if not registry_url():
        return
    load_cached_catalog()
    threading.Thread(
        target=refresh_catalog, name="plugin-registry-fetch", daemon=True
    ).start()
