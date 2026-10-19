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


def _space_free_alias(home: str) -> Optional[str]:
    """Return a whitespace-free symlink to ``home`` (POSIX only), or None."""
    if os.name == "nt":
        return None
    import hashlib
    import tempfile

    digest = hashlib.sha1(home.encode("utf-8")).hexdigest()[:10]
    for root in ("/tmp", tempfile.gettempdir()):
        if not root or " " in root or not os.path.isdir(root):
            continue
        alias = os.path.join(root, f"ysocial-{os.getuid()}-{digest}")
        try:
            if os.path.islink(alias):
                if os.path.realpath(alias) == os.path.realpath(home):
                    return alias
                os.remove(alias)
            elif os.path.exists(alias):
                continue
            os.symlink(home, alias)
            return alias
        except OSError:
            continue
    return None


def ray_safe_cmd(cmd):
    """Rewrite paths under the data folder so they contain no whitespace.

    Ray starts its workers through ``bash -c exec <python> <default_worker.py>``
    without quoting, so an interpreter or package path with a space (the macOS
    default, ``~/Library/Application Support/YSocial``) kills every worker at
    start and simulations never progress. Running the HPC processes through a
    whitespace-free symlink to the data folder keeps ``sys.executable`` and
    ``site-packages`` free of spaces.
    """

    home = os.path.abspath(get_writable_path())
    if " " not in home and "\t" not in home:
        return list(cmd)
    alias = _space_free_alias(home)
    if not alias:
        return list(cmd)
    out = []
    for arg in cmd:
        arg = str(arg)
        if arg == home or arg.startswith(home + os.sep):
            arg = alias + arg[len(home) :]
        out.append(arg)
    return out


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
