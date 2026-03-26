"""Registry of supported external runtime repositories."""

from __future__ import annotations

from dataclasses import dataclass
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
    repo_url: str
    default_branch: str
    install_commands: tuple[tuple[str, ...], ...]
    validate_entrypoints: tuple[str, ...]
    validate_import: str | None = None


SUPPORTED_EXTERNAL_REPOS: dict[str, ExternalRuntimeSpec] = {
    "microblogging_client": ExternalRuntimeSpec(
        key="microblogging_client",
        group="microblogging",
        group_label="Microblogging",
        label="YClient",
        path=EXTERNAL_DIR / "YClient",
        repo_url="git@github.com:YSocialTwin/YClient.git",
        default_branch="main",
        install_commands=(("python", "-m", "pip", "install", "-r", "requirements_client.txt"),),
        validate_entrypoints=("y_client", "requirements_client.txt"),
        validate_import="y_client",
    ),
    "microblogging_server": ExternalRuntimeSpec(
        key="microblogging_server",
        group="microblogging",
        group_label="Microblogging",
        label="YServer",
        path=EXTERNAL_DIR / "YServer",
        repo_url="git@github.com:YSocialTwin/YServer.git",
        default_branch="main",
        install_commands=(("python", "-m", "pip", "install", "-r", "requirements_server.txt"),),
        validate_entrypoints=("y_server", "requirements_server.txt"),
        validate_import="y_server",
    ),
    "forum_client": ExternalRuntimeSpec(
        key="forum_client",
        group="forum",
        group_label="Forum",
        label="YClientReddit",
        path=EXTERNAL_DIR / "YClientReddit",
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
