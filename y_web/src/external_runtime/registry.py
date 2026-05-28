"""Registry of supported external runtime repositories."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_DIR = ROOT / "external"
PLUGINS_INDEX_PATH = EXTERNAL_DIR / "plugins.json"
PLUGIN_INFO_RELATIVE_PATH = Path("meta") / "info.json"
PLUGIN_REGISTRY_RELATIVE_PATH = Path("meta") / "registry.json"
LEGACY_PLUGIN_REGISTRY_PATHS = (
    Path("plugins_exposed") / "agent_types.json",
    Path("plugin_exposed") / "agent_types.json",
)


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


SUPPORTED_EXTERNAL_REPOS: dict[str, ExternalRuntimeSpec] = {
    "microblogging_client": ExternalRuntimeSpec(
        key="microblogging_client",
        group="microblogging",
        group_label="Microblogging",
        category="simulation_runtimes",
        category_label="Simulation Runtimes",
        label="YClient",
        path=EXTERNAL_DIR / "YClient",
        github_repo="YSocialTwin/YClient",
        repo_url="git@github.com:YSocialTwin/YClient.git",
        default_branch="main",
        install_commands=(
            ("python", "-m", "pip", "install", "-r", "requirements_client.txt"),
        ),
        validate_entrypoints=("y_client", "requirements_client.txt"),
        validate_import="y_client",
        is_private=False,
    ),
    "microblogging_server": ExternalRuntimeSpec(
        key="microblogging_server",
        group="microblogging",
        group_label="Microblogging",
        category="simulation_runtimes",
        category_label="Simulation Runtimes",
        label="YServer",
        path=EXTERNAL_DIR / "YServer",
        github_repo="YSocialTwin/YServer",
        repo_url="git@github.com:YSocialTwin/YServer.git",
        default_branch="main",
        install_commands=(
            ("python", "-m", "pip", "install", "-r", "requirements_server.txt"),
        ),
        validate_entrypoints=("y_server", "requirements_server.txt"),
        validate_import="y_server",
        is_private=False,
    ),
    "forum_client": ExternalRuntimeSpec(
        key="forum_client",
        group="forum",
        group_label="Forum",
        category="simulation_runtimes",
        category_label="Simulation Runtimes",
        label="YClientReddit",
        path=EXTERNAL_DIR / "YClientReddit",
        github_repo="YSocialTwin/YClientReddit",
        repo_url="git@github.com:YSocialTwin/YClientReddit.git",
        default_branch="main",
        install_commands=(
            ("python", "-m", "pip", "install", "-r", "requirements_client.txt"),
        ),
        validate_entrypoints=("y_client", "requirements_client.txt"),
        validate_import="y_client",
    ),
    "forum_server": ExternalRuntimeSpec(
        key="forum_server",
        group="forum",
        group_label="Forum",
        category="simulation_runtimes",
        category_label="Simulation Runtimes",
        label="YServerReddit",
        path=EXTERNAL_DIR / "YServerReddit",
        github_repo="YSocialTwin/YServerReddit",
        repo_url="git@github.com:YSocialTwin/YServerReddit.git",
        default_branch="main",
        install_commands=(
            ("python", "-m", "pip", "install", "-r", "requirements_server.txt"),
        ),
        validate_entrypoints=("y_server", "requirements_server.txt"),
        validate_import="y_server",
    ),
    "hpc_simulator": ExternalRuntimeSpec(
        key="hpc_simulator",
        group="hpc",
        group_label="HPC",
        category="simulation_runtimes",
        category_label="Simulation Runtimes",
        label="YSimulator",
        path=EXTERNAL_DIR / "YSimulator",
        github_repo="YSocialTwin/YSimulator",
        repo_url="git@github.com:YSocialTwin/YSimulator.git",
        default_branch="main",
        install_commands=(
            ("python", "-m", "pip", "install", "-r", "requirements.txt"),
        ),
        validate_entrypoints=("run_server.py", "run_client.py"),
        validate_import="YSimulator",
    ),
    "agent_plugins": ExternalRuntimeSpec(
        key="agent_plugins",
        group="agent_plugins",
        group_label="Agent Plugins",
        category="agent_extensions",
        category_label="Agent Extensions",
        label="y_agents_plugins",
        path=EXTERNAL_DIR / "y_agents_plugins",
        github_repo="YSocialTwin/y_agents_plugins",
        repo_url="git@github.com:YSocialTwin/y_agents_plugins.git",
        default_branch="main",
        install_commands=(),
        validate_entrypoints=(),
        validate_import=None,
    ),
}


def runtime_spec(repo_key: str) -> ExternalRuntimeSpec:
    return SUPPORTED_EXTERNAL_REPOS[repo_key]


def grouped_runtime_specs() -> list[tuple[str, str, Sequence[ExternalRuntimeSpec]]]:
    groups: dict[str, list[ExternalRuntimeSpec]] = {}
    labels: dict[str, str] = {}
    for spec in SUPPORTED_EXTERNAL_REPOS.values():
        groups.setdefault(spec.group, []).append(spec)
        labels[spec.group] = spec.group_label

    ordered_groups = ["microblogging", "forum", "hpc", "agent_plugins"]
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
                        "description": "Plugin-defined ad hoc agent families for YSocial experiments.",
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


def runtime_visible_to_user(spec: ExternalRuntimeSpec, admin_user) -> bool:
    if admin_user is None:
        return False
    if not spec.is_private:
        return True

    overrides = _visibility_overrides().get(spec.key)
    if overrides == "*":
        return True
    if isinstance(overrides, tuple):
        return admin_user.username in overrides

    if spec.visible_to_usernames:
        return admin_user.username in spec.visible_to_usernames

    return getattr(admin_user, "role", None) == "admin"
