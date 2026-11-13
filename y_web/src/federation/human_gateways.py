"""Clients of the human gateways of microblogging, forum and photo sharing (F8, H3), written in the style of
``y_web.src.im.gateway_client``: loopback HTTP with a token, and the runtime's offline script when no gateway answers
and no server runs. YWeb never writes the runtime databases.

The three runtimes differ (``SPECS``): the microblogging gateway is a set of routes of the server itself (the token is
the ``human_gateway.token`` option of the server configuration), the forum gateway is its own process
(``python -m y_server.gateway``) and the photo-sharing one is started by ``run_gateway.py``. For the two processes
YWeb writes ``human_gateway.token`` in the experiment folder and ``human_gateway.json`` (host, port, pid).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

STATE_FILE = "human_gateway.json"
TOKEN_FILE = "human_gateway.token"
TIMEOUT = 8
START_TIMEOUT = 40


class GatewayUnavailable(RuntimeError):
    """No gateway answers and the runtime cannot be reached offline."""


@dataclass(frozen=True)
class Spec:
    platform_type: str
    repo: str
    token_header: str
    ensure_path: str  # HTTP route
    script: str = (
        "run_offline_gateway.py"  # the runtime's entry for a request without a gateway process
    )


SPECS = {
    "microblogging": Spec(
        "microblogging",
        "YServer",
        "X-YServer-Gateway-Token",
        "/gateway/v1/humans/ensure",
    ),
    "forum": Spec("forum", "YServerReddit", "X-YGateway-Token", "/register"),
    "photo_sharing": Spec(
        "photo_sharing", "YPhotoSharing", "X-YPS-Gateway-Token", "/v1/humans/ensure"
    ),
}
# Microblogging on the HPC backend (YSimulator): the server is a Ray actor with no HTTP surface, so every request goes
# through the runtime's script (``run_human_gateway.py``), which works with the server running or stopped.
HPC_MICROBLOGGING = Spec(
    "microblogging", "YSimulator", "", "", script="run_human_gateway.py"
)


def is_hpc(exp) -> bool:
    return (
        str(getattr(exp, "simulator_type", None) or "Standard").strip().upper() == "HPC"
    )


def read_state(folder) -> Optional[dict]:
    try:
        data = json.loads((Path(folder) / STATE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("port") else None
    except (OSError, ValueError):
        return None


def read_token(folder) -> Optional[str]:
    try:
        return (Path(folder) / TOKEN_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def server_up(folder) -> bool:
    """The runtime servers publish ``ray_ready.temp`` while they run."""
    return (Path(folder) / "ray_ready.temp").exists()


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def _load_json(path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


class RuntimeGateway:
    """``ensure(key, username, human_id)`` on one experiment: ``(status, payload)``.

    ``server_config`` is the path of the server configuration of the experiment, ``database`` the server database
    (the forum offline script wants both), ``offline`` an injectable runner ``(spec, request) -> (status, payload)``
    for tests."""

    def __init__(
        self,
        platform_type: str,
        folder,
        server_config=None,
        database=None,
        session=None,
        offline: Optional[Callable] = None,
        hpc: bool = False,
    ):
        if platform_type not in SPECS or (hpc and platform_type != "microblogging"):
            raise GatewayUnavailable(f"no human gateway for {platform_type}")
        self.hpc = bool(hpc)
        self.spec = HPC_MICROBLOGGING if hpc else SPECS[platform_type]
        self.folder = Path(folder)
        self.server_config = Path(server_config) if server_config else None
        self.database = Path(database) if database else None
        self.session = session or requests
        self._offline_runner = offline

    def _base(self) -> Tuple[str, str]:
        if self.spec.platform_type == "microblogging":
            cfg = _load_json(self.server_config) if self.server_config else {}
            token = (cfg.get("human_gateway") or {}).get("token")
            host, port = cfg.get("host") or "127.0.0.1", cfg.get("port")
            if not token or not port or not server_up(self.folder):
                raise GatewayUnavailable("the microblogging gateway is not available")
            return f"http://{host}:{int(port)}", str(token)
        state, token = read_state(self.folder), read_token(self.folder)
        if not state or not token or not _alive(state.get("pid")):
            raise GatewayUnavailable("gateway is not running")
        host = state.get("host", "127.0.0.1")
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise GatewayUnavailable("gateway address is not a loopback address")
        return f"http://{host}:{int(state['port'])}", token

    def _body(
        self, key: str, username: str, human_id: str, language: Optional[str]
    ) -> dict:
        t = self.spec.platform_type
        if t == "forum":
            return {
                "key": key,
                "account": {
                    "username": username[:15],
                    "email": f"{key.replace(':', '_')}@human.invalid"[:50],
                    "language": language or "en",
                    "human_id": human_id,
                },
            }
        body = {"human_key": key, "username": username, "language": language}
        if t == "microblogging":
            body["human_id"] = human_id
        return body

    def ensure(
        self, key: str, username: str, human_id: str, language: Optional[str] = None
    ):
        body = self._body(key, username, human_id, language)
        if self.hpc:
            return self._run_offline([str(self.folder)], {"op": "ensure", "body": body})
        try:
            return self._http(body)
        except GatewayUnavailable:
            if server_up(self.folder):
                raise
        return self._offline(body)

    # -- publishing (F8, H5): the actions of an enrolled person, with their optional ``crosspost_to`` -------------------
    def actions(self, account_id, username: str, key: str, actions: list):
        """Send ``actions`` of the person on this runtime through its gateway (offline when no server runs).

        The shape differs per runtime (see the ``docs/human-gateway.md`` of each): microblogging and photo sharing take an
        ``account_id``, the forum the username and e-mail the account was created with. Returns ``(status, payload)``.
        """
        t = self.spec.platform_type
        if self.hpc:
            return self._run_offline(
                [str(self.folder)],
                {
                    "op": "actions",
                    "body": {"account_id": str(account_id), "actions": actions},
                },
            )
        if t == "forum":
            email = f"{key.replace(':', '_')}@human.invalid"[:50]
            body = {"username": str(username)[:15], "email": email, "actions": actions}
            path = "/act"
        else:
            acct = (
                int(account_id)
                if t == "microblogging" and str(account_id).isdigit()
                else account_id
            )
            body = {"account_id": acct, "actions": actions}
            path = "/gateway/v1/actions" if t == "microblogging" else "/v1/actions"
        try:
            return self._http_path(path, body)
        except GatewayUnavailable:
            if server_up(self.folder):
                raise
        if t == "microblogging":
            argv, request = [str(self.server_config)], {"op": "actions", "body": body}
        elif t == "forum":
            argv, request = [str(self.server_config), str(self.database)], {
                "op": "act",
                "body": body,
            }
        else:
            argv, request = [str(self.folder)], {
                "method": "POST",
                "path": path,
                "body": body,
            }
        return self._run_offline(argv, request)

    def _http(self, body: dict):
        return self._http_path(self.spec.ensure_path, body)

    def _http_path(self, path: str, body: dict):
        base, token = self._base()
        try:
            resp = self.session.post(
                base + path,
                json=body,
                headers={self.spec.token_header: token},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise GatewayUnavailable(str(exc)) from exc
        try:
            payload = resp.json()
        except ValueError:
            payload = {"ok": False, "code": "bad_response"}
        return resp.status_code, payload

    def _request_of(self, body: dict):
        t = self.spec.platform_type
        if t == "microblogging":
            return [str(self.server_config)], {"op": "ensure", "body": body}
        if t == "forum":
            return [str(self.server_config), str(self.database)], {
                "op": "register",
                "body": body,
            }
        return [str(self.folder)], {
            "method": "POST",
            "path": self.spec.ensure_path,
            "body": body,
        }

    def _offline(self, body: dict):
        argv, request = self._request_of(body)
        return self._run_offline(argv, request)

    def _run_offline(self, argv, request):
        if self._offline_runner is not None:
            return self._offline_runner(self.spec, request)
        from y_web.src.simulation.server import detect_env_handler
        from y_web.src.system.path_utils import get_external_repo_dir

        repo = get_external_repo_dir(self.spec.repo)
        script = os.path.join(repo, self.spec.script)
        if not os.path.exists(script):
            raise GatewayUnavailable(
                f"{self.spec.repo} has no human gateway script: update the runtime"
            )
        try:
            done = subprocess.run(
                [detect_env_handler() or sys.executable, script] + argv,
                cwd=repo,
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=60,
            )
            answer = json.loads((done.stdout or "").strip().splitlines()[-1])
            status = int(answer.pop("status"))
            return status, answer.get("payload", answer)
        except (
            OSError,
            ValueError,
            IndexError,
            KeyError,
            subprocess.SubprocessError,
        ) as exc:
            raise GatewayUnavailable(f"offline gateway failed: {exc}") from exc


# -- processes (forum and photo sharing; microblogging has no process) ------------------------------
def write_token(folder) -> str:
    """A fresh per-run token in ``human_gateway.token`` (mode 0600)."""
    token = secrets.token_urlsafe(32)
    path = Path(folder) / TOKEN_FILE
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    return token


def set_microblogging_token(server_config) -> str:
    """The token of the microblogging gateway lives in the server configuration (``human_gateway.token``)."""
    path = Path(server_config)
    cfg = _load_json(path)
    section = (
        cfg.get("human_gateway") if isinstance(cfg.get("human_gateway"), dict) else {}
    )
    if not section.get("token"):
        section = dict(section, token=secrets.token_urlsafe(32))
        cfg["human_gateway"] = section
        path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return section["token"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_running(folder) -> bool:
    state = read_state(folder)
    return bool(state and _alive(state.get("pid")))


def _clear(folder: Path) -> None:
    for name in (STATE_FILE, TOKEN_FILE):
        try:
            (folder / name).unlink()
        except OSError:
            pass


def start_gateway(
    platform_type: str,
    folder,
    repo_dir: str,
    python_cmd: Optional[str] = None,
    server_url: Optional[str] = None,
) -> Optional[int]:
    """Start the gateway process of the forum or of photo sharing; its pid, or ``None`` with a warning in the log."""
    folder = Path(folder)
    if is_running(folder):
        return int(read_state(folder)["pid"])
    _clear(folder)
    token = write_token(folder)
    py = python_cmd or sys.executable
    try:
        kwargs = (
            {"start_new_session": True} if not sys.platform.startswith("win") else {}
        )
        if platform_type == "forum":
            port = _free_port()
            proc = subprocess.Popen(
                [
                    py,
                    "-m",
                    "y_server.gateway",
                    "--server",
                    server_url or "",
                    "--token-file",
                    str(folder / TOKEN_FILE),
                    "--port",
                    str(port),
                ],
                cwd=repo_dir,
                stdin=subprocess.DEVNULL,
                **kwargs,
            )
            (folder / STATE_FILE).write_text(
                json.dumps({"host": "127.0.0.1", "port": port, "pid": proc.pid}),
                encoding="utf-8",
            )
        elif platform_type == "photo_sharing":
            script = os.path.join(repo_dir, "run_gateway.py")
            if not os.path.exists(script):
                raise FileNotFoundError(
                    f"{script} not found: update the photo sharing runtime"
                )
            proc = subprocess.Popen(
                [py, script, str(folder)],
                cwd=repo_dir,
                env=dict(os.environ, YPHOTOSHARING_GATEWAY_TOKEN=token),
                stdin=subprocess.DEVNULL,
                **kwargs,
            )
        else:
            return None
    except Exception as exc:  # noqa: BLE001 - a gateway problem never fails a run
        logger.warning(
            "Human gateway of %s could not be started: %s", platform_type, exc
        )
        _clear(folder)
        return None
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if read_state(folder) and _alive(proc.pid):
            return proc.pid
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    logger.warning(
        "Human gateway of %s did not become ready; the simulation continues without it",
        platform_type,
    )
    stop_gateway(folder, pid=proc.pid)
    return None


def stop_gateway(folder, pid: Optional[int] = None) -> bool:
    """SIGTERM then SIGKILL, and remove the runtime files."""
    folder = Path(folder)
    pid = pid or (read_state(folder) or {}).get("pid")
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
    _clear(folder)
    return stopped
