"""Export and report files of an IM experiment (plan, 5.7, 7.5).

``yim-export`` reads the run database directly and never starts Ray; ``--snapshot`` copies the database
first, so an export of a run in progress is safe. Reports are written by ``yim-analyze`` into
``<folder>/reports``; YWeb lists them and never edits them.
"""

import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from y_web.src.im.validation import _python_command
from y_web.src.simulation.subprocess_env import build_subprocess_env

EXPORT_MODULE = "yinstantmessaging.cli.export"
EXPORT_TIMEOUT_SECONDS = 600
EXPORT_FORMATS = ("parquet", "csv")
# reports that need no extra model and no second run; the others stay on the command line
REPORT_COMMANDS = (
    "activity",
    "cascades",
    "network",
    "homogeneity",
    "emergence",
    "created-chats",
    "stress-reward",
)
REPORT_MODULE = "yinstantmessaging.cli.analyze"
REPORT_TIMEOUT_SECONDS = 900
ARTIFACT_KINDS = {"exports": "exports", "reports": "reports"}


def _env(repo_dir: str) -> Dict[str, str]:
    env = dict(build_subprocess_env() or {})
    env["PYTHONPATH"] = os.pathsep.join(
        [repo_dir] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    return {**os.environ, **env}


def parquet_available(repo_dir: Optional[str] = None) -> bool:
    """True when the runtime can write Parquet (the ``analysis`` extra of IM)."""
    if repo_dir is None:
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir("YInstantMessaging")
    try:
        proc = subprocess.run(
            _python_command() + ["-c", "import pyarrow"],
            cwd=repo_dir,
            env=_env(repo_dir),
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def run_export(
    folder: str,
    fmt: str = "csv",
    no_text: bool = False,
    snapshot: bool = False,
    repo_dir: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Run ``yim-export`` on ``folder``; return ``(ok, result or {"error": message})``."""
    if fmt not in EXPORT_FORMATS:
        return False, {"error": f"unknown export format: {fmt}"}
    if repo_dir is None:
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir("YInstantMessaging")
    cmd = _python_command() + [
        "-m",
        EXPORT_MODULE,
        "--config",
        str(folder),
        "--format",
        fmt,
    ]
    if no_text:
        cmd.append("--no-text")
    if snapshot:
        cmd.append("--snapshot")
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_dir,
            env=_env(repo_dir),
            capture_output=True,
            text=True,
            timeout=EXPORT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, {"error": f"yim-export could not be run: {exc}"}
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, {
            "error": (
                detail[-1]
                if detail
                else f"yim-export exited with code {proc.returncode}"
            )
        }
    try:
        return True, json.loads(proc.stdout)
    except ValueError:
        return True, {}


def run_report(
    folder: str, command: str, snapshot: bool = False, repo_dir: Optional[str] = None
) -> Tuple[bool, Dict[str, Any]]:
    """Run ``yim-analyze <command>`` on ``folder``; the report lands in ``<folder>/reports``."""
    if command not in REPORT_COMMANDS:
        return False, {"error": f"unknown report: {command}"}
    if repo_dir is None:
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir("YInstantMessaging")
    cmd = _python_command() + ["-m", REPORT_MODULE, command, "--config", str(folder)]
    if snapshot:
        cmd.append("--snapshot")
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_dir,
            env=_env(repo_dir),
            capture_output=True,
            text=True,
            timeout=REPORT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, {"error": f"yim-analyze could not be run: {exc}"}
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, {
            "error": (
                detail[-1]
                if detail
                else f"yim-analyze exited with code {proc.returncode}"
            )
        }
    try:
        return True, json.loads(proc.stdout)
    except ValueError:
        return True, {}


def list_artifacts(folder: str) -> Dict[str, List[Dict[str, Any]]]:
    """Files under ``exports/`` and ``reports/`` of the experiment folder, newest first."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for kind, sub in ARTIFACT_KINDS.items():
        root = os.path.join(folder, sub)
        rows = []
        if os.path.isdir(root):
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    path = os.path.join(dirpath, name)
                    rel = os.path.relpath(path, root).replace(os.sep, "/")
                    stat = os.stat(path)
                    rows.append(
                        {"name": rel, "size": stat.st_size, "mtime": stat.st_mtime}
                    )
        out[kind] = sorted(rows, key=lambda r: (-r["mtime"], r["name"]))
    return out


def resolve_artifact(folder: str, kind: str, name: str) -> Optional[str]:
    """Absolute path of an export or report file, or None when ``kind``/``name`` escape the folder."""
    sub = ARTIFACT_KINDS.get(kind)
    if not sub or not name:
        return None
    root = os.path.realpath(os.path.join(folder, sub))
    path = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        return None
    return path
