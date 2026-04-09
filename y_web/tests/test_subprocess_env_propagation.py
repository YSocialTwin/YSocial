"""
Phase A — Subprocess Environment Propagation tests.

Regression guard: every subprocess.Popen call-site in the simulation and HPC
layers must pass an explicit ``env`` keyword argument so that environment
variables (PYTHONPATH, virtual-env markers, log-file paths) are reliably
forwarded to child processes.

Strategy
--------
* For complex orchestration functions whose dependency chains make full
  integration impractical (start_server, start_hpc_server, start_hpc_client),
  we use *source-code inspection* to assert that ``env=env`` is present in
  every Popen call.  Source inspection is immune to import-chain fragility and
  serves as a permanent regression guard.
* For simpler entry-point scripts (client_runner, server_runner) and the
  simulation/client.py Popen path, we combine import tests and targeted mocks.
"""

import inspect
import re
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper: collect all Popen call-sites from a source string and check env=
# ---------------------------------------------------------------------------


def _popen_calls_missing_env(source: str) -> list[int]:
    """
    Return the 1-based line numbers of subprocess.Popen(...) calls that do NOT
    include ``env=`` in their arguments.  Handles multi-line calls by tracking
    open-paren depth.
    """
    missing = []
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect the start of a Popen call
        if re.search(r"\bsubprocess\.Popen\s*\(", line):
            call_start = i + 1  # 1-based
            # Collect the full call text (may span multiple lines)
            full_call = line
            depth = line.count("(") - line.count(")")
            j = i + 1
            while depth > 0 and j < len(lines):
                full_call += "\n" + lines[j]
                depth += lines[j].count("(") - lines[j].count(")")
                j += 1
            # Check whether env= appears in the collected text
            if not re.search(r"\benv\s*=", full_call):
                missing.append(call_start)
        i += 1
    return missing


# ---------------------------------------------------------------------------
# Source-inspection regression guards (Bugs 1-3)
# ---------------------------------------------------------------------------


def test_hpc_client_all_popen_calls_pass_env():
    """hpc/client.py: every subprocess.Popen call must include env= (Bug 1 guard)."""
    import y_web.src.hpc.client as mod

    missing = _popen_calls_missing_env(inspect.getsource(mod))
    assert (
        not missing
    ), f"subprocess.Popen call(s) in hpc/client.py missing env= at lines: {missing}"


def test_simulation_server_all_popen_calls_pass_env():
    """simulation/server.py: every subprocess.Popen call must include env= (Bug 2 guard)."""
    import y_web.src.simulation.server as mod

    missing = _popen_calls_missing_env(inspect.getsource(mod))
    assert (
        not missing
    ), f"subprocess.Popen call(s) in simulation/server.py missing env= at lines: {missing}"


def test_hpc_server_all_popen_calls_pass_env():
    """hpc/server.py: every subprocess.Popen call must include env= (Bug 3 guard)."""
    import y_web.src.hpc.server as mod

    missing = _popen_calls_missing_env(inspect.getsource(mod))
    assert (
        not missing
    ), f"subprocess.Popen call(s) in hpc/server.py missing env= at lines: {missing}"


def test_simulation_client_all_popen_calls_pass_env():
    """simulation/client.py: every subprocess.Popen call must include env=."""
    import y_web.src.simulation.client as mod

    missing = _popen_calls_missing_env(inspect.getsource(mod))
    assert (
        not missing
    ), f"subprocess.Popen call(s) in simulation/client.py missing env= at lines: {missing}"


# ---------------------------------------------------------------------------
# Source-inspection: env dict must be populated before Popen call
# ---------------------------------------------------------------------------


def test_hpc_client_env_dict_built_before_popen():
    """hpc/client.py: an env dict must be constructed before the Popen calls."""
    import y_web.src.hpc.client as mod

    src = inspect.getsource(mod)
    assert re.search(
        r"env\s*=\s*build_subprocess_env\(", src
    ), "hpc/client.py must build env via build_subprocess_env() before the Popen calls"


def test_simulation_server_sqlite_env_contains_log_file_assignment():
    """simulation/server.py SQLite path: YSERVER_LOG_FILE must be set in env."""
    import y_web.src.simulation.server as mod

    src = inspect.getsource(mod)
    assert (
        '"YSERVER_LOG_FILE"' in src
    ), "simulation/server.py must set YSERVER_LOG_FILE in the subprocess env (Bug 2 fix)"


def test_hpc_server_gunicorn_env_contains_config_assignment():
    """hpc/server.py gunicorn path: YSERVER_CONFIG must be set in env."""
    import y_web.src.hpc.server as mod

    src = inspect.getsource(mod)
    assert (
        'env["YSERVER_CONFIG"]' in src or "env['YSERVER_CONFIG']" in src
    ), "hpc/server.py must assign env['YSERVER_CONFIG'] (Bug 3 fix)"


def test_subprocess_env_helper_strips_werkzeug_reloader_state(monkeypatch):
    """Child processes must not inherit Flask/Werkzeug dev-server socket state."""
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    monkeypatch.setenv("WERKZEUG_SERVER_FD", "0")
    monkeypatch.setenv("WERKZEUG_DEBUG_PIN", "off")
    monkeypatch.setenv("FLASK_RUN_FROM_CLI", "true")

    from y_web.src.simulation.subprocess_env import build_subprocess_env

    env = build_subprocess_env({"Y_SERVER_SUBPROCESS": "1"})

    assert "WERKZEUG_RUN_MAIN" not in env
    assert "WERKZEUG_SERVER_FD" not in env
    assert "WERKZEUG_DEBUG_PIN" not in env
    assert "FLASK_RUN_FROM_CLI" not in env
    assert env["Y_SERVER_SUBPROCESS"] == "1"


def test_subprocess_env_helper_injects_persistent_model_cache(monkeypatch, tmp_path):
    """Child processes must inherit a stable shared model cache configuration."""
    monkeypatch.setenv("YSOCIAL_MODEL_CACHE_DIR", str(tmp_path / "model-cache"))

    from y_web.src.simulation.subprocess_env import build_subprocess_env

    env = build_subprocess_env()

    assert env["YSOCIAL_MODEL_CACHE_DIR"] == str(tmp_path / "model-cache")
    assert env["HF_HOME"].startswith(env["YSOCIAL_MODEL_CACHE_DIR"])
    assert env["TRANSFORMERS_CACHE"].startswith(env["HF_HOME"])
    assert env["HUGGINGFACE_HUB_CACHE"].startswith(env["HF_HOME"])
    assert env["TORCH_HOME"].startswith(env["YSOCIAL_MODEL_CACHE_DIR"])


def test_subprocess_env_helper_uses_persisted_model_cache_setting(monkeypatch, tmp_path):
    """Saved model-cache settings must become the default for new subprocesses."""
    monkeypatch.delenv("YSOCIAL_MODEL_CACHE_DIR", raising=False)

    import y_web.src.system.model_cache as model_cache
    from y_web.src.simulation.subprocess_env import build_subprocess_env

    settings_path = tmp_path / "model_cache_settings.json"
    monkeypatch.setattr(model_cache, "_settings_path", lambda: settings_path)

    saved_root = model_cache.save_model_cache_path(tmp_path / "persisted-cache")
    env = build_subprocess_env()

    assert env["YSOCIAL_MODEL_CACHE_DIR"] == str(saved_root)
    assert env["HF_HOME"].startswith(str(saved_root))


def test_simulation_server_uses_sanitized_subprocess_env():
    """simulation/server.py must sanitize inherited Flask/Werkzeug env vars."""
    import y_web.src.simulation.server as mod

    src = inspect.getsource(mod)
    assert "build_subprocess_env" in src


def test_simulation_client_uses_sanitized_subprocess_env():
    """simulation/client.py must sanitize inherited Flask/Werkzeug env vars."""
    import y_web.src.simulation.client as mod

    src = inspect.getsource(mod)
    assert "build_subprocess_env" in src


def test_hpc_server_uses_sanitized_subprocess_env():
    """hpc/server.py must sanitize inherited Flask/Werkzeug env vars."""
    import y_web.src.hpc.server as mod

    src = inspect.getsource(mod)
    assert "build_subprocess_env" in src


def test_hpc_client_uses_sanitized_subprocess_env():
    """hpc/client.py must sanitize inherited Flask/Werkzeug env vars."""
    import y_web.src.hpc.client as mod

    src = inspect.getsource(mod)
    assert "build_subprocess_env" in src


# ---------------------------------------------------------------------------
# simulation/client.py: PYTHONPATH propagation (behavioral)
# ---------------------------------------------------------------------------


def test_simulation_client_env_contains_pythonpath_source():
    """simulation/client.py must set PYTHONPATH in the env dict it passes to Popen."""
    import y_web.src.simulation.client as mod

    src = inspect.getsource(mod)
    assert (
        "PYTHONPATH" in src
    ), "simulation/client.py must set PYTHONPATH in the subprocess env"


# ---------------------------------------------------------------------------
# client_runner / server_runner sys.path bootstrap (Bug 4 guard)
# ---------------------------------------------------------------------------


def test_client_runner_importable():
    """Importing client_runner must not raise (Bug 4 fix: sys.path bootstrap)."""
    try:
        import y_web.src.simulation.client_runner  # noqa: F401
    except ModuleNotFoundError as exc:
        pytest.fail(f"client_runner import failed: {exc}")


def test_server_runner_importable():
    """Importing server_runner must not raise (Bug 4 fix: sys.path bootstrap)."""
    try:
        import y_web.src.simulation.server_runner  # noqa: F401
    except ModuleNotFoundError as exc:
        pytest.fail(f"server_runner import failed: {exc}")


def test_client_runner_repo_root_on_sys_path():
    """client_runner._REPO_ROOT must appear on sys.path after import."""
    import y_web.src.simulation.client_runner as cr

    assert hasattr(cr, "_REPO_ROOT"), "client_runner must define _REPO_ROOT"
    # _REPO_ROOT must be on sys.path (it is inserted at import time)
    assert (
        cr._REPO_ROOT in sys.path
    ), f"client_runner._REPO_ROOT ({cr._REPO_ROOT!r}) not found on sys.path"


def test_server_runner_repo_root_on_sys_path():
    """server_runner._REPO_ROOT must appear on sys.path after import."""
    import y_web.src.simulation.server_runner as sr

    assert hasattr(sr, "_REPO_ROOT"), "server_runner must define _REPO_ROOT"
    assert (
        sr._REPO_ROOT in sys.path
    ), f"server_runner._REPO_ROOT ({sr._REPO_ROOT!r}) not found on sys.path"
