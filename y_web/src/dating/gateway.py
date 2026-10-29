"""Human gateway of a dating run: client, process lifecycle and offline entry (IR-D-22, IR-D-31).

YWeb never writes the run database. Every action of a person, and every deck shown to a person, goes
through the gateway of the runtime (``run_gateway.py`` in YDating), which calls the server's own handlers.
The gateway listens on a loopback address; YWeb reads its address from ``human_gateway.json`` (written by
the gateway) and the per-run token from ``human_gateway.token`` (written by YWeb when it starts it, mode
0600). Start order: server -> gateway -> clients; stop order: the reverse. A gateway that does not start is
a warning, never a failed run: the agents do not need it.
"""

import json
import logging
import os
import secrets
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

STATE_FILE = "human_gateway.json"
TOKEN_FILE = "human_gateway.token"
TOKEN_HEADER = "X-YDating-Gateway-Token"
TIMEOUT = 8
START_TIMEOUT_SECONDS = 40


class GatewayUnavailable(RuntimeError):
    """The gateway is not running or does not answer (the page shows a notice)."""


# ------------------------------------------------------------------------------------ configuration
def human_config(exp_folder: str) -> dict:
    """The ``human`` section of the experiment's ``server_config.json`` (empty when absent)."""
    try:
        with open(
            os.path.join(exp_folder, "server_config.json"), encoding="utf-8"
        ) as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return {}
    human = cfg.get("human") if isinstance(cfg, dict) else None
    return human if isinstance(human, dict) else {}


def human_enabled(exp_folder: str) -> bool:
    return bool(human_config(exp_folder).get("enabled"))


# ----------------------------------------------------------------------------------------- runtime files
def read_gateway_state(exp_folder: str) -> Optional[dict]:
    try:
        with open(os.path.join(exp_folder, STATE_FILE), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) and data.get("port") else None
    except (OSError, ValueError):
        return None


def read_gateway_token(exp_folder: str) -> Optional[str]:
    try:
        with open(os.path.join(exp_folder, TOKEN_FILE), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def _remove(exp_folder: str, *names: str) -> None:
    for name in names:
        try:
            os.remove(os.path.join(exp_folder, name))
        except OSError:
            pass


def is_running(exp_folder: str) -> bool:
    state = read_gateway_state(exp_folder)
    return bool(state and _alive(state.get("pid")))


def server_up(exp_folder: str) -> bool:
    """The server of the experiment publishes ``ray_ready.temp`` while it runs."""
    return os.path.exists(os.path.join(exp_folder, "ray_ready.temp"))


def offline_possible(exp_folder: str) -> bool:
    """A person can register or edit the profile without the server (nobody else writes)."""
    return human_enabled(exp_folder) and not server_up(exp_folder)


# -------------------------------------------------------------------------------------------- client
class GatewayClient:
    """``call(op, body)`` returns ``(status, payload)``; offline when the server is down."""

    def __init__(self, exp_folder: str, session=None):
        self.exp_folder = exp_folder
        self.session = session or requests

    def _base(self) -> Tuple[str, str]:
        state, token = read_gateway_state(self.exp_folder), read_gateway_token(
            self.exp_folder
        )
        if not state or not token:
            raise GatewayUnavailable("gateway is not running")
        host = state.get("host", "127.0.0.1")
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise GatewayUnavailable("gateway address is not a loopback address")
        host = f"[{host}]" if ":" in host else host
        return f"http://{host}:{int(state['port'])}", token

    def _http(self, op: str, body: Dict[str, Any]):
        base, token = self._base()
        try:
            resp = self.session.post(
                f"{base}/v1/{op}",
                json=body,
                headers={TOKEN_HEADER: token},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise GatewayUnavailable(str(exc)) from exc
        try:
            payload = resp.json()
        except ValueError:
            payload = {"ok": False, "error": "bad response"}
        return resp.status_code, payload

    def call(self, op: str, body: Dict[str, Any]):
        try:
            return self._http(op, body)
        except GatewayUnavailable:
            if not offline_possible(self.exp_folder):
                raise
        return self._offline(op, body)

    def _offline(self, op: str, body: Dict[str, Any]):
        from y_web.src.hpc.platforms import get_hpc_platform
        from y_web.src.simulation.server import detect_env_handler
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir(get_hpc_platform("dating").runtime_repo)
        return offline_request(
            self.exp_folder, repo_dir, {"op": op, "body": body}, detect_env_handler()
        )

    # -- operations
    def register(self, key: str, account: dict):
        return self.call("register", {"key": key, "account": account})

    def state(self, agent_id: str):
        return self.call("state", {"agent_id": agent_id})

    def browse(self, agent_id: str):
        return self.call("browse", {"agent_id": agent_id})

    def conversations(self, agent_id: str):
        return self.call("conversations", {"agent_id": agent_id})

    def notifications(self, agent_id: str):
        return self.call("notifications", {"agent_id": agent_id})

    def act(self, agent_id: str, actions: list):
        return self.call("act", {"agent_id": agent_id, "actions": actions})

    def leave(self, agent_id: str):
        return self.call("leave", {"agent_id": agent_id})


# ------------------------------------------------------------------------------------------ process
def start_gateway(
    exp_folder: str, repo_dir: str, python_cmd: Optional[str] = None
) -> Optional[int]:
    """Start the gateway if human participation is on; return its pid, or ``None`` (with a warning)."""
    if not human_enabled(exp_folder):
        return None
    if is_running(exp_folder):
        return int(read_gateway_state(exp_folder)["pid"])
    _remove(exp_folder, STATE_FILE, TOKEN_FILE)
    token = secrets.token_urlsafe(32)
    fd = os.open(
        os.path.join(exp_folder, TOKEN_FILE),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    env = dict(os.environ, YDATING_GATEWAY_TOKEN=token)
    script = os.path.join(repo_dir, "run_gateway.py")
    try:
        if not os.path.exists(script):
            raise FileNotFoundError(f"{script} not found: update the YDating runtime")
        kwargs = (
            {"start_new_session": True} if not sys.platform.startswith("win") else {}
        )
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
    logger.warning(
        "Human gateway did not become ready; the simulation continues without it"
    )
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


def start_for_experiment(exp_folder: str) -> None:
    """Start the gateway of a dating experiment (a failure is a warning, never an error)."""
    try:
        from y_web.src.hpc.platforms import get_hpc_platform
        from y_web.src.simulation.server import detect_env_handler
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir(get_hpc_platform("dating").runtime_repo)
        start_gateway(exp_folder, repo_dir, detect_env_handler())
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: human gateway not started: {exc}")


def gateway_status(exp_folder: str) -> dict:
    """What the admin page shows: ``off`` / ``stopped`` / ``running`` / ``unreachable``."""
    if not human_enabled(exp_folder):
        return {"status": "off"}
    if not is_running(exp_folder):
        return {"status": "stopped"}
    try:
        base, token = GatewayClient(exp_folder)._base()
        resp = requests.get(
            f"{base}/v1/health", headers={TOKEN_HEADER: token}, timeout=TIMEOUT
        )
    except (GatewayUnavailable, requests.RequestException):
        return {"status": "unreachable"}
    return {"status": "running" if resp.status_code == 200 else "unreachable"}


def offline_request(
    exp_folder: str, repo_dir: str, request: dict, python_cmd: Optional[str] = None
):
    """Run one request through the runtime's offline gateway; returns ``(status, payload)``."""
    script = os.path.join(repo_dir, "run_offline_gateway.py")
    if not os.path.exists(script):
        raise GatewayUnavailable(
            "the YDating runtime has no offline gateway: update it"
        )
    try:
        done = subprocess.run(
            [python_cmd or sys.executable, script, exp_folder],
            cwd=repo_dir,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=60,
        )
        answer = json.loads((done.stdout or "").strip().splitlines()[-1])
        status = int(answer.pop("status"))
        return status, answer
    except (
        OSError,
        ValueError,
        IndexError,
        KeyError,
        subprocess.SubprocessError,
    ) as exc:
        raise GatewayUnavailable(f"offline gateway failed: {exc}") from exc
