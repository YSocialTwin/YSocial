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
    """hpc/client.py: an env dict (``env = os.environ.copy()``) must be constructed."""
    import y_web.src.hpc.client as mod

    src = inspect.getsource(mod)
    assert re.search(
        r"env\s*=\s*os\.environ\.copy\(\)", src
    ), "hpc/client.py must build env = os.environ.copy() before the Popen calls"


def test_simulation_server_sqlite_env_contains_log_file_assignment():
    """simulation/server.py SQLite path: YSERVER_LOG_FILE must be set in env."""
    import y_web.src.simulation.server as mod

    src = inspect.getsource(mod)
    assert (
        'env["YSERVER_LOG_FILE"]' in src or "env['YSERVER_LOG_FILE']" in src
    ), "simulation/server.py must assign env['YSERVER_LOG_FILE'] (Bug 2 fix)"


def test_hpc_server_gunicorn_env_contains_config_assignment():
    """hpc/server.py gunicorn path: YSERVER_CONFIG must be set in env."""
    import y_web.src.hpc.server as mod

    src = inspect.getsource(mod)
    assert (
        'env["YSERVER_CONFIG"]' in src or "env['YSERVER_CONFIG']" in src
    ), "hpc/server.py must assign env['YSERVER_CONFIG'] (Bug 3 fix)"


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
