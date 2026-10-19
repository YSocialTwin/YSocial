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


# Ray >= 2.5x enables token authentication by default and keeps the token in
# ``~/.ray/auth_token``. YSocial runs the Ray cluster, the HPC server/client and
# the web process on the same machine (loopback only), so every process must
# agree on one mode; a mismatch ends in ``InvalidAuthToken`` and idle agents.
RAY_AUTH_ENV = {"RAY_AUTH_MODE": "disabled"}


def apply_ray_auth_defaults(env=None):
    """Disable Ray token auth unless the user chose a mode explicitly."""
    target = os.environ if env is None else env
    for key, value in RAY_AUTH_ENV.items():
        if not target.get("RAY_AUTH_MODE") and not target.get("RAY_AUTH_TOKEN"):
            target[key] = value
    return target


# the web process itself talks to Ray too (stop/interview endpoints)
apply_ray_auth_defaults()


def agent_memory_source_dir() -> Optional[str]:
    """Return the ``src`` folder of the Agent Memory plugin when it is installed.

    The plugin lives in ``external/y_memory_subsystem``; putting its ``src`` on the
    child ``PYTHONPATH`` lets every runtime (clients, ad hoc agents, HPC) import
    ``yclient_memory`` from the plugin, with or without an editable install.
    """

    src = os.path.join(get_writable_path(), "external", "y_memory_subsystem", "src")
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

    apply_ray_auth_defaults(env)
    env.update(get_model_cache_env())
    # every child process resolves the same data folder as the parent
    env["YSOCIAL_HOME"] = get_writable_path()

    if extra:
        env.update(extra)

    memory_src = agent_memory_source_dir()
    if memory_src:
        parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
        if memory_src not in parts:
            env["PYTHONPATH"] = os.pathsep.join([*parts, memory_src])

    return env
