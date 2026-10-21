"""Controlled install/update operations for external runtime repositories."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from y_web.src.system.path_utils import get_writable_path

from .registry import grouped_runtime_specs, repo_is_public, runtime_spec

LOG_DIR = Path(get_writable_path()) / "logs"
LOG_FILE = LOG_DIR / "external_runtime_operations.log"
_GITHUB_TIMEOUT = 6

# Short-lived cache of the remote lookups (releases, branches, branch head): the
# plugin pages ask for them on every open and every lookup is a network round trip.
_REMOTE_CACHE: dict[tuple, tuple[float, Any]] = {}
_REMOTE_CACHE_LOCK = threading.Lock()
_REMOTE_TTL_OK = 120.0  # seconds, successful lookup
_RELEASES_TTL_OK = 600.0  # releases change rarely
_REMOTE_TTL_ERR = 30.0  # seconds, failed lookup (avoid repeating slow timeouts)


def clear_remote_cache() -> None:
    """Forget cached remote lookups (call after install/update/delete)."""
    with _REMOTE_CACHE_LOCK:
        _REMOTE_CACHE.clear()


def _remote_cached(kind: str, spec, extra: str, github_token, fn, ttl_ok=None):
    """Return ``fn()`` ((value, error) tuple) cached per repo/token for a short time."""
    key = (kind, spec.github_repo, extra, bool(github_token), hash(github_token or ""))
    now = time.monotonic()
    with _REMOTE_CACHE_LOCK:
        hit = _REMOTE_CACHE.get(key)
        if hit and hit[0] > now:
            return hit[1]
    result = fn()
    ttl = _REMOTE_TTL_ERR if result[1] else (ttl_ok or _REMOTE_TTL_OK)
    with _REMOTE_CACHE_LOCK:
        _REMOTE_CACHE[key] = (now + ttl, result)
    return result


class ExternalRuntimeError(RuntimeError):
    """Raised when an external runtime management action cannot complete."""


def host_git_available() -> bool:
    """True when a *working* ``git`` is on PATH.

    On macOS without the Command Line Tools, ``/usr/bin/git`` is only a shim that
    opens an install dialog; it must not count as git.
    """
    git = shutil.which("git")
    if git is None:
        return False
    if sys.platform == "darwin" and git == "/usr/bin/git":
        try:
            if (
                subprocess.run(
                    ["xcode-select", "-p"], capture_output=True, timeout=5, check=False
                ).returncode
                != 0
            ):
                return False
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        return (
            subprocess.run(
                [git, "--version"], capture_output=True, timeout=10, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def resolve_python_executable() -> str:
    """Return the Python interpreter that matches the active conda/micromamba env."""
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())

    # Managed runtime (uv-built venv set up by the installer): the launcher
    # exports YSOCIAL_PYTHON so plugins install into the interpreter that runs
    # YSocial, never into a system Python.
    managed = os.environ.get("YSOCIAL_PYTHON")
    if managed and Path(managed).exists():
        # No .resolve(): a venv's python is a symlink to the base interpreter, and
        # following it would install plugins into the (externally managed) base.
        return os.path.abspath(managed)

    conda_prefix = os.environ.get("CONDA_PREFIX") or os.environ.get("MAMBA_PREFIX")
    if conda_prefix:
        candidate = Path(conda_prefix).resolve() / "bin" / "python"
        if candidate.exists():
            return str(candidate)

    # Keep the venv path: resolving the symlink would point at the base interpreter.
    return os.path.abspath(sys.executable)


@dataclass
class RuntimeStatus:
    key: str
    label: str
    group: str
    group_label: str
    category: str
    category_label: str
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
    archive_managed: bool = False
    update_available: bool | None = None
    # release-managed installs only (not git, not branch archive)
    release_managed: bool = False
    installed_release_tag: str | None = None
    release_update_available: bool | None = None
    # plugin registry (see catalog.py): who vouches for the plugin
    trust: str = "official"
    source: str = "builtin"
    description: str = ""

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
    # "*/*" like curl/browsers: a zipball/tarball request is redirected to
    # codeload.github.com, which answers 415 to "Accept: application/octet-stream".
    headers = {
        "Accept": "*/*",
        "User-Agent": "YSocial-External-Runtime-Manager",
    }
    token = _github_token(explicit_token)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _git_auth_env(explicit_token: str | None = None) -> dict[str, str]:
    """Environment that lets ``git`` authenticate to github.com with a token.

    The token is passed through git's per-process config (``GIT_CONFIG_*``): it is
    never written to the remote URL, to ``.git/config`` or to the command line, and
    any configured credential helper is bypassed (a missing ``gh`` binary there
    would otherwise make every private clone fail).
    """
    token = _github_token(explicit_token)
    if not token:
        return {}
    basic = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    return {
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "",
        "GIT_CONFIG_KEY_1": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_1": f"AUTHORIZATION: basic {basic}",
    }


_GIT_AUTH_FAILURE_MARKERS = (
    "authentication failed",
    "could not read username",
    "invalid username or token",
    "repository not found",
)


def _git_remote(command: list[str], cwd: Path, github_token: str | None = None) -> str:
    """Run a git command that talks to the remote, with token auth and a clear hint."""
    try:
        return _run_command(command, cwd=cwd, env=_git_auth_env(github_token))
    except ExternalRuntimeError as exc:
        message = str(exc)
        if any(marker in message.lower() for marker in _GIT_AUTH_FAILURE_MARKERS):
            hint = (
                "GitHub refused the credentials. If this repository is private, enter "
                "a GitHub token with read access to its contents in the installer "
                "(or set GH_TOKEN / GITHUB_TOKEN for the server process)."
            )
            raise ExternalRuntimeError(f"{message}\n{hint}") from exc
        raise


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
            encoding="utf-8",
            errors="replace",
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


def _safe_git(path: Path, args: list[str], github_token: str | None = None) -> str:
    if not host_git_available():
        raise ExternalRuntimeError(
            "Git is not available on this host. Use release-based installation instead."
        )
    if github_token is not None or args[:1] in (["fetch"], ["pull"]):
        return _git_remote(["git", *args], cwd=path, github_token=github_token)
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


def _list_remote_branches_uncached(
    spec, github_token: str | None = None
) -> tuple[list[str], str | None]:
    branches: list[str] = []
    for page in range(1, 11):  # up to 1000 branches
        url = (
            f"https://api.github.com/repos/{spec.github_repo}/branches"
            f"?per_page=100&page={page}"
        )
        try:
            response = _github_api_request(url, github_token=github_token)
        except ExternalRuntimeError as exc:
            return sorted(set(branches)), str(exc)
        if response.status_code == 404:
            # Unknown repository, or a private one queried without a token.
            return sorted(set(branches)), (
                None
                if branches
                else "GitHub does not list this repository's branches "
                "(private repository? provide a GitHub token)."
            )
        if response.status_code == 403:
            return sorted(set(branches)), "GitHub branch lookup denied or rate limited."
        if response.status_code >= 400:
            return (
                sorted(set(branches)),
                f"GitHub branch lookup failed ({response.status_code}).",
            )

        try:
            payload = response.json()
        except ValueError:
            return sorted(set(branches)), "GitHub branch response was not valid JSON."
        if not isinstance(payload, list):
            return sorted(set(branches)), "GitHub branch response was not a list."

        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                branches.append(name)
        if len(payload) < 100:
            break
    return sorted(set(branches)), None


def _list_remote_branches_git(
    spec, github_token: str | None = None
) -> tuple[list[str], str | None]:
    """Branches via ``git ls-remote``: no API rate limit, uses the user's git credentials."""
    if not host_git_available():
        return [], None
    cwd = spec.path.parent if spec.path.parent.exists() else Path.cwd()
    try:
        output = _git_remote(
            ["git", "ls-remote", "--heads", spec.repo_url],
            cwd=cwd,
            github_token=github_token,
        )
    except ExternalRuntimeError as exc:
        return [], str(exc)
    names = []
    for line in output.splitlines():
        ref = line.split("\t")[-1].strip()
        if ref.startswith("refs/heads/"):
            names.append(ref.removeprefix("refs/heads/"))
    return sorted(set(names)), None


def _list_remote_branches(spec, github_token: str | None = None):
    return _remote_cached(
        "branches",
        spec,
        "",
        github_token,
        lambda: _list_remote_branches_uncached(spec, github_token=github_token),
    )


def _branch_list_for_repo(
    spec, git_managed: bool, github_token: str | None = None
) -> tuple[list[str], str | None]:
    branches: set[str] = set()
    branch_error = None

    remote_branches, remote_error = _list_remote_branches(
        spec, github_token=github_token
    )
    if remote_branches:
        branches.update(remote_branches)
    else:
        # GitHub API unavailable (rate limit, private repo, proxy): ask git directly.
        git_branches, git_error = _list_remote_branches_git(
            spec, github_token=github_token
        )
        if git_branches:
            branches.update(git_branches)
        elif remote_error or git_error:
            branch_error = remote_error or git_error

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
    return sorted(branches), branch_error


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
    install_commands = _effective_install_commands(spec)
    if not install_commands:
        # no manifest: a pure-Python plugin that runs inside the core has no
        # dependencies of its own, so there is nothing missing
        return True
    for command in install_commands:
        if "-r" in command:
            req_path = spec.path / command[command.index("-r") + 1]
            if not req_path.exists():
                return False
    return True


def _validate_prereqs(spec) -> bool:
    if not spec.path.exists():
        return False
    if not spec.validate_entrypoints:
        return True
    return all((spec.path / entry).exists() for entry in spec.validate_entrypoints)


def core_constraints_file() -> Path | None:
    """Pinned versions of the core's dependencies (installed by the launcher).

    Plugins are installed with ``PIP_CONSTRAINT`` pointing here so a plugin
    requirement can never upgrade/downgrade a package the core depends on
    (pip reports a conflict instead of silently breaking YSocial).
    """
    explicit = os.environ.get("YSOCIAL_CONSTRAINTS")
    candidates = [Path(explicit)] if explicit else []
    try:
        from y_web.src.system.path_utils import get_home_path

        candidates.append(Path(get_home_path()) / "runtime" / "constraints.txt")
    except Exception:
        pass
    return next((c for c in candidates if c.is_file()), None)


def _ensure_pip(python_executable: str) -> str:
    """Make sure ``python -m pip`` works (uv venvs may be created without pip)."""
    probe = subprocess.run(
        [python_executable, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if probe.returncode == 0:
        return ""
    return _run_command(
        [python_executable, "-m", "ensurepip", "--upgrade"],
        cwd=Path.cwd(),
        timeout=300,
    )


def _effective_install_commands(spec) -> tuple[tuple[str, ...], ...]:
    if spec.install_commands:
        return spec.install_commands

    detected_commands: list[tuple[str, ...]] = []
    requirements_path = spec.path / "requirements.txt"
    pyproject_path = spec.path / "pyproject.toml"
    setup_path = spec.path / "setup.py"

    if requirements_path.exists():
        detected_commands.append(
            ("python", "-m", "pip", "install", "-r", "requirements.txt")
        )
    if pyproject_path.exists() or setup_path.exists():
        detected_commands.append(("python", "-m", "pip", "install", "-e", "."))
    return tuple(detected_commands)


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


def _list_releases_uncached(
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


def _list_releases(spec, github_token: str | None = None):
    return _remote_cached(
        "releases",
        spec,
        "",
        github_token,
        lambda: _list_releases_uncached(spec, github_token=github_token),
        ttl_ok=_RELEASES_TTL_OK,
    )


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


def _version_numbers(tag: str | None) -> tuple[int, ...] | None:
    """Numeric part of a release tag ("v2.1.0" -> (2, 1, 0)), None when it has none."""
    match = re.match(r"^\s*[vV]?(\d+(?:\.\d+)*)", str(tag or ""))
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def release_is_newer(latest: str | None, installed: str | None) -> bool:
    """True only when ``latest`` is a higher version than ``installed``.

    Tags are compared as numbers (v2.10.0 > v2.9.0), not as text, and equal
    versions are never an update; tags without numbers fall back to inequality.
    """
    if not latest or not installed:
        return False
    new, old = _version_numbers(latest), _version_numbers(installed)
    if new is None or old is None:
        return str(latest).strip() != str(installed).strip()
    width = max(len(new), len(old))
    pad = lambda parts: parts + (0,) * (width - len(parts))  # noqa: E731
    return pad(new) > pad(old)


def _get_archive(url: str, github_token: str | None, timeout: int):
    """GET an archive; on 415 retry once without any Accept preference."""
    headers = _github_download_headers(github_token)
    response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    if response.status_code == 415:
        headers.pop("Accept", None)
        response = requests.get(
            url, headers=headers, timeout=timeout, allow_redirects=True
        )
    return response


def _download_release_archive(
    spec, release: dict[str, Any], github_token: str | None = None
) -> bytes:
    url = release.get("zipball_url") or release.get("tarball_url")
    if not url:
        raise ExternalRuntimeError(
            f"Release {release.get('tag')} does not expose a downloadable archive."
        )

    try:
        response = _get_archive(url, github_token, 60)
    except requests.RequestException as exc:
        raise ExternalRuntimeError(f"Release download failed: {exc}") from exc

    if response.status_code == 404:
        raise ExternalRuntimeError("Release archive not found or not accessible.")
    if response.status_code == 403:
        raise ExternalRuntimeError("GitHub denied access to the release archive.")
    if response.status_code >= 400:
        raise ExternalRuntimeError(f"Release download failed ({response.status_code}).")
    return response.content


ARCHIVE_MARKER = ".ysocial-source.json"


def _read_archive_marker(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((path / ARCHIVE_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("source") == "archive" else None


def _remote_branch_head_uncached(
    spec, branch: str, github_token: str | None = None
) -> tuple[str | None, str | None]:
    """Latest commit SHA of ``branch`` on GitHub, as ``(sha, error)``."""
    url = f"https://api.github.com/repos/{spec.github_repo}/commits/{branch}"
    try:
        response = _github_api_request(url, github_token=github_token)
    except ExternalRuntimeError as exc:
        return None, str(exc)
    if response.status_code >= 400:
        return None, f"GitHub branch lookup failed ({response.status_code})."
    try:
        sha = str(response.json().get("sha") or "").strip()
    except (ValueError, AttributeError):
        return None, "GitHub commit response was not valid JSON."
    return (sha or None), (None if sha else "GitHub returned no commit.")


def _remote_branch_head(spec, branch: str, github_token: str | None = None):
    return _remote_cached(
        "head",
        spec,
        branch,
        github_token,
        lambda: _remote_branch_head_uncached(spec, branch, github_token=github_token),
    )


def _download_branch_archive(
    spec, branch: str, github_token: str | None = None
) -> bytes:
    url = f"https://api.github.com/repos/{spec.github_repo}/zipball/{branch}"
    try:
        response = _get_archive(url, github_token, 120)
    except requests.RequestException as exc:
        raise ExternalRuntimeError(f"Branch download failed: {exc}") from exc
    if response.status_code == 404:
        raise ExternalRuntimeError(
            f"Branch {branch} of {spec.github_repo} was not found or is not accessible "
            "(private repository? provide a GitHub token)."
        )
    if response.status_code == 403:
        raise ExternalRuntimeError("GitHub denied access to the branch archive.")
    if response.status_code >= 400:
        raise ExternalRuntimeError(f"Branch download failed ({response.status_code}).")
    return response.content


RELEASE_MARKER = ".ysocial-release.json"


def _write_release_marker(path: Path, tag: str) -> None:
    try:
        (path / RELEASE_MARKER).write_text(
            json.dumps(
                {
                    "source": "release",
                    "tag": tag,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _installed_release_tag(repo_key: str, path: Path) -> str | None:
    """Release tag of a release-archive install: marker first, then the action log
    (installs made before the marker existed)."""
    try:
        data = json.loads((path / RELEASE_MARKER).read_text(encoding="utf-8"))
        tag = str(data.get("tag") or "").strip()
        if tag:
            return tag
    except (OSError, ValueError, AttributeError):
        pass
    for record in read_external_runtime_logs(limit=2000, repo_key=repo_key):
        if record.get("success") and record.get("action") == "download_release":
            tag = str(record.get("branch") or "").strip()
            if tag:
                return tag
    return None


def _write_archive_marker(path: Path, branch: str, sha: str | None) -> None:
    (path / ARCHIVE_MARKER).write_text(
        json.dumps(
            {
                "source": "archive",
                "branch": branch,
                "commit": sha,
                "installed_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def is_archive_install(repo: "str | Path") -> bool:
    """True when the plugin was installed from a branch archive (no git checkout).

    ``repo`` is a repository key or the plugin's directory.
    """
    path = repo if isinstance(repo, Path) else runtime_spec(repo).path
    return _read_archive_marker(path) is not None and not (path / ".git").exists()


def install_runtime_branch_archive(
    repo_key: str,
    branch: str | None,
    actor: str,
    github_token: str | None = None,
) -> None:
    """Install a branch from its GitHub archive: no git needed, updates re-download."""
    spec = runtime_spec(repo_key)
    branch_name = _resolve_branch(spec, branch)
    if spec.path.exists():
        raise ExternalRuntimeError(f"{spec.label} already exists at {spec.path}")
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    sha, _error = _remote_branch_head(spec, branch_name, github_token)
    archive = _download_branch_archive(spec, branch_name, github_token)
    try:
        _extract_archive_bytes(archive, spec.path)
        _write_archive_marker(spec.path, branch_name, sha)
    except Exception as exc:
        shutil.rmtree(spec.path, ignore_errors=True)
        raise ExternalRuntimeError(f"Branch extraction failed: {exc}") from exc
    output = "\n".join(
        [
            f"Installed {spec.label} from the archive of branch {branch_name}"
            + (f" at {sha[:7]}." if sha else "."),
            f"Repository: {spec.github_repo}",
            f"Destination: {spec.path}",
        ]
    )
    log_external_runtime_action(
        repo_key, "install_branch_archive", actor, branch_name, True, output
    )


def update_runtime_branch_archive(
    repo_key: str,
    branch: str | None,
    actor: str,
    github_token: str | None = None,
) -> bool:
    """Re-download the branch if its head moved. Returns True when replaced.

    Archive installs are not meant to be edited: the directory is replaced as a whole.
    """
    spec = runtime_spec(repo_key)
    marker = _read_archive_marker(spec.path)
    if marker is None:
        raise ExternalRuntimeError(
            f"{spec.label} was not installed from a branch archive"
        )
    branch_name = _resolve_branch(spec, branch or marker.get("branch"))
    sha, error = _remote_branch_head(spec, branch_name, github_token)
    if sha and sha == marker.get("commit") and branch_name == marker.get("branch"):
        log_external_runtime_action(
            repo_key,
            "update",
            actor,
            branch_name,
            True,
            f"{spec.label} is already at the latest commit of {branch_name} ({sha[:7]}).",
        )
        return False
    archive = _download_branch_archive(spec, branch_name, github_token)
    staging = spec.path.with_name(spec.path.name + ".new")
    previous = spec.path.with_name(spec.path.name + ".old")
    for leftover in (staging, previous):
        shutil.rmtree(leftover, ignore_errors=True)
    try:
        _extract_archive_bytes(archive, staging)
        _write_archive_marker(staging, branch_name, sha)
        spec.path.rename(previous)
        staging.rename(spec.path)
    except Exception as exc:
        if previous.exists() and not spec.path.exists():
            previous.rename(spec.path)  # roll back
        shutil.rmtree(staging, ignore_errors=True)
        raise ExternalRuntimeError(f"Branch update failed: {exc}") from exc
    shutil.rmtree(previous, ignore_errors=True)
    log_external_runtime_action(
        repo_key,
        "update",
        actor,
        branch_name,
        True,
        f"Updated {spec.label} to {branch_name}"
        + (f" at {sha[:7]}." if sha else ".")
        + (f" (head lookup: {error})" if error else ""),
    )
    return True


def get_runtime_status(
    repo_key: str,
    github_token: str | None = None,
    *,
    include_remote_metadata: bool = True,
    check_release_update: bool = False,
) -> RuntimeStatus:
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

    archive_marker = _read_archive_marker(path) if exists and not git_managed else None
    update_available = None
    if archive_marker:
        current_branch = archive_marker.get("branch")
        current_commit = (archive_marker.get("commit") or "")[:7] or None
        if include_remote_metadata and current_branch:
            head, _err = _remote_branch_head(spec, current_branch, github_token)
            if head:
                update_available = head != archive_marker.get("commit")

    releases: list[dict[str, Any]] = []
    release_error: str | None = None
    branch_error: str | None = None
    if include_remote_metadata:
        # the releases and branches lookups are independent network calls
        with ThreadPoolExecutor(max_workers=2) as pool:
            releases_future = pool.submit(
                _list_releases, spec, github_token=github_token
            )
            branches_future = pool.submit(
                _branch_list_for_repo, spec, git_managed, github_token=github_token
            )
            releases, release_error = releases_future.result()
            branches, branch_error = branches_future.result()
    elif git_managed or archive_marker:
        # Git-managed runtimes need remote branch discovery even in fast view so
        # branch selectors can expose remote-only branches such as feature or
        # hotfix branches that are not yet present locally.
        branches, branch_error = _branch_list_for_repo(
            spec, git_managed, github_token=github_token
        )
    else:
        branches = sorted(
            {
                str(spec.default_branch or "").strip() or "main",
                str(current_branch or "").strip(),
            }
            - {""}
        )
    release_managed = (
        exists and not git_managed and archive_marker is None and not path.is_symlink()
    )
    installed_release_tag = None
    release_update_available = None
    if release_managed:
        installed_release_tag = _installed_release_tag(spec.key, path)
        if not include_remote_metadata and check_release_update:
            # cheap list view: only the (cached) release list, no branch lookups
            releases, release_error = _list_releases(spec, github_token=github_token)
        latest_tag = releases[0]["tag"] if releases else None
        if installed_release_tag and latest_tag:
            release_update_available = release_is_newer(
                latest_tag, installed_release_tag
            )
    path_kind = "missing"
    if exists:
        path_kind = "symlink" if path.is_symlink() else "directory"

    return RuntimeStatus(
        key=spec.key,
        label=spec.label,
        group=spec.group,
        group_label=spec.group_label,
        category=spec.category,
        category_label=spec.category_label,
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
        release_error=release_error or branch_error,
        path_kind=path_kind,
        python_executable=resolve_python_executable(),
        is_private=spec.is_private and not repo_is_public(spec),
        archive_managed=archive_marker is not None,
        update_available=update_available,
        release_managed=release_managed,
        installed_release_tag=installed_release_tag,
        release_update_available=release_update_available,
        trust=getattr(spec, "trust", "official"),
        source=getattr(spec, "source", "builtin"),
        description=getattr(spec, "description", ""),
    )


def get_grouped_runtime_status(
    github_token: str | None = None,
    *,
    include_remote_metadata: bool = True,
    check_release_update: bool = False,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group_key, group_label, specs in grouped_runtime_specs():
        groups.append(
            {
                "group": group_key,
                "label": group_label,
                "repos": [
                    get_runtime_status(
                        spec.key,
                        github_token=github_token,
                        include_remote_metadata=include_remote_metadata,
                        check_release_update=check_release_update,
                    ).to_dict()
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
    _write_release_marker(spec.path, release["tag"])

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


def clone_runtime_repo(
    repo_key: str,
    branch: str | None,
    actor: str,
    github_token: str | None = None,
) -> None:
    spec = runtime_spec(repo_key)
    branch_name = _resolve_branch(spec, branch)
    if not host_git_available():
        raise ExternalRuntimeError(
            f"Git is not available on this host. Install {spec.label} from a GitHub release instead."
        )
    if spec.path.exists():
        raise ExternalRuntimeError(f"{spec.label} already exists at {spec.path}")
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    output = _git_remote(
        ["git", "clone", "--branch", branch_name, spec.repo_url, str(spec.path)],
        cwd=spec.path.parent,
        github_token=github_token,
    )
    log_external_runtime_action(repo_key, "clone", actor, branch_name, True, output)


def fetch_runtime_repo(
    repo_key: str,
    branch: str | None,
    actor: str,
    github_token: str | None = None,
) -> None:
    spec = runtime_spec(repo_key)
    marker = _read_archive_marker(spec.path)
    if marker is not None and not (spec.path / ".git").exists():
        branch_name = _resolve_branch(spec, branch or marker.get("branch"))
        sha, error = _remote_branch_head(spec, branch_name, github_token)
        if not sha:
            raise ExternalRuntimeError(error or "Could not read the branch head")
        log_external_runtime_action(
            repo_key,
            "fetch",
            actor,
            branch_name,
            True,
            f"Latest commit of {branch_name}: {sha[:7]} "
            f"(installed: {(marker.get('commit') or '?')[:7]}).",
        )
        return
    status = get_runtime_status(repo_key)
    if not host_git_available():
        raise ExternalRuntimeError(
            f"Git is not available on this host. Git-based fetch operations are unavailable for {spec.label}."
        )
    if not status.installed:
        raise ExternalRuntimeError(f"{spec.label} is not installed")
    if not status.git_managed:
        raise ExternalRuntimeError(
            f"{spec.label} was installed from a release archive. Use the advanced clone option for git operations."
        )
    branch_name = _resolve_branch(spec, branch)
    output_parts = [
        _normalize_origin_remote(spec),
        _safe_git(
            spec.path,
            ["fetch", "origin", branch_name, "--prune"],
            github_token=github_token,
        ),
    ]
    output = "\n".join(part for part in output_parts if part)
    log_external_runtime_action(repo_key, "fetch", actor, branch_name, True, output)


def _checkout_branch(path: Path, branch_name: str) -> str:
    local_branches = _safe_git(
        path, ["branch", "--format=%(refname:short)"]
    ).splitlines()
    if branch_name in [item.strip() for item in local_branches]:
        output_parts = [_safe_git(path, ["checkout", branch_name])]
        try:
            output_parts.append(
                _safe_git(
                    path,
                    [
                        "branch",
                        "--set-upstream-to",
                        f"origin/{branch_name}",
                        branch_name,
                    ],
                )
            )
        except Exception:
            pass
        return "\n".join(part for part in output_parts if part)

    remote_branches = _safe_git(
        path, ["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"]
    )
    remote_branch_names = {
        line.strip().removeprefix("origin/")
        for line in remote_branches.splitlines()
        if line.strip()
    }
    if branch_name not in remote_branch_names:
        raise ExternalRuntimeError(f"Branch {branch_name} was not found on origin")
    output_parts = [
        _safe_git(path, ["checkout", "-B", branch_name, f"origin/{branch_name}"])
    ]
    try:
        output_parts.append(
            _safe_git(
                path,
                ["branch", "--set-upstream-to", f"origin/{branch_name}", branch_name],
            )
        )
    except Exception:
        pass
    return "\n".join(part for part in output_parts if part)


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


def update_runtime_repo(
    repo_key: str,
    branch: str | None,
    actor: str,
    github_token: str | None = None,
) -> None:
    spec = runtime_spec(repo_key)
    if (
        _read_archive_marker(spec.path) is not None
        and not (spec.path / ".git").exists()
    ):
        update_runtime_branch_archive(repo_key, branch, actor, github_token)
        return
    status = get_runtime_status(repo_key)
    if not host_git_available():
        raise ExternalRuntimeError(
            f"Git is not available on this host. Git-based update operations are unavailable for {spec.label}."
        )
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
        _safe_git(
            spec.path,
            ["fetch", "origin", branch_name, "--prune"],
            github_token=github_token,
        ),
        _checkout_branch(spec.path, branch_name),
        _safe_git(
            spec.path,
            ["pull", "--ff-only", "origin", branch_name],
            github_token=github_token,
        ),
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

    install_commands = _effective_install_commands(spec)
    if not install_commands:
        # Plugins that run inside the core (e.g. Reactive Agents) ship no
        # requirements.txt / pyproject.toml / setup.py: nothing to install.
        output = (
            f"{spec.label} declares no dependency manifest "
            "(requirements.txt, pyproject.toml or setup.py): nothing to install."
        )
        log_external_runtime_action(repo_key, "install", actor, None, True, output)
        return

    output_parts: list[str] = []
    env = os.environ.copy()
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    constraints = core_constraints_file()
    if constraints is not None:
        env["PIP_CONSTRAINT"] = str(constraints)
    python_executable = resolve_python_executable()
    output_parts.append(f"Using interpreter: {python_executable}")
    if constraints is not None:
        output_parts.append(f"Constraining core packages with: {constraints}")
    output_parts.append(_ensure_pip(python_executable))
    for command in install_commands:
        resolved = [
            python_executable if token == "python" else token for token in command
        ]
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

    if spec.validate_entrypoints:
        output_parts = [
            f"Required files present: {', '.join(spec.validate_entrypoints)}"
        ]
    else:
        output_parts = ["No explicit required files configured for this plugin."]
    if spec.validate_import:
        script = (
            "import sys; "
            f"sys.path.insert(0, {spec.path.as_posix()!r}); "
            f"__import__({spec.validate_import!r}); "
            f"print('Imported {spec.validate_import}')"
        )
        output_parts.append(
            _run_command([resolve_python_executable(), "-c", script], cwd=spec.path)
        )
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
