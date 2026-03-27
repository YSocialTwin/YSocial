"""Registry of supported external runtime repositories."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_DIR = ROOT / "external"


@dataclass(frozen=True)
class ExternalRuntimeSpec:
    key: str
    group: str
    group_label: str
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
        label="YClient",
        path=EXTERNAL_DIR / "YClient",
        github_repo="YSocialTwin/YClient",
        repo_url="git@github.com:YSocialTwin/YClient.git",
        default_branch="main",
        install_commands=(("python", "-m", "pip", "install", "-r", "requirements_client.txt"),),
        validate_entrypoints=("y_client", "requirements_client.txt"),
        validate_import="y_client",
        is_private=False,
    ),
    "microblogging_server": ExternalRuntimeSpec(
        key="microblogging_server",
        group="microblogging",
        group_label="Microblogging",
        label="YServer",
        path=EXTERNAL_DIR / "YServer",
        github_repo="YSocialTwin/YServer",
        repo_url="git@github.com:YSocialTwin/YServer.git",
        default_branch="main",
        install_commands=(("python", "-m", "pip", "install", "-r", "requirements_server.txt"),),
        validate_entrypoints=("y_server", "requirements_server.txt"),
        validate_import="y_server",
        is_private=False,
    ),
    "forum_client": ExternalRuntimeSpec(
        key="forum_client",
        group="forum",
        group_label="Forum",
        label="YClientReddit",
        path=EXTERNAL_DIR / "YClientReddit",
        github_repo="YSocialTwin/YClientReddit",
        repo_url="git@github.com:YSocialTwin/YClientReddit.git",
        default_branch="main",
        install_commands=(("python", "-m", "pip", "install", "-r", "requirements_client.txt"),),
        validate_entrypoints=("y_client", "requirements_client.txt"),
        validate_import="y_client",
    ),
    "forum_server": ExternalRuntimeSpec(
        key="forum_server",
        group="forum",
        group_label="Forum",
        label="YServerReddit",
        path=EXTERNAL_DIR / "YServerReddit",
        github_repo="YSocialTwin/YServerReddit",
        repo_url="git@github.com:YSocialTwin/YServerReddit.git",
        default_branch="main",
        install_commands=(("python", "-m", "pip", "install", "-r", "requirements_server.txt"),),
        validate_entrypoints=("y_server", "requirements_server.txt"),
        validate_import="y_server",
    ),
    "hpc_simulator": ExternalRuntimeSpec(
        key="hpc_simulator",
        group="hpc",
        group_label="HPC",
        label="YSimulator",
        path=EXTERNAL_DIR / "YSimulator",
        github_repo="YSocialTwin/YSimulator",
        repo_url="git@github.com:YSocialTwin/YSimulator.git",
        default_branch="main",
        install_commands=(("python", "-m", "pip", "install", "-r", "requirements.txt"),),
        validate_entrypoints=("run_server.py", "run_client.py"),
        validate_import="YSimulator",
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

    ordered_groups = ["microblogging", "forum", "hpc"]
    return [
        (group_key, labels[group_key], tuple(groups.get(group_key, [])))
        for group_key in ordered_groups
        if group_key in groups
    ]


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
            usernames = tuple(
                str(item).strip()
                for item in value
                if str(item).strip()
            )
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
