from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import current_app

from y_web import db
from y_web.src.experiment.context import register_experiment_database
from y_web.src.models import Exps
from y_web.src.system.path_utils import get_writable_path

import sys as _sys

from ._helpers import _get_experiment_uid_from_db_name, _normalize_memory_mode, _safe_json_loads


def _pick_listening_port(
    ports: List[int], *, preferred_port: Optional[int] = None
) -> Optional[int]:
    cleaned: List[int] = []
    for port in ports:
        try:
            value = int(port)
        except Exception:
            continue
        if value > 0 and value not in cleaned:
            cleaned.append(value)
    if not cleaned:
        return None
    if preferred_port:
        try:
            preferred_value = int(preferred_port)
        except Exception:
            preferred_value = None
        if preferred_value in cleaned:
            return preferred_value
    ranged = [port for port in cleaned if 5000 <= port <= 6000]
    if ranged:
        return ranged[0]
    return cleaned[0]


def _listening_ports_for_pid(pid: Optional[int]) -> List[int]:
    try:
        import psutil
    except Exception:
        return []

    try:
        proc = psutil.Process(int(pid or 0))
    except Exception:
        return []

    ports: List[int] = []
    try:
        connections = proc.net_connections(kind="tcp")
    except Exception:
        return []

    listen_status = getattr(psutil, "CONN_LISTEN", "LISTEN")
    for conn in connections:
        try:
            status = getattr(conn, "status", None)
            if status not in {listen_status, "LISTEN"}:
                continue
            laddr = getattr(conn, "laddr", None)
            port = getattr(laddr, "port", None) if laddr is not None else None
            if port:
                ports.append(int(port))
        except Exception:
            continue
    return ports


def _process_matches_experiment(
    proc: Any, *, exp: Exps, exp_uid: Optional[str]
) -> bool:
    try:
        cmdline = [str(part or "") for part in (proc.cmdline() or [])]
    except Exception:
        cmdline = []
    haystack = " ".join(cmdline)
    if exp_uid and exp_uid in haystack:
        return True
    db_name = str(getattr(exp, "db_name", "") or "").strip()
    if db_name and db_name in haystack:
        return True
    return False


def _discover_runtime_port_for_experiment_process(
    exp: Exps, *, preferred_port: Optional[int] = None
) -> Optional[int]:
    exp_uid = _get_experiment_uid_from_db_name(getattr(exp, "db_name", "") or "")

    _interview_mod = _sys.modules.get("y_web.routes.api.interview")
    _ports_for_pid = (
        _interview_mod._listening_ports_for_pid
        if _interview_mod is not None
        else _listening_ports_for_pid
    )

    pid_ports = _ports_for_pid(getattr(exp, "server_pid", None))
    chosen = _pick_listening_port(pid_ports, preferred_port=preferred_port)
    if chosen:
        return chosen

    try:
        import psutil
    except Exception:
        return None

    for proc in psutil.process_iter(["pid", "name"]):
        if not _process_matches_experiment(proc, exp=exp, exp_uid=exp_uid):
            continue
        chosen = _pick_listening_port(
            _ports_for_pid(getattr(proc, "pid", None)),
            preferred_port=preferred_port,
        )
        if chosen:
            return chosen
    return None


def _get_latest_experiment_runtime(exp: Exps) -> Exps:
    exp_id = int(getattr(exp, "idexp", 0) or 0)
    if not exp_id:
        return exp
    try:
        db.session.expire_all()
    except Exception:
        pass
    latest = Exps.query.filter_by(idexp=exp_id).first()
    return latest or exp


def _server_base_url(exp: Exps) -> str:
    _interview_mod = _sys.modules.get("y_web.routes.api.interview")
    _get_latest = (
        _interview_mod._get_latest_experiment_runtime
        if _interview_mod is not None
        else _get_latest_experiment_runtime
    )
    _discover_port = (
        _interview_mod._discover_runtime_port_for_experiment_process
        if _interview_mod is not None
        else _discover_runtime_port_for_experiment_process
    )
    latest = _get_latest(exp)
    host = (getattr(latest, "server", "") or "").strip() or "127.0.0.1"
    configured_port = int(getattr(latest, "port", 0) or 0)
    runtime_port = _discover_port(
        latest, preferred_port=configured_port
    )
    port = int(runtime_port or configured_port or 0)
    if host.startswith(("http://", "https://")):
        return host.rstrip("/")
    return f"http://{host}:{port}"


def _post_server_json(exp: Exps, path: str, payload: dict, *, timeout_s: float = 4.0):
    base = _server_base_url(exp)
    url = f"{base}{path}"
    resp = requests.post(url, json=payload, timeout=timeout_s)
    return _safe_json_loads(resp.text)


def _post_server_json_with_retries(
    exp: Exps,
    path: str,
    payload: dict,
    *,
    timeouts_s: Tuple[float, ...],
    require_status_200: bool = False,
) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    attempts = max(1, len(timeouts_s))
    for timeout_s in timeouts_s[:attempts]:
        try:
            out = _post_server_json(exp, path, payload, timeout_s=float(timeout_s))
        except Exception as exc:
            last_err = exc
            continue

        if not isinstance(out, dict):
            last_err = RuntimeError(f"{path} invalid response")
            continue

        if require_status_200 and int(out.get("status") or 0) != 200:
            last_err = RuntimeError(f"{path} status={out.get('status')}")
            continue

        return out

    if last_err is not None:
        raise RuntimeError(f"{path} failed after {attempts} attempts: {last_err}")
    raise RuntimeError(f"{path} failed after {attempts} attempts")


def _build_change_db_path_for_exp(exp: Exps) -> str:
    """
    Build payload path expected by YServer /change_db endpoint.

    Mirrors the existing server boot logic so interview mode uses the same DB binding rules.
    """
    db_uri_main = str(current_app.config.get("SQLALCHEMY_DATABASE_URI", "") or "")
    db_type = "postgresql" if db_uri_main.startswith("postgresql") else "sqlite"

    y_web_dir = get_writable_path(os.path.join("y_web"))
    if db_type == "sqlite":
        full_path = os.path.join(y_web_dir, str(getattr(exp, "db_name", "") or ""))
        if len(full_path) > 2 and full_path[1] == ":":
            if len(full_path) > 3 and full_path[2] in ("/", "\\"):
                return full_path[3:].replace("\\", "/")
            return full_path[2:].replace("\\", "/")
        return full_path[1:].replace("\\", "/")

    old_db_name = db_uri_main.split("/")[-1]
    return db_uri_main.replace(
        old_db_name, str(getattr(exp, "db_name", "") or "").strip()
    )


def _ensure_experiment_server_db_binding(exp: Exps) -> Dict[str, Any]:
    """
    Best-effort /change_db call so memory/search is scoped to the selected experiment DB.
    """
    out = {"ok": False, "change_db_url": "", "path": "", "error": ""}
    try:
        path_payload = _build_change_db_path_for_exp(exp)
    except Exception as exc:
        out["error"] = f"build_path_failed:{exc}"
        return out
    out["path"] = path_payload

    base = _server_base_url(exp)
    url = f"{base}/change_db"
    out["change_db_url"] = url
    try:
        resp = requests.post(url, json={"path": path_payload}, timeout=4.0)
        txt = resp.text or ""
        if resp.status_code == 200 and ("status" in txt):
            out["ok"] = True
            return out
        out["error"] = f"status={resp.status_code}"
        return out
    except Exception as exc:
        out["error"] = str(exc)
        return out


def _ensure_experiment_db_bind(exp: Exps) -> bool:
    """
    Ensure local db_exp-bound models query the selected experiment DB.

    Interview helpers read directly from Post/User_mgmt/Reactions models, which all
    use __bind_key__ = 'db_exp'. Relying only on request middleware is too fragile
    here because these helpers are also reused outside normal page routes.
    """
    try:
        exp_id = int(getattr(exp, "idexp", 0) or 0)
        db_name = str(getattr(exp, "db_name", "") or "").strip()
        if not exp_id or not db_name:
            return False
        register_experiment_database(current_app, exp_id, db_name)
        bind_key = f"db_exp_{exp_id}"
        binds = current_app.config.setdefault("SQLALCHEMY_BINDS", {})
        if bind_key in binds:
            binds["db_exp"] = binds[bind_key]
        return True
    except Exception:
        return False


def _memory_server_unavailable(db_binding: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(db_binding, dict):
        return True
    return not bool(db_binding.get("ok"))


def _build_unavailable_memory_snapshot(
    *,
    run_id: Optional[str],
    agent_user_id: int,
    memory_mode: Optional[str] = None,
    reason: str = "experiment_server_unavailable",
) -> Dict[str, Any]:
    requested_mode = _normalize_memory_mode(memory_mode)
    return {
        "run_id": run_id,
        "agent_user_id": int(agent_user_id),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "memory_mode_requested": requested_mode,
        "memory_mode_used": "unavailable",
        "load_state": "unavailable",
        "unavailable_reason": str(reason or "experiment_server_unavailable"),
        "note": (
            "Memory retrieval is unavailable because the experiment server is not reachable. "
            "Interview replies may still be grounded by persona, transcript history, and facts snapshots from the experiment database."
        ),
        "relationships": [],
        "threads": [],
        "recent_events_tail": [],
        "agent_events_tail": [],
    }
