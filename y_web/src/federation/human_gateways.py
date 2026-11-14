"""Clients of the human gateways of the platform runtimes (F8, H3), written in the style of the gateway client of the
instant messaging repository: loopback HTTP with a token, and the runtime's offline script when no gateway answers
and no server runs. YWeb never writes the runtime databases.

What each runtime's gateway looks like is declared by its provider (``human_gateway``, a ``HumanGatewayTraits``): the
gateway is a set of routes of the server itself (the token is the ``human_gateway.token`` option of the server
configuration), or a process of its own (YWeb writes ``human_gateway.token`` in the experiment folder and
``human_gateway.json`` with host, port and pid), or only a script of the runtime. This module owns the transport.
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
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional, Tuple

import requests

from y_web.platforms.base import GatewayLaunch, GatewayPaths
from y_web.src.federation import traits

logger = logging.getLogger(__name__)

STATE_FILE = "human_gateway.json"
TOKEN_FILE = "human_gateway.token"
TIMEOUT = 8
START_TIMEOUT = 40


class GatewayUnavailable(RuntimeError):
    """No gateway answers and the runtime cannot be reached offline."""


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
    (some runtime scripts want both), ``offline`` an injectable runner ``(spec, request) -> (status, payload)``
    for tests; ``hpc`` picks the provider of the HPC runtime when the platform has one per runtime.
    """

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
        spec = traits.human_gateway(platform_type, "HPC" if hpc else "Standard")
        if spec is None or not (spec.repo and spec.ensure_body):
            raise GatewayUnavailable(f"no human gateway for {platform_type}")
        self.platform_type = platform_type
        self.hpc = bool(hpc)
        self.spec = spec
        self.folder = Path(folder)
        self.server_config = Path(server_config) if server_config else None
        self.database = Path(database) if database else None
        self.paths = GatewayPaths(self.folder, self.server_config, self.database)
        self.session = session or requests
        self._offline_runner = offline

    def _base(self) -> Tuple[str, str]:
        if self.spec.token_in_server_config:
            cfg = _load_json(self.server_config) if self.server_config else {}
            token = (cfg.get("human_gateway") or {}).get("token")
            host, port = cfg.get("host") or "127.0.0.1", cfg.get("port")
            if not token or not port or not server_up(self.folder):
                raise GatewayUnavailable("the server gateway is not available")
            return f"http://{host}:{int(port)}", str(token)
        state, token = read_state(self.folder), read_token(self.folder)
        if not state or not token or not _alive(state.get("pid")):
            raise GatewayUnavailable("gateway is not running")
        host = state.get("host", "127.0.0.1")
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise GatewayUnavailable("gateway address is not a loopback address")
        return f"http://{host}:{int(state['port'])}", token

    def ensure(
        self, key: str, username: str, human_id: str, language: Optional[str] = None
    ):
        body = self.spec.ensure_body(key, username, human_id, language)
        if self.spec.http:
            try:
                return self._http_path(self.spec.ensure_path, body)
            except GatewayUnavailable:
                if server_up(self.folder):
                    raise
        return self._run_offline(*self.spec.offline_ensure(self.paths, body))

    # -- publishing (F8, H5): the actions of an enrolled person, with their optional ``crosspost_to`` -------------------
    def actions(self, account_id, username: str, key: str, actions: list):
        """Send ``actions`` of the person on this runtime through its gateway (offline when no server runs).

        The shape differs per runtime (see the ``docs/human-gateway.md`` of each). Returns ``(status, payload)``.
        """
        path, body = self.spec.actions_request(account_id, username, key, actions)
        if self.spec.http:
            try:
                return self._http_path(path, body)
            except GatewayUnavailable:
                if server_up(self.folder):
                    raise
        return self._run_offline(*self.spec.offline_actions(self.paths, path, body))

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

    def _run_offline(self, argv, request):
        if self._offline_runner is not None:
            return self._offline_runner(
                SimpleNamespace(
                    platform_type=self.platform_type,
                    repo=self.spec.repo,
                    script=self.spec.script,
                ),
                request,
            )
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


# -- processes (the runtimes whose gateway is a process of its own) ------------------------------
def write_token(folder) -> str:
    """A fresh per-run token in ``human_gateway.token`` (mode 0600)."""
    token = secrets.token_urlsafe(32)
    path = Path(folder) / TOKEN_FILE
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    return token


def set_server_token(server_config) -> str:
    """The token of a gateway that is part of the server lives in the server configuration (``human_gateway.token``)."""
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
    """Start the gateway process of a runtime that has one; its pid, or ``None`` with a warning in the log."""
    folder = Path(folder)
    spec = traits.human_gateway(platform_type)
    if spec is None or spec.start_process is None:
        return None
    if is_running(folder):
        return int(read_state(folder)["pid"])
    _clear(folder)
    token = write_token(folder)
    try:
        proc, state = spec.start_process(
            GatewayLaunch(
                folder=folder,
                repo_dir=repo_dir,
                python=python_cmd or sys.executable,
                token=token,
                server_url=server_url or "",
                token_file=folder / TOKEN_FILE,
                port=_free_port(),
                popen_kwargs=(
                    {"start_new_session": True}
                    if not sys.platform.startswith("win")
                    else {}
                ),
            )
        )
        if state:
            (folder / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
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
