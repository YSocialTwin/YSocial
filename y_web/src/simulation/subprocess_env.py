"""
Helpers for building subprocess environments for simulation runtimes.
"""

import os
from typing import Dict, Optional

from y_web.src.system.model_cache import get_model_cache_env
from y_web.src.system.path_utils import get_writable_path

_STRIP_ENV_KEYS = (
    "WERKZEUG_RUN_MAIN",
    "WERKZEUG_SERVER_FD",
    "WERKZEUG_DEBUG_PIN",
    "WERKZEUG_DEBUG_TRAP",
    "FLASK_RUN_FROM_CLI",
)


def agent_memory_source_dir() -> Optional[str]:
    """Return the ``src`` folder of the Agent Memory plugin when it is installed.

    The plugin lives in ``external/y_memory_subsystem``; putting its ``src`` on the
    child ``PYTHONPATH`` lets every runtime (clients, ad hoc agents, HPC) import
    ``yclient_memory`` from the plugin, with or without an editable install.
    """

    src = os.path.join(
        get_writable_path(), "external", "y_memory_subsystem", "src"
    )
    if os.path.isdir(os.path.join(src, "yclient_memory")):
        return src
    return None


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

    memory_src = agent_memory_source_dir()
    if memory_src:
        parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
        if memory_src not in parts:
            env["PYTHONPATH"] = os.pathsep.join([*parts, memory_src])

    return env
