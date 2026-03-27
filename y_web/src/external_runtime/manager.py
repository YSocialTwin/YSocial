"""Controlled install/update operations for external runtime repositories."""

from __future__ import annotations

import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from y_web import BASE_DIR

from .registry import grouped_runtime_specs, runtime_spec

LOG_DIR = Path(BASE_DIR) / "logs"
LOG_FILE = LOG_DIR / "external_runtime_operations.log"
_GITHUB_TIMEOUT = 6


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
    github_repo: str
    default_branch: str
    installed: bool
    exists: bool
    git_managed: bool
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
    available_releases: list[dict[str, Any]]
    latest_release_tag: str | None
    releases_enabled: bool
    release_error: str | None
    path_kind: str
    python_executable: str
    is_private: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_external_runtime_action(
    repo_key: str,
    action: str,
    actor: str,
    branch: str | None,
    success: bool,
    output: str,
) -> None:
    _ensure_log_dir()
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_key": repo_key,
        "action": action,
        "actor": actor,
        "branch": branch,
        "success": success,
        "output": output[-40000:],
    }
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def read_external_runtime_logs(
    limit: int = 200,
    repo_key: str | None = None,
) -> list[dict[str, Any]]:
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


def _github_token(explicit_token: str | None = None) -> str | None:
    token = explicit_token or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    token = (token or "").strip()
    return token or None


def _github_api_headers(explicit_token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "YSocial-External-Runtime-Manager",
    }
    token = _github_token(explicit_token)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_download_headers(explicit_token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/octet-stream",
        "User-Agent": "YSocial-External-Runtime-Manager",
    }
    token = _github_token(explicit_token)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _run_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> str:
    merged_env = os.environ.copy()
    merged_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    merged_env.setdefault("GIT_ASKPASS", "echo")
    if env:
        merged_env.update(env)

    try:
        process = subprocess.run(
            command,
            cwd=str(cwd),
            env=merged_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        cmd = " ".join(shlex.quote(part) for part in command)
        raise ExternalRuntimeError(
            f"Command timed out after {timeout}s ({cmd})"
        ) from exc

    output = (process.stdout or "") + (process.stderr or "")
    if process.returncode != 0:
        cmd = " ".join(shlex.quote(part) for part in command)
        raise ExternalRuntimeError(f"Command failed ({cmd})\n{output.strip()}")
    return output.strip()


def _safe_git(path: Path, args: list[str]) -> str:
    return _run_command(["git", *args], cwd=path)


def _is_git_worktree(path: Path) -> bool:
    try:
        _safe_git(path, ["rev-parse", "--is-inside-work-tree"])
        return True
    except Exception:
        return False


def _resolve_branch(spec, selected_branch: str | None) -> str:
    branch = (selected_branch or spec.default_branch).strip()
    return branch or spec.default_branch


def _branch_list_for_repo(spec, git_managed: bool) -> list[str]:
    branches: set[str] = set()
    try:
        if git_managed:
            local_output = _safe_git(spec.path, ["branch", "--format=%(refname:short)"])
            for line in local_output.splitlines():
                if line.strip():
                    branches.add(line.strip())

            remote_output = _safe_git(
                spec.path,
                ["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"],
            )
            for line in remote_output.splitlines():
                branch_name = line.strip().removeprefix("origin/")
                if branch_name and branch_name != "HEAD":
                    branches.add(branch_name)
    except Exception:
        pass

    branches.add(spec.default_branch)
    return sorted(branches)


def _ahead_behind(path: Path) -> tuple[int | None, int | None, str | None]:
    try:
        tracking = _safe_git(
            path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
        ).strip()
    except Exception:
        return None, None, None

    counts = (
        _safe_git(path, ["rev-list", "--left-right", "--count", f"{tracking}...HEAD"])
        .strip()
        .split()
    )
    if len(counts) != 2:
        return None, None, tracking
    behind = int(counts[0])
    ahead = int(counts[1])
    return ahead, behind, tracking


def _dependency_files_ready(spec) -> bool:
    if not spec.path.exists():
        return False
    if not spec.install_commands:
        return True
    for command in spec.install_commands:
        if "-r" in command:
            req_path = spec.path / command[command.index("-r") + 1]
            if not req_path.exists():
                return False
    return True


def _validate_prereqs(spec) -> bool:
    if not spec.path.exists():
        return False
    return all((spec.path / entry).exists() for entry in spec.validate_entrypoints)


def _github_api_request(url: str, github_token: str | None = None) -> requests.Response:
    try:
        response = requests.get(
            url,
            headers=_github_api_headers(github_token),
            timeout=_GITHUB_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ExternalRuntimeError(f"GitHub request failed: {exc}") from exc
    return response


def _release_summary(payload: dict[str, Any]) -> dict[str, Any]:
    name = (payload.get("name") or payload.get("tag_name") or "").strip()
    tag = (payload.get("tag_name") or "").strip()
    return {
        "tag": tag,
        "name": name or tag,
        "published_at": payload.get("published_at"),
        "prerelease": bool(payload.get("prerelease")),
        "draft": bool(payload.get("draft")),
        "zipball_url": payload.get("zipball_url"),
        "tarball_url": payload.get("tarball_url"),
    }


def _list_releases(
    spec, github_token: str | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    url = f"https://api.github.com/repos/{spec.github_repo}/releases?per_page=10"
    try:
        response = _github_api_request(url, github_token=github_token)
    except ExternalRuntimeError as exc:
        return [], str(exc)
    if response.status_code == 404:
        return [], None
    if response.status_code == 403:
        return [], "GitHub API access denied or rate limited."
    if response.status_code >= 400:
        return [], f"GitHub release lookup failed ({response.status_code})."

    try:
        payload = response.json()
    except ValueError:
        return [], "GitHub release response was not valid JSON."
    if not isinstance(payload, list):
        return [], "GitHub release response was not a list."

    releases = [_release_summary(item) for item in payload if isinstance(item, dict)]
    releases = [item for item in releases if item.get("tag") and not item.get("draft")]
    return releases, None


def _find_release(
    spec, release_tag: str | None, github_token: str | None = None
) -> dict[str, Any]:
    releases, error = _list_releases(spec, github_token=github_token)
    if error:
        raise ExternalRuntimeError(error)
    if not releases:
        raise ExternalRuntimeError(
            f"No GitHub releases are available for {spec.label}."
        )

    desired_tag = (release_tag or releases[0]["tag"]).strip()
    for release in releases:
        if release["tag"] == desired_tag:
            return release
    raise ExternalRuntimeError(f"Release {desired_tag} was not found for {spec.label}.")


def _extract_archive_bytes(archive_bytes: bytes, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="ysocial-runtime-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        extracted_root = temp_dir / "extracted"
        extracted_root.mkdir(parents=True, exist_ok=True)

        if zipfile.is_zipfile(io.BytesIO(archive_bytes)):
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                archive.extractall(extracted_root)
        else:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as archive:
                archive.extractall(extracted_root)

        top_entries = [item for item in extracted_root.iterdir()]
        source_root = extracted_root
        if len(top_entries) == 1 and top_entries[0].is_dir():
            source_root = top_entries[0]

        destination.mkdir(parents=True, exist_ok=False)
        for item in source_root.iterdir():
            shutil.move(str(item), str(destination / item.name))


def _download_release_archive(
    spec, release: dict[str, Any], github_token: str | None = None
) -> bytes:
    url = release.get("zipball_url") or release.get("tarball_url")
    if not url:
        raise ExternalRuntimeError(
            f"Release {release.get('tag')} does not expose a downloadable archive."
        )

    try:
        response = requests.get(
            url,
            headers=_github_download_headers(github_token),
            timeout=60,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise ExternalRuntimeError(f"Release download failed: {exc}") from exc

    if response.status_code == 404:
        raise ExternalRuntimeError("Release archive not found or not accessible.")
    if response.status_code == 403:
        raise ExternalRuntimeError("GitHub denied access to the release archive.")
    if response.status_code >= 400:
        raise ExternalRuntimeError(f"Release download failed ({response.status_code}).")
    return response.content


def get_runtime_status(repo_key: str, github_token: str | None = None) -> RuntimeStatus:
    spec = runtime_spec(repo_key)
    path = spec.path
    exists = path.exists()
    git_managed = exists and _is_git_worktree(path)
    installed = exists

    current_branch = None
    current_commit = None
    dirty = False
    tracking_branch = None
    ahead = None
    behind = None

    if git_managed:
        try:
            current_branch = (
                _safe_git(path, ["branch", "--show-current"]).strip() or None
            )
        except Exception:
            current_branch = None
        try:
            current_commit = (
                _safe_git(path, ["rev-parse", "--short", "HEAD"]).strip() or None
            )
        except Exception:
            current_commit = None
        try:
            dirty = bool(_safe_git(path, ["status", "--porcelain"]).strip())
        except Exception:
            dirty = False
        ahead, behind, tracking_branch = _ahead_behind(path)

    releases, release_error = _list_releases(spec, github_token=github_token)
    branches = _branch_list_for_repo(spec, git_managed)
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
        github_repo=spec.github_repo,
        default_branch=spec.default_branch,
        installed=installed,
        exists=exists,
        git_managed=git_managed,
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
        available_releases=releases,
        latest_release_tag=releases[0]["tag"] if releases else None,
        releases_enabled=bool(releases),
        release_error=release_error,
        path_kind=path_kind,
        python_executable=sys.executable,
        is_private=spec.is_private,
    )


def get_grouped_runtime_status(github_token: str | None = None) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group_key, group_label, specs in grouped_runtime_specs():
        groups.append(
            {
                "group": group_key,
                "label": group_label,
                "repos": [
                    get_runtime_status(spec.key, github_token=github_token).to_dict()
                    for spec in specs
                ],
            }
        )
    return groups


def download_runtime_release(
    repo_key: str,
    release_tag: str | None,
    actor: str,
    github_token: str | None = None,
) -> None:
    spec = runtime_spec(repo_key)
    if spec.path.exists():
        raise ExternalRuntimeError(f"{spec.label} already exists at {spec.path}")

    spec.path.parent.mkdir(parents=True, exist_ok=True)
    release = _find_release(spec, release_tag, github_token=github_token)
    archive_bytes = _download_release_archive(spec, release, github_token=github_token)
    try:
        _extract_archive_bytes(archive_bytes, spec.path)
    except Exception as exc:
        if spec.path.exists():
            shutil.rmtree(spec.path, ignore_errors=True)
        raise ExternalRuntimeError(f"Release extraction failed: {exc}") from exc

    output = "\n".join(
        [
            f"Installed {spec.label} from GitHub release {release['tag']}.",
            f"Repository: {spec.github_repo}",
            f"Destination: {spec.path}",
        ]
    )
    log_external_runtime_action(
        repo_key, "download_release", actor, release["tag"], True, output
    )


def clone_runtime_repo(repo_key: str, branch: str | None, actor: str) -> None:
    spec = runtime_spec(repo_key)
    branch_name = _resolve_branch(spec, branch)
    if spec.path.exists():
        raise ExternalRuntimeError(f"{spec.label} already exists at {spec.path}")
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    output = _run_command(
        ["git", "clone", "--branch", branch_name, spec.repo_url, str(spec.path)],
        cwd=spec.path.parent,
    )
    log_external_runtime_action(repo_key, "clone", actor, branch_name, True, output)


def fetch_runtime_repo(repo_key: str, branch: str | None, actor: str) -> None:
    spec = runtime_spec(repo_key)
    status = get_runtime_status(repo_key)
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")
    if not status.git_managed:
        raise ExternalRuntimeError(
            f"{spec.label} was installed from a release archive. Use the advanced clone option for git operations."
        )
    branch_name = _resolve_branch(spec, branch)
    output_parts = [
        _normalize_origin_remote(spec),
        _safe_git(spec.path, ["fetch", "origin", branch_name, "--prune"]),
    ]
    output = "\n".join(part for part in output_parts if part)
    log_external_runtime_action(repo_key, "fetch", actor, branch_name, True, output)


def _checkout_branch(path: Path, branch_name: str) -> str:
    local_branches = _safe_git(
        path, ["branch", "--format=%(refname:short)"]
    ).splitlines()
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


def _normalize_origin_remote(spec) -> str:
    current_origin = None
    try:
        current_origin = _safe_git(spec.path, ["remote", "get-url", "origin"]).strip()
    except Exception:
        current_origin = None

    if current_origin == spec.repo_url:
        return f"Origin already set to {spec.repo_url}"

    if current_origin:
        _safe_git(spec.path, ["remote", "set-url", "origin", spec.repo_url])
        return f"Updated origin remote from {current_origin} to {spec.repo_url}"

    _safe_git(spec.path, ["remote", "add", "origin", spec.repo_url])
    return f"Added origin remote {spec.repo_url}"


def update_runtime_repo(repo_key: str, branch: str | None, actor: str) -> None:
    spec = runtime_spec(repo_key)
    status = get_runtime_status(repo_key)
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")
    if not status.git_managed:
        raise ExternalRuntimeError(
            f"{spec.label} was installed from a release archive. Delete it and use the advanced clone option if you need branch-based updates."
        )
    if status.dirty:
        raise ExternalRuntimeError(
            f"{spec.label} has local modifications. Clean the worktree before updating."
        )

    branch_name = _resolve_branch(spec, branch)
    output_parts = [
        _normalize_origin_remote(spec),
        _safe_git(spec.path, ["fetch", "origin", branch_name, "--prune"]),
        _checkout_branch(spec.path, branch_name),
        _safe_git(spec.path, ["pull", "--ff-only", "origin", branch_name]),
    ]
    log_external_runtime_action(
        repo_key,
        "update",
        actor,
        branch_name,
        True,
        "\n".join(part for part in output_parts if part),
    )


def install_runtime_dependencies(repo_key: str, actor: str) -> None:
    spec = runtime_spec(repo_key)
    status = get_runtime_status(repo_key)
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")

    output_parts: list[str] = []
    env = os.environ.copy()
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    output_parts.append(f"Using interpreter: {sys.executable}")
    for command in spec.install_commands:
        resolved = [sys.executable if token == "python" else token for token in command]
        output_parts.append(
            _run_command(resolved, cwd=spec.path, env=env, timeout=1800)
        )
    log_external_runtime_action(
        repo_key,
        "install",
        actor,
        None,
        True,
        "\n".join(part for part in output_parts if part),
    )


def validate_runtime_repo(repo_key: str, actor: str) -> str:
    spec = runtime_spec(repo_key)
    status = get_runtime_status(repo_key)
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")
    missing = [
        entry for entry in spec.validate_entrypoints if not (spec.path / entry).exists()
    ]
    if missing:
        raise ExternalRuntimeError(
            f"{spec.label} is missing required files: {', '.join(missing)}"
        )

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


def delete_runtime_repo(repo_key: str, actor: str) -> None:
    spec = runtime_spec(repo_key)
    if not spec.path.exists() and not spec.path.is_symlink():
        raise ExternalRuntimeError(f"{spec.label} is not installed")

    if spec.path.is_symlink():
        link_target = os.readlink(spec.path)
        spec.path.unlink()
        output = f"Removed symlink {spec.path} -> {link_target}"
    elif spec.path.is_dir():
        shutil.rmtree(spec.path)
        output = f"Removed runtime directory {spec.path}"
    else:
        spec.path.unlink()
        output = f"Removed file {spec.path}"

    log_external_runtime_action(repo_key, "delete", actor, None, True, output)
