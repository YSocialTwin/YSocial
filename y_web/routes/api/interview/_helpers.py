from __future__ import annotations

import json
import os
import re
from typing import Any, List, Optional, Tuple

from flask import jsonify
from flask_login import current_user

from y_web.src.models import Admin_users

from ._blueprint import (
    _INTERVIEW_MEMORY_MODE_DEFAULT,
    _MEMORY_MODE_LEGACY,
    _MEMORY_MODE_SEMANTIC,
)


def _get_experiment_uid_from_db_name(db_name: str) -> Optional[str]:
    """Extract the experiment UID from SQLite/PostgreSQL experiment db names."""
    if not db_name:
        return None
    if db_name.startswith("experiments_"):
        return db_name.replace("experiments_", "")
    if db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
        parts = re.split(r"[/\\\\]", db_name)
        if len(parts) >= 2:
            return parts[1]
    return None


def _parse_timeout_series(
    raw: Optional[str], default: Tuple[float, ...]
) -> Tuple[float, ...]:
    values: List[float] = []
    for part in str(raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            value = float(token)
        except Exception:
            continue
        if value > 0:
            values.append(value)
    return tuple(values) if values else default


_INTERVIEW_MEMORY_EVENTS_TIMEOUTS = _parse_timeout_series(
    os.environ.get("INTERVIEW_MEMORY_EVENTS_TIMEOUTS"),
    (6.0, 12.0, 20.0),
)
_INTERVIEW_MEMORY_SEARCH_TIMEOUTS = _parse_timeout_series(
    os.environ.get("INTERVIEW_MEMORY_SEARCH_TIMEOUTS"),
    (7.0, 15.0, 25.0),
)


def _json_success(data=None, meta=None, status=200):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def _json_error(message: str, status: int = 400, *, code: Optional[str] = None):
    payload = {"success": False, "error": message}
    if code:
        payload["code"] = code
    return jsonify(payload), status


def _require_privileged() -> Optional[Admin_users]:
    username = (getattr(current_user, "username", "") or "").strip()
    if not username:
        return None
    admin_user = Admin_users.query.filter_by(username=username).first()
    if not admin_user or admin_user.role not in {"admin", "researcher"}:
        return None
    return admin_user


def _normalize_llm_base_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"http://{url}"
    if not url.endswith("/v1"):
        url = url.rstrip("/") + "/v1"
    return url


def _safe_json_loads(text: str) -> Optional[dict]:
    try:
        return json.loads(text or "")
    except Exception:
        return None


def _normalize_memory_mode(mode: Optional[str]) -> str:
    val = str(mode or "").strip().lower()
    if val in {_MEMORY_MODE_LEGACY, _MEMORY_MODE_SEMANTIC}:
        return val
    return _INTERVIEW_MEMORY_MODE_DEFAULT


def _truncate_middle(text: str, max_len: int) -> str:
    s = (text or "").strip()
    if max_len <= 0:
        return ""
    if len(s) <= max_len:
        return s
    keep = max_len - 3
    left = max(0, keep // 2)
    right = max(0, keep - left)
    return (s[:left] + "..." + s[-right:]).strip()
