"""
Helpers for building subprocess environments for simulation runtimes.
"""

import os
from typing import Dict, Optional

from y_web.src.system.model_cache import get_model_cache_env

_STRIP_ENV_KEYS = (
    "WERKZEUG_RUN_MAIN",
    "WERKZEUG_SERVER_FD",
    "WERKZEUG_DEBUG_PIN",
    "WERKZEUG_DEBUG_TRAP",
    "FLASK_RUN_FROM_CLI",
)

def build_subprocess_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Return a sanitized child-process environment.

    Flask/Werkzeug dev-server state must not leak into spawned server or client
    processes. Inheriting reloader variables such as WERKZEUG_SERVER_FD can make
    a child process try to reuse the parent app's listening socket, which breaks
    unrelated subprocesses such as YServerReddit.
    """

    env = os.environ.copy()
    for key in _STRIP_ENV_KEYS:
        env.pop(key, None)

    env.update(get_model_cache_env())

    if extra:
        env.update(extra)

    return env
