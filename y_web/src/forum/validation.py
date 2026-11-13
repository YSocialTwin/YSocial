"""Offline validation of a forum experiment folder (``python -m YForum.cli.validate``), the same pattern as dating.

The validator writes nothing and never starts Ray. Exit code 0 means valid, 2 invalid.
"""

import json
import os
import subprocess
from typing import List, Optional, Tuple

from y_web.src.simulation.subprocess_env import build_subprocess_env, python_command

VALIDATE_MODULE = "YForum.cli.validate"
VALIDATE_TIMEOUT_SECONDS = 60


class ForumValidationError(RuntimeError):
    """The experiment folder is not valid for YForum (``messages`` carry the reasons)."""

    def __init__(self, messages: List[str]):
        self.messages = list(messages)
        super().__init__("; ".join(self.messages) or "invalid forum configuration")


def run_forum_validate(
    config_dir: str, repo_dir: Optional[str] = None, client_config: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """Run the validator on ``config_dir``; return ``(valid, error messages)``."""
    if repo_dir is None:
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir("YForum")

    env = dict(build_subprocess_env() or {})
    env["PYTHONPATH"] = os.pathsep.join(
        [repo_dir] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    cmd = python_command() + [
        "-m",
        VALIDATE_MODULE,
        "--config",
        str(config_dir),
        "--json",
    ]
    if client_config:
        cmd += ["--client-config", str(client_config)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_dir,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=VALIDATE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, [f"the forum validator could not be run: {exc}"]
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, [
            "the forum validator gave no readable report"
            + (f": {detail[-1]}" if detail else "")
        ]
    if proc.returncode == 0 and report.get("valid"):
        return True, []
    messages = [
        f"{e.get('check', 'config')}: {e.get('message', '')}".strip()
        for e in report.get("errors", [])
    ]
    return False, messages or [
        f"the forum validator exited with code {proc.returncode}"
    ]


def validate_forum_folder(
    config_dir: str, repo_dir: Optional[str] = None, client_config: Optional[str] = None
) -> None:
    """Raise :class:`ForumValidationError` unless the folder (and the named client file) pass."""
    valid, messages = run_forum_validate(config_dir, repo_dir, client_config)
    if not valid:
        raise ForumValidationError(messages)


def forum_hpc_installed() -> bool:
    """YForum is present (writable or bundled copy) with the two entry points the HPC launcher runs."""
    import os

    from y_web.src.system.path_utils import get_external_repo_dir

    root = get_external_repo_dir("YForum")
    return all(
        os.path.isfile(os.path.join(root, name))
        for name in ("run_server.py", "run_client.py")
    )
