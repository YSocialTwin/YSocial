"""Authoritative offline validation of a dating experiment folder (``python -m YDating.cli.validate``).

The validator writes nothing and never starts Ray. Exit code 0 means valid, 2 invalid. It is the same
pattern as :mod:`y_web.src.im.validation` for instant messaging.
"""

import json
import os
import subprocess
from typing import List, Optional, Tuple

from y_web.src.simulation.subprocess_env import build_subprocess_env

VALIDATE_MODULE = "YDating.cli.validate"
VALIDATE_TIMEOUT_SECONDS = 60


class DatingValidationError(RuntimeError):
    """The experiment folder is not valid for dating (``messages`` carry the reasons)."""

    def __init__(self, messages: List[str]):
        self.messages = list(messages)
        super().__init__("; ".join(self.messages) or "invalid dating configuration")


def _python_command() -> List[str]:
    from y_web.src.simulation.server import detect_env_handler

    python_cmd = detect_env_handler()
    if (
        isinstance(python_cmd, str)
        and " " in python_cmd
        and not os.path.isabs(python_cmd)
    ):
        return python_cmd.split()
    return [python_cmd]


def run_dating_validate(
    config_dir: str, repo_dir: Optional[str] = None, client_config: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """Run the validator on ``config_dir``; return ``(valid, error messages)``.

    A runtime that cannot be executed or answers something unparsable counts as invalid, with a message.
    """
    if repo_dir is None:
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir("YDating")

    env = dict(build_subprocess_env() or {})
    env["PYTHONPATH"] = os.pathsep.join(
        [repo_dir] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    cmd = _python_command() + [
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
        return False, [f"the dating validator could not be run: {exc}"]

    try:
        report = json.loads(proc.stdout)
    except ValueError:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, [
            "the dating validator gave no readable report"
            + (f": {detail[-1]}" if detail else "")
        ]

    if proc.returncode == 0 and report.get("valid"):
        return True, []
    messages = [
        f"{e.get('check', 'config')}: {e.get('message', '')}".strip()
        for e in report.get("errors", [])
    ]
    return False, messages or [
        f"the dating validator exited with code {proc.returncode}"
    ]


def validate_dating_folder(
    config_dir: str, repo_dir: Optional[str] = None, client_config: Optional[str] = None
) -> None:
    """Raise :class:`DatingValidationError` unless the folder (and the named client file) pass."""
    valid, messages = run_dating_validate(config_dir, repo_dir, client_config)
    if not valid:
        raise DatingValidationError(messages)
