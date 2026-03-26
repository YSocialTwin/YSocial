"""Controlled git/install/validate operations for external runtimes."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from y_web import BASE_DIR

from .registry import grouped_runtime_specs, runtime_spec

LOG_DIR = Path(BASE_DIR) / "logs"
LOG_FILE = LOG_DIR / "external_runtime_operations.log"


class ExternalRuntimeError(RuntimeError):
    """Raised when an external runtime management action cannot complete."""


@dataclass
class RuntimeStatus:
    key: str
    label: str
    group: str
    group_label: str
    path: str
    repo_url: str
    default_branch: str
    installed: bool
    exists: bool
    is_symlink: bool
    current_branch: str | None
    current_commit: str | None
    tracking_branch: str | None
    ahead: int | None
    behind: int | None
    dirty: bool
    dependency_files_ready: bool
    validation_ready: bool
    available_branches: list[str]
    path_kind: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_external_runtime_action(repo_key: str, action: str, actor: str, branch: str | None, success: bool, output: str) -> None:
    _ensure_log_dir()
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_key": repo_key,
        "action": action,
        "actor": actor,
        "branch": branch,
        "success": success,
        "output": output[-20000:],
    }
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def read_external_runtime_logs(limit: int = 200, repo_key: str | None = None) -> list[dict[str, Any]]:
    if not LOG_FILE.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if repo_key and payload.get("repo_key") != repo_key:
            continue
        records.append(payload)
    return records[::-1]


def _run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    process = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (process.stdout or "") + (process.stderr or "")
    if process.returncode != 0:
        cmd = " ".join(shlex.quote(part) for part in command)
        raise ExternalRuntimeError(f"Command failed ({cmd})\n{output.strip()}")
    return output.strip()


def _safe_git(path: Path, args: list[str]) -> str:
    return _run_command(["git", *args], cwd=path)


def _git_available(path: Path) -> bool:
    try:
        _safe_git(path, ["rev-parse", "--is-inside-work-tree"])
        return True
    except Exception:
        return False


def _resolve_branch(spec, selected_branch: str | None) -> str:
    branch = (selected_branch or spec.default_branch).strip()
    return branch or spec.default_branch


def _branch_list_for_repo(spec, installed: bool) -> list[str]:
    branches: set[str] = set()
    try:
        if installed and _git_available(spec.path):
            local_output = _safe_git(spec.path, ["branch", "--format=%(refname:short)"])
            for line in local_output.splitlines():
                if line.strip():
                    branches.add(line.strip())

            remote_output = _safe_git(spec.path, ["ls-remote", "--heads", "origin"])
        else:
            parent = spec.path.parent if spec.path.parent.exists() else Path.cwd()
            remote_output = _run_command(["git", "ls-remote", "--heads", spec.repo_url], cwd=parent)

        for line in remote_output.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                branches.add(parts[1].removeprefix("refs/heads/"))
    except Exception:
        pass

    branches.add(spec.default_branch)
    return sorted(branches)


def _ahead_behind(path: Path) -> tuple[int | None, int | None, str | None]:
    try:
        tracking = _safe_git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]).strip()
    except Exception:
        return None, None, None

    counts = _safe_git(path, ["rev-list", "--left-right", "--count", f"{tracking}...HEAD"]).strip().split()
    if len(counts) != 2:
        return None, None, tracking
    behind = int(counts[0])
    ahead = int(counts[1])
    return ahead, behind, tracking


def _dependency_files_ready(spec) -> bool:
    if not spec.install_commands:
        return True
    for command in spec.install_commands:
        if "-r" in command:
            req_path = spec.path / command[command.index("-r") + 1]
            if not req_path.exists():
                return False
    return True


def _validate_prereqs(spec) -> bool:
    return all((spec.path / entry).exists() for entry in spec.validate_entrypoints)


def get_runtime_status(repo_key: str) -> RuntimeStatus:
    spec = runtime_spec(repo_key)
    path = spec.path
    exists = path.exists()
    installed = exists and _git_available(path)
    current_branch = None
    current_commit = None
    dirty = False
    tracking_branch = None
    ahead = None
    behind = None

    if installed:
        try:
            current_branch = _safe_git(path, ["branch", "--show-current"]).strip() or None
        except Exception:
            current_branch = None
        try:
            current_commit = _safe_git(path, ["rev-parse", "--short", "HEAD"]).strip() or None
        except Exception:
            current_commit = None
        try:
            dirty = bool(_safe_git(path, ["status", "--porcelain"]).strip())
        except Exception:
            dirty = False
        ahead, behind, tracking_branch = _ahead_behind(path)

    branches = _branch_list_for_repo(spec, installed)
    path_kind = "missing"
    if exists:
        path_kind = "symlink" if path.is_symlink() else "directory"

    return RuntimeStatus(
        key=spec.key,
        label=spec.label,
        group=spec.group,
        group_label=spec.group_label,
        path=str(path),
        repo_url=spec.repo_url,
        default_branch=spec.default_branch,
        installed=installed,
        exists=exists,
        is_symlink=path.is_symlink(),
        current_branch=current_branch,
        current_commit=current_commit,
        tracking_branch=tracking_branch,
        ahead=ahead,
        behind=behind,
        dirty=dirty,
        dependency_files_ready=_dependency_files_ready(spec),
        validation_ready=_validate_prereqs(spec),
        available_branches=branches,
        path_kind=path_kind,
    )


def get_grouped_runtime_status() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group_key, group_label, specs in grouped_runtime_specs():
        groups.append(
            {
                "group": group_key,
                "label": group_label,
                "repos": [get_runtime_status(spec.key).to_dict() for spec in specs],
            }
        )
    return groups


def clone_runtime_repo(repo_key: str, branch: str | None, actor: str) -> None:
    spec = runtime_spec(repo_key)
    branch_name = _resolve_branch(spec, branch)
    if spec.path.exists():
        raise ExternalRuntimeError(f"{spec.label} already exists at {spec.path}")
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    output = _run_command(["git", "clone", "--branch", branch_name, spec.repo_url, str(spec.path)], cwd=spec.path.parent)
    log_external_runtime_action(repo_key, "clone", actor, branch_name, True, output)


def fetch_runtime_repo(repo_key: str, branch: str | None, actor: str) -> None:
    spec = runtime_spec(repo_key)
    status = get_runtime_status(repo_key)
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")
    branch_name = _resolve_branch(spec, branch)
    output = _safe_git(spec.path, ["fetch", "origin", branch_name, "--prune"])
    log_external_runtime_action(repo_key, "fetch", actor, branch_name, True, output)


def _checkout_branch(path: Path, branch_name: str) -> str:
    local_branches = _safe_git(path, ["branch", "--format=%(refname:short)"]).splitlines()
    if branch_name in [item.strip() for item in local_branches]:
        return _safe_git(path, ["checkout", branch_name])

    remote_branches = _safe_git(path, ["ls-remote", "--heads", "origin"])
    remote_branch_names = {
        line.split()[1].removeprefix("refs/heads/")
        for line in remote_branches.splitlines()
        if len(line.split()) == 2 and line.split()[1].startswith("refs/heads/")
    }
    if branch_name not in remote_branch_names:
        raise ExternalRuntimeError(f"Branch {branch_name} was not found on origin")
    return _safe_git(path, ["checkout", "-B", branch_name, f"origin/{branch_name}"])


def update_runtime_repo(repo_key: str, branch: str | None, actor: str) -> None:
    spec = runtime_spec(repo_key)
    status = get_runtime_status(repo_key)
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")
    if status.dirty:
        raise ExternalRuntimeError(f"{spec.label} has local modifications. Clean the worktree before updating.")

    branch_name = _resolve_branch(spec, branch)
    output_parts = [
        _safe_git(spec.path, ["fetch", "origin", branch_name, "--prune"]),
        _checkout_branch(spec.path, branch_name),
        _safe_git(spec.path, ["pull", "--ff-only", "origin", branch_name]),
    ]
    log_external_runtime_action(repo_key, "update", actor, branch_name, True, "\n".join(part for part in output_parts if part))


def install_runtime_dependencies(repo_key: str, actor: str) -> None:
    spec = runtime_spec(repo_key)
    status = get_runtime_status(repo_key)
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")
    output_parts: list[str] = []
    env = os.environ.copy()
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    for command in spec.install_commands:
        resolved = [sys.executable if token == "python" else token for token in command]
        output_parts.append(_run_command(resolved, cwd=spec.path, env=env))
    log_external_runtime_action(repo_key, "install", actor, None, True, "\n".join(part for part in output_parts if part))


def validate_runtime_repo(repo_key: str, actor: str) -> str:
    spec = runtime_spec(repo_key)
    status = get_runtime_status(repo_key)
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")
    missing = [entry for entry in spec.validate_entrypoints if not (spec.path / entry).exists()]
    if missing:
        raise ExternalRuntimeError(f"{spec.label} is missing required files: {', '.join(missing)}")

    output_parts = [f"Required files present: {', '.join(spec.validate_entrypoints)}"]
    if spec.validate_import:
        script = (
            "import sys; "
            f"sys.path.insert(0, {spec.path.as_posix()!r}); "
            f"__import__({spec.validate_import!r}); "
            f"print('Imported {spec.validate_import}')"
        )
        output_parts.append(_run_command([sys.executable, "-c", script], cwd=spec.path))
    output = "\n".join(part for part in output_parts if part)
    log_external_runtime_action(repo_key, "validate", actor, None, True, output)
    return output
