"""Lifecycle of the IM human gateway (plan 4.8, 5.8).

Start order is IM server -> gateway -> IM clients; the stop order is the reverse. A gateway that does not
start is a warning, never a failed run: the simulation does not need it (plan 4.8, R18).
"""

import json
import logging
import os
import secrets
import signal
import subprocess
import sys
import time
from typing import Optional

from y_web.src.im.gateway_client import (
    STATE_FILE,
    TOKEN_FILE,
    GatewayUnavailable,
    GatewayClient,
    read_gateway_state,
)

logger = logging.getLogger(__name__)
START_TIMEOUT_SECONDS = 40


def human_config(exp_folder: str) -> dict:
    """The ``human`` section of the experiment's ``server_config.json`` (empty when absent)."""
    try:
        with open(os.path.join(exp_folder, "server_config.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return {}
    human = cfg.get("human")
    return human if isinstance(human, dict) else {}


def human_enabled(exp_folder: str) -> bool:
    return bool(human_config(exp_folder).get("enabled"))


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def is_running(exp_folder: str) -> bool:
    state = read_gateway_state(exp_folder)
    return bool(state and _alive(state.get("pid")))


def _remove(exp_folder: str, *names: str) -> None:
    for name in names:
        try:
            os.remove(os.path.join(exp_folder, name))
        except OSError:
            pass


def start_gateway(exp_folder: str, repo_dir: str, python_cmd: Optional[str] = None) -> Optional[int]:
    """Start the gateway if human participation is on; return its pid, or ``None`` (with a warning)."""
    if not human_enabled(exp_folder):
        return None
    if is_running(exp_folder):
        return int(read_gateway_state(exp_folder)["pid"])
    _remove(exp_folder, STATE_FILE, TOKEN_FILE)
    token = secrets.token_urlsafe(32)
    token_path = os.path.join(exp_folder, TOKEN_FILE)
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    env = dict(os.environ, YIM_GATEWAY_TOKEN=token)
    script = os.path.join(repo_dir, "run_gateway.py")
    try:
        if not os.path.exists(script):
            raise FileNotFoundError(f"{script} not found: update the instant messaging runtime")
        kwargs = {"start_new_session": True} if not sys.platform.startswith("win") else {}
        process = subprocess.Popen(
            [python_cmd or sys.executable, script, exp_folder],
            cwd=repo_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 - a gateway problem never fails the run
        logger.warning("Human gateway could not be started: %s", exc)
        _remove(exp_folder, TOKEN_FILE)
        return None
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if read_gateway_state(exp_folder):
            return process.pid
        if process.poll() is not None:
            break
        time.sleep(0.5)
    logger.warning("Human gateway did not become ready; the simulation continues without it")
    stop_gateway(exp_folder, pid=process.pid)
    return None


def stop_gateway(exp_folder: str, pid: Optional[int] = None) -> bool:
    """Stop the gateway (SIGTERM, then SIGKILL) and remove its runtime files."""
    state = read_gateway_state(exp_folder) or {}
    pid = pid or state.get("pid")
    stopped = False
    if pid and _alive(pid):
        try:
            os.kill(int(pid), signal.SIGTERM)
            for _ in range(50):
                if not _alive(pid):
                    break
                time.sleep(0.1)
            else:
                os.kill(int(pid), getattr(signal, "SIGKILL", signal.SIGTERM))
            stopped = True
        except OSError:
            pass
    _remove(exp_folder, STATE_FILE, TOKEN_FILE)
    return stopped


def gateway_status(exp_folder: str) -> dict:
    """What the experiment page shows: ``off`` / ``stopped`` / ``running`` / ``unreachable``."""
    if not human_enabled(exp_folder):
        return {"status": "off"}
    if not is_running(exp_folder):
        return {"status": "stopped"}
    try:
        code, body = GatewayClient(exp_folder).state()
    except GatewayUnavailable:
        return {"status": "unreachable"}
    if code != 200:
        return {"status": "unreachable"}
    return {"status": "running", "state": body.get("data")}


def register_offline(exp_folder: str, repo_dir: str, key: str, username: str, python_cmd: Optional[str] = None) -> bool:
    """Create a human account while the server is down, through the runtime's own script; ``True`` on success."""
    script = os.path.join(repo_dir, "run_register_human.py")
    if not os.path.exists(script):
        return False
    done = subprocess.run(
        [python_cmd or sys.executable, script, exp_folder, key, username],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    if done.returncode != 0:
        logger.warning("Offline human registration failed: %s", (done.stderr or "").strip())
    return done.returncode == 0
