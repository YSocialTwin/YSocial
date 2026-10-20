"""Registry of supported external runtime repositories."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from y_web.i18n import N_
from y_web.src.system.path_utils import get_resource_path, get_writable_path

# Texts of the plugin list that live in this module or in repositories without a
# translation catalog of their own. They are only declared here (for extraction);
# the plugin pages translate them when they are shown.
RUNTIME_TEXTS = (
    N_("Simulation Runtime Stack"),
    N_("Agent Extensions"),
    N_("Frontend Extensions"),
    N_("Backend Extensions"),
    N_("Runs the agents of a microblogging simulation (client side)."),
    N_("Hosts the microblogging platform the agents interact with (server side)."),
    N_("Runs the agents of a forum simulation (client side)."),
    N_("Hosts the forum platform the agents interact with (server side)."),
    N_(
        "Simulation runtime for photo-sharing experiments, with an Instagram-like platform."
    ),
    N_("Runs large-scale simulations in a distributed way on HPC clusters."),
    N_(
        "Gives simulated agents a memory of past interactions: relationship history, thread continuity and conversation cues used when they reply."
    ),
)

ROOT = Path(get_writable_path())
EXTERNAL_DIR = ROOT / "external"
RESOURCE_EXTERNAL_DIR = Path(get_resource_path("external"))
PLUGINS_INDEX_PATH = EXTERNAL_DIR / "plugins.json"
PLUGIN_INFO_RELATIVE_PATH = Path("meta") / "info.json"
PLUGIN_REGISTRY_RELATIVE_PATH = Path("meta") / "registry.json"
LEGACY_PLUGIN_REGISTRY_PATHS = (
    Path("plugins_exposed") / "agent_types.json",
    Path("plugin_exposed") / "agent_types.json",
)
_BOOTSTRAP_REPORT = {
    "writable_external_dir": str(EXTERNAL_DIR),
    "resource_external_dir": str(RESOURCE_EXTERNAL_DIR),
    "seeded_repos": [],
    "existing_repos": [],
    "missing_resource_repos": [],
    "seed_errors": {},
}


BUILTIN_PLUGINS_FILE = Path(__file__).with_name("builtin_plugins.json")


def _read_builtin_payload() -> list[dict]:
    """The plugins that ship with YSocial (``builtin_plugins.json``, in the package).

    This file is part of the release, not downloaded: it is the trusted base that
    the public plugin registry (``catalog.py``) can add to but never override.
    """
    payload = json.loads(BUILTIN_PLUGINS_FILE.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(
        payload.get("plugins"), list
    ):
        raise ValueError(f"unsupported format: {BUILTIN_PLUGINS_FILE.name}")
    return payload["plugins"]


_BUILTIN_PAYLOAD = _read_builtin_payload()


def _seed_external_runtime_repo(repo_name: str) -> str:
    """Copy bundled external runtime repo into writable storage on first run."""
    target_dir = EXTERNAL_DIR / repo_name
    if target_dir.exists():
        return "existing"
    source_dir = RESOURCE_EXTERNAL_DIR / repo_name
    if not source_dir.exists() or not source_dir.is_dir():
        return "missing_resource"
    # In source mode writable/resource roots are the same; avoid self-copy.
    if source_dir.resolve() == target_dir.resolve():
        return "same_path"
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir, dirs_exist_ok=False)
    return "seeded"


def ensure_external_runtime_layout() -> None:
    """
    Ensure writable external runtime directory exists and seed it from bundled
    resources when running a frozen build for the first time.
    """
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    for repo_name in [e["directory"] for e in _BUILTIN_PAYLOAD if e.get("seed")]:
        try:
            result = _seed_external_runtime_repo(repo_name)
            if result == "seeded":
                _BOOTSTRAP_REPORT["seeded_repos"].append(repo_name)
            elif result in {"existing", "same_path"}:
                _BOOTSTRAP_REPORT["existing_repos"].append(repo_name)
            elif result == "missing_resource":
                _BOOTSTRAP_REPORT["missing_resource_repos"].append(repo_name)
        except Exception as exc:
            # Keep startup resilient: failure to seed must not break import.
            _BOOTSTRAP_REPORT["seed_errors"][repo_name] = str(exc)


def external_runtime_bootstrap_report() -> dict:
    """Return startup diagnostics for writable external runtime initialization."""
    return {
        "writable_external_dir": _BOOTSTRAP_REPORT["writable_external_dir"],
        "resource_external_dir": _BOOTSTRAP_REPORT["resource_external_dir"],
        "seeded_repos": list(_BOOTSTRAP_REPORT["seeded_repos"]),
        "existing_repos": list(_BOOTSTRAP_REPORT["existing_repos"]),
        "missing_resource_repos": list(_BOOTSTRAP_REPORT["missing_resource_repos"]),
        "seed_errors": dict(_BOOTSTRAP_REPORT["seed_errors"]),
    }


ensure_external_runtime_layout()


@dataclass(frozen=True)
class ExternalRuntimeSpec:
    key: str
    group: str
    group_label: str
    category: str
    category_label: str
    label: str
    path: Path
    github_repo: str
    repo_url: str
    default_branch: str
    install_commands: tuple[tuple[str, ...], ...]
    validate_entrypoints: tuple[str, ...]
    validate_import: str | None = None
    is_private: bool = True
    visible_to_usernames: tuple[str, ...] = ()
    # Plugins listed in the public plugin registry (``catalog.py``) carry these;
    # the repositories hard-coded below keep the defaults.
    trust: str = "official"  # "official" | "community"
    source: str = "builtin"  # "builtin" | "registry"
    description: str = ""
    authors: tuple[str, ...] = ()
    min_ysocial_version: str | None = None


def _builtin_spec(entry: dict) -> ExternalRuntimeSpec:
    repo = entry["repo"]
    return ExternalRuntimeSpec(
        key=entry["key"],
        group=entry["group"],
        group_label=entry["group_label"],
        category=entry["category"],
        category_label=entry["category_label"],
        label=entry["label"],
        path=EXTERNAL_DIR / entry["directory"],
        github_repo=repo,
        repo_url=f"https://github.com/{repo}.git",
        default_branch=entry.get("branch", "main"),
        install_commands=tuple(tuple(c) for c in entry.get("install_commands", ())),
        validate_entrypoints=tuple(entry.get("validate_entrypoints", ())),
        validate_import=entry.get("validate_import"),
        is_private=bool(entry.get("private", True)),
        visible_to_usernames=tuple(entry.get("visible_to_usernames", ())),
        description=str(entry.get("description") or "").strip(),
    )


# Built-in plugins: the data lives in ``builtin_plugins.json``; the keys are
# referenced from the rest of the code (experiment types, locks, ...), so they
# are stable and never come from the network.
SUPPORTED_EXTERNAL_REPOS: dict[str, ExternalRuntimeSpec] = {
    entry["key"]: _builtin_spec(entry) for entry in _BUILTIN_PAYLOAD
}


# --- plugins listed in the public plugin registry ----------------------------
# ``SUPPORTED_EXTERNAL_REPOS`` stays the built-in whitelist. The registry client
# (``catalog.py``) only ever adds *validated* entries here, never overrides a
# built-in key, and callers read the merged view through ``supported_repos()``.
_CATALOG_SPECS: dict[str, ExternalRuntimeSpec] = {}
_CATALOG_LOCK = threading.Lock()


def set_catalog_specs(specs: dict[str, ExternalRuntimeSpec]) -> None:
    """Replace the registry-provided specs (built-in keys are never shadowed)."""
    clean = {k: v for k, v in specs.items() if k not in SUPPORTED_EXTERNAL_REPOS}
    with _CATALOG_LOCK:
        _CATALOG_SPECS.clear()
        _CATALOG_SPECS.update(clean)


def supported_repos() -> dict[str, ExternalRuntimeSpec]:
    """Snapshot of the built-in repositories plus the registry-provided ones."""
    with _CATALOG_LOCK:
        extra = dict(_CATALOG_SPECS)
    merged = dict(SUPPORTED_EXTERNAL_REPOS)
    merged.update(extra)
    return merged


def runtime_spec(repo_key: str) -> ExternalRuntimeSpec:
    return supported_repos()[repo_key]


def grouped_runtime_specs() -> list[tuple[str, str, Sequence[ExternalRuntimeSpec]]]:
    groups: dict[str, list[ExternalRuntimeSpec]] = {}
    labels: dict[str, str] = {}
    for spec in supported_repos().values():
        groups.setdefault(spec.group, []).append(spec)
        labels[spec.group] = spec.group_label

    ordered_groups = [
        "microblogging",
        "forum",
        "photo_sharing",
        "hpc",
        "agent_plugins",
        "frontend_plugins",
        "backend_settings",
    ]
    return [
        (group_key, labels[group_key], tuple(groups.get(group_key, [])))
        for group_key in ordered_groups
        if group_key in groups
    ]


def _normalize_repository_reference(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = raw.removesuffix(".git").rstrip("/")
    if raw.startswith("git@github.com:"):
        raw = "https://github.com/" + raw.split("git@github.com:", 1)[1]
    elif raw.startswith("ssh://git@github.com/"):
        raw = "https://github.com/" + raw.split("ssh://git@github.com/", 1)[1]
    return raw.rstrip("/")


def _normalize_plugin_info(repo_dir: Path, payload: dict) -> dict:
    authors = payload.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    elif not isinstance(authors, list):
        authors = []

    repository_url = str(
        payload.get("repository_url")
        or payload.get("repository url")
        or f"https://github.com/YSocialTwin/{repo_dir.name}"
    ).strip()

    return {
        "plugin_name": str(payload.get("plugin_name") or repo_dir.name).strip(),
        "category": str(payload.get("category") or "Agent Extensions").strip(),
        "group": str(payload.get("group") or "Agent Plugins").strip(),
        "description": str(payload.get("description") or "").strip(),
        "authors": [str(author).strip() for author in authors if str(author).strip()],
        "repository_url": repository_url,
    }


def scan_plugin_info_files() -> list[dict]:
    plugins: list[dict] = []
    if not EXTERNAL_DIR.exists():
        return plugins

    for repo_dir in sorted(EXTERNAL_DIR.iterdir()):
        if not repo_dir.is_dir():
            continue
        info_path = repo_dir / PLUGIN_INFO_RELATIVE_PATH
        if not info_path.exists():
            continue
        try:
            payload = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        plugins.append(_normalize_plugin_info(repo_dir, payload))

    plugin_repo = EXTERNAL_DIR / "y_agents_plugins"
    if plugin_repo.is_dir() and not any(
        plugin.get("plugin_name") == "y_agents_plugins" for plugin in plugins
    ):
        registry_path = None
        for relative_path in (
            PLUGIN_REGISTRY_RELATIVE_PATH,
            *LEGACY_PLUGIN_REGISTRY_PATHS,
        ):
            candidate = plugin_repo / relative_path
            if candidate.exists():
                registry_path = candidate
                break
        if registry_path is not None:
            plugins.append(
                _normalize_plugin_info(
                    plugin_repo,
                    {
                        "plugin_name": "y_agents_plugins",
                        "category": "Agent Extensions",
                        "group": "Agent Plugins",
                        "description": "Ready-made special-purpose agents (moderator, propaganda, comic relief, stress testing and more) to add to an experiment.",
                        "authors": ["YSocialTwin"],
                        "repository_url": "https://github.com/YSocialTwin/y_agents_plugins",
                    },
                )
            )
    return plugins


def sync_plugins_index() -> list[dict]:
    plugins = scan_plugin_info_files()
    PLUGINS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLUGINS_INDEX_PATH.write_text(
        json.dumps({"plugins": plugins}, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return plugins


def load_plugins_index(refresh: bool = False) -> list[dict]:
    if refresh or not PLUGINS_INDEX_PATH.exists():
        return sync_plugins_index()

    try:
        payload = json.loads(PLUGINS_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sync_plugins_index()

    if isinstance(payload, dict):
        plugins = payload.get("plugins", [])
    elif isinstance(payload, list):
        plugins = payload
    else:
        return sync_plugins_index()

    normalized = []
    for item in plugins:
        if not isinstance(item, dict):
            continue
        repo_name = re.sub(
            r"[^a-zA-Z0-9._-]+", "_", str(item.get("plugin_name") or "plugin")
        )
        normalized.append(_normalize_plugin_info(EXTERNAL_DIR / repo_name, item))
    return normalized


def plugin_metadata_for_runtime(
    spec: ExternalRuntimeSpec, plugins_index: list[dict] | None = None
) -> dict | None:
    plugins = plugins_index if plugins_index is not None else load_plugins_index()
    match_keys = {
        _normalize_repository_reference(spec.repo_url),
        _normalize_repository_reference(f"https://github.com/{spec.github_repo}"),
        spec.path.name.lower(),
        spec.label.lower(),
    }

    for plugin in plugins:
        plugin_name = str(plugin.get("plugin_name") or "").strip().lower()
        repository_url = _normalize_repository_reference(plugin.get("repository_url"))
        if repository_url in match_keys or plugin_name in match_keys:
            return plugin
    return None


# --- repositories that were private and became public -----------------------
# ``is_private`` in the specs below is only the *initial* classification. A
# repository that GitHub reports as public (anonymous request) is treated as
# public everywhere, so it shows up for every admin without editing the
# registry, the installer or the visibility configuration.
_PUBLIC_RECHECK_SECONDS = 900.0
_PUBLIC_STATE: dict[str, tuple[float, bool]] = {}  # key -> (checked_at, is_public)
_PUBLIC_LOCK = threading.Lock()
_PUBLIC_LOADED = False


def _public_state_path() -> Path:
    return EXTERNAL_DIR / "repo_visibility.json"


def _load_public_state() -> None:
    """Read the last known state from disk once (survives restarts)."""
    global _PUBLIC_LOADED
    with _PUBLIC_LOCK:
        if _PUBLIC_LOADED:
            return
        _PUBLIC_LOADED = True
        try:
            payload = json.loads(_public_state_path().read_text(encoding="utf-8"))
            for key, item in payload.items():
                _PUBLIC_STATE.setdefault(
                    str(key), (float(item["checked_at"]), bool(item["public"]))
                )
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass


def _save_public_state() -> None:
    try:
        path = _public_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            key: {"checked_at": at, "public": public}
            for key, (at, public) in _PUBLIC_STATE.items()
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def repo_is_public(spec: "ExternalRuntimeSpec") -> bool:
    """Last known answer to "is this repository public on GitHub?" (no network)."""
    _load_public_state()
    with _PUBLIC_LOCK:
        item = _PUBLIC_STATE.get(spec.key)
    return bool(item and item[1])


def _probe_public(github_repo: str, timeout: float) -> bool | None:
    """True/False when GitHub answers clearly, None when unknown (offline, rate limit)."""
    import requests

    try:
        response = requests.get(
            f"https://api.github.com/repos/{github_repo}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
        )
    except requests.RequestException:
        return None
    if response.status_code == 200:
        try:
            return response.json().get("private") is False
        except ValueError:
            return None
    if response.status_code == 404:
        return False  # private (anonymous request) or not existing
    return None


def refresh_public_repos(*, force: bool = False, timeout: float = 3.0) -> None:
    """Re-check, in parallel, the repositories still classified as private.

    Anonymous requests only, so a repository the user can reach with a token
    is not mistaken for a public one. Failures keep the previous answer.
    """
    try:
        from flask import current_app, has_app_context

        if has_app_context() and current_app.config.get("TESTING"):
            return
    except RuntimeError:
        pass
    _load_public_state()
    now = time.time()
    due = []
    for spec in supported_repos().values():
        if not spec.is_private:
            continue
        with _PUBLIC_LOCK:
            item = _PUBLIC_STATE.get(spec.key)
        if force or item is None or now - item[0] > _PUBLIC_RECHECK_SECONDS:
            due.append(spec)
    if not due:
        return
    with ThreadPoolExecutor(max_workers=len(due)) as pool:
        answers = list(pool.map(lambda sp: _probe_public(sp.github_repo, timeout), due))
    changed = False
    with _PUBLIC_LOCK:
        for spec, answer in zip(due, answers):
            if answer is None:
                continue
            _PUBLIC_STATE[spec.key] = (now, answer)
            changed = True
    if changed:
        _save_public_state()


def _visibility_overrides() -> dict[str, tuple[str, ...] | str]:
    raw = os.getenv("YSOCIAL_PLUGIN_VISIBILITY", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    result: dict[str, tuple[str, ...] | str] = {}
    for repo_key, value in payload.items():
        if value == "*":
            result[str(repo_key)] = "*"
            continue
        if isinstance(value, list):
            usernames = tuple(str(item).strip() for item in value if str(item).strip())
            result[str(repo_key)] = usernames
    return result


def _development_mode_enabled() -> bool:
    """Whether the running app was started with ``--development``
    (``y_social.py``), i.e. ``app.config["DEVELOPMENT_MODE"]`` is truthy.

    Reads the live Flask app config rather than an env var so the one
    CLI flag at startup is the single source of truth (see
    ``y_social.py::start_app``'s own docstring comment next to where it
    sets this key). Defensive about app context: some callers of
    ``runtime_visible_to_user`` (notably this module's own unit tests)
    call it with no Flask app pushed at all, so this reads as ``False``
    there instead of raising -- the same, pre-existing behaviour those
    callers already expect.
    """
    try:
        from flask import current_app, has_app_context

        if not has_app_context():
            return False
        return bool(current_app.config.get("DEVELOPMENT_MODE", False))
    except RuntimeError:
        return False


def runtime_visible_to_user(spec: ExternalRuntimeSpec, admin_user) -> bool:
    if admin_user is None:
        return False
    if not spec.is_private:
        return True
    if repo_is_public(spec):
        return True  # was private, GitHub now reports it public
    if _development_mode_enabled():
        # User-reported requirement: a "development" startup flag should
        # unlock every plugin repository marked private in this registry
        # for listing/installing/enabling -- when the flag is absent,
        # behaviour below is completely unchanged (explicit allow-list
        # gating only; plain admin role is no longer enough on its own,
        # see the comment at this function's final `return False`).
        return True

    overrides = _visibility_overrides().get(spec.key)
    if overrides == "*":
        return True
    if isinstance(overrides, tuple):
        return admin_user.username in overrides

    if spec.visible_to_usernames:
        return admin_user.username in spec.visible_to_usernames

    # User-reported gap (2026-10-08): "when the new flag -e is not
    # specified private plugins that are already installed are still
    # visible". Root cause -- every repo actually marked private in this
    # registry (photo_sharing, reactive_agents, frontend_adds_on,
    # scenario_design) ships with an empty visible_to_usernames and no
    # override, so every request here used to fall through to "any admin
    # sees it", which defeated --development entirely for the normal
    # case of an admin testing without the flag. A private repo with no
    # explicit allow-list is now hidden unless --development is on;
    # admin role alone is no longer a visibility bypass.
    return False


def runtime_installed_and_visible(repo_key: str, admin_user) -> bool:
    """True iff *repo_key* is both installed on disk AND visible to
    *admin_user* (``runtime_visible_to_user``).

    User-reported gap (2026-10-08): the Plugins catalog page (and its
    install/enable/logs actions) all gate on ``runtime_visible_to_user``,
    but several OTHER admin pages that surface a plugin's feature once
    it's installed (which simulator types to offer when creating an
    experiment, the frontend-plugin settings list, agent-plugin
    features) only ever checked "is this repo's path present on disk" --
    a bare ``runtime_spec(repo_key).path.exists()`` -- with no privacy
    gate at all. That meant a private plugin already installed on this
    machine stayed fully usable through those other pages even for an
    admin who'd never pass ``runtime_visible_to_user``'s checks, and
    even with ``--development`` off. Callers that decide whether to
    surface an installed plugin's feature to the current admin should
    use this instead of a bare path check.
    """
    try:
        spec = runtime_spec(repo_key)
    except KeyError:
        return False
    if not spec.path.exists():
        return False
    return runtime_visible_to_user(spec, admin_user)
