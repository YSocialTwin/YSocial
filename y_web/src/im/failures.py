"""Why an instant messaging client stopped: the last ERROR record of its execution log (plan, 5.4).

The client writes, before any exit other than 0 and 130, a record with ``level: "ERROR"``,
``error_type``, ``error_message`` and ``exit_code`` (``docs/logging.md`` of YInstantMessaging).
"""

import json
from typing import Any, Dict, Optional

_TAIL_BYTES = 262144

def exit_messages():
    """Message per exit code of the client, in the words an administrator needs (translated)."""
    from y_web.i18n import gettext as _

    return {
        1: _("Unexpected error in the client: see the execution log."),
        2: _("Invalid configuration or a missing required plugin: fix the client settings and start again."),
        3: _("The server was not ready or not reachable, or its actor is dead: start the experiment server first."),
        4: _("The database is unusable, a migration failed or its schema is newer than the installed runtime."),
        5: _("Too many language-model sessions failed in a round: check that the LLM server and model are reachable. The client resumes from the round it did not close."),
        6: _("The configuration differs from the one recorded when the run started: restore the original files or reset the experiment."),
        130: _("The client was interrupted."),
    }


def _tail(path: str):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_BYTES))
            data = handle.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if size > _TAIL_BYTES and lines else lines


def describe_client_failure(execution_log_path: Optional[str]) -> Optional[Dict[str, Any]]:
    """The last ERROR record that carries an exit code, as ``exit_code``, ``error_type``, ``detail``, ``message``."""
    if not execution_log_path:
        return None
    found = None
    for raw in _tail(execution_log_path):
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if str(entry.get("level", "")).upper() != "ERROR" or entry.get("exit_code") is None:
            continue
        found = entry
    if found is None:
        return None
    try:
        code = int(found["exit_code"])
    except (TypeError, ValueError):
        code = 1
    detail = str(found.get("error_message") or found.get("message") or "").strip()
    return {
        "exit_code": code,
        "error_type": found.get("error_type"),
        "detail": detail,
        "message": (lambda m: m.get(code, m[1]))(exit_messages()),
    }


def failure_reason(execution_log_path: Optional[str]) -> Optional[str]:
    """One line for logs and cards, or ``None`` when the log says nothing."""
    info = describe_client_failure(execution_log_path)
    if info is None:
        return None
    text = f"exit code {info['exit_code']}: {info['message']}"
    if info["detail"]:
        text += f" ({info['detail']})"
    return text
