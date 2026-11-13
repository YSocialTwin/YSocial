"""Is the optional YFederation plugin (``ysocial_federation``) available?

The SDK is not a pip dependency: it lives in ``external/YFederation``. A YSocial installation without it must keep
running classic (non federated) simulations exactly as before, so nothing at module level of YWeb imports the SDK.
This module is the single place that answers "can World Simulation features be used?":

* ``sdk_available()``  cached answer for the web process (menu entry, routes, badges);
* ``sdk_reason()``     why not, in English (for logs and for the message shown to the admin);
* ``require_sdk()``    raises a ``WorldSimulationError`` (code ``sdk_missing``) up-front;
* ``child_import_check()`` the same check done the way the servers and clients will see it (their environment).
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import threading
import time
from typing import Optional, Tuple

SDK_MODULE = "ysocial_federation"
MISSING_MESSAGE = "The YFederation plugin is not installed"
NEGATIVE_TTL = 30.0  # seconds a negative answer is trusted (the plugin may be installed while YWeb runs)

_lock = threading.Lock()
_cache: dict = {"ok": None, "reason": "", "at": 0.0}


def _probe() -> Tuple[bool, str]:
    """Import the SDK in this process; when it is not on ``sys.path`` try the folder of the plugin first."""
    try:
        importlib.import_module(SDK_MODULE)
        return True, ""
    except (
        Exception
    ) as exc:  # noqa: BLE001 - ImportError, but also a broken install must never raise here
        first = exc
    try:
        from y_web.src.simulation.subprocess_env import federation_sdk_dir

        folder = federation_sdk_dir()
    except Exception:  # noqa: BLE001
        folder = None
    if folder:
        if folder not in sys.path:
            sys.path.append(folder)
        importlib.invalidate_caches()
        try:
            importlib.import_module(SDK_MODULE)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            first = exc
    return False, f"{MISSING_MESSAGE} ({type(first).__name__}: {first})"


def sdk_available(refresh: bool = False) -> bool:
    """True when ``ysocial_federation`` can be imported by the web process (cached)."""
    now = time.monotonic()
    with _lock:
        if (
            not refresh
            and _cache["ok"] is not None
            and (_cache["ok"] or now - _cache["at"] < NEGATIVE_TTL)
        ):
            return bool(_cache["ok"])
        ok, reason = _probe()
        _cache.update(ok=ok, reason=reason, at=now)
        return ok


def sdk_reason() -> str:
    """Empty when the SDK is available, otherwise the English reason."""
    sdk_available()
    return _cache["reason"]


def reset_cache() -> None:
    with _lock:
        _cache.update(ok=None, reason="", at=0.0)


def require_sdk() -> None:
    """Raise a ``WorldSimulationError`` with code ``sdk_missing`` when the plugin is not available."""
    if not sdk_available():
        from y_web.src.federation.service import WorldSimulationError

        raise WorldSimulationError(
            {"code": "sdk_missing", "message": sdk_reason() or MISSING_MESSAGE}
        )


def child_import_check(
    timeout: float = 20.0, env: Optional[dict] = None
) -> Tuple[bool, str]:
    """Can a server or client of a member import the SDK? Runs ``python -c 'import ysocial_federation'``.

    It uses the environment the member processes get (``build_subprocess_env``: the PYTHONPATH carries the plugin
    folder). Returns ``(ok, message)``; ``message`` is the last line of the error when it fails. A bundled
    executable (no ``python`` interpreter to ask) is trusted."""
    if "python" not in os.path.basename(sys.executable).lower():
        return True, ""
    if env is None:
        from y_web.src.simulation.subprocess_env import build_subprocess_env

        env = build_subprocess_env()
    try:
        done = subprocess.run(
            [sys.executable, "-c", f"import {SDK_MODULE}"],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"importing {SDK_MODULE} took more than {int(timeout)} s"
    except OSError as exc:
        return False, str(exc)
    if done.returncode == 0:
        return True, ""
    lines = [l for l in (done.stderr or "").strip().splitlines() if l.strip()]
    return False, lines[-1] if lines else f"exit code {done.returncode}"


def require_child_sdk() -> None:
    """``WorldSimulationError`` (code ``sdk_not_importable``) when the member processes could not import the SDK."""
    ok, message = child_import_check()
    if not ok:
        from y_web.src.federation.service import WorldSimulationError

        raise WorldSimulationError({"code": "sdk_not_importable", "message": message})
