"""
Phase 12 validation tests.

Verifies that:
  - ``src/simulation/agent_sampler.py`` exists and exposes the expected public API
  - ``src/simulation/process_runner.py`` still exposes the same names (backward compat)
  - ``src/hpc/log_offset.py`` exists and exposes the expected public API
  - ``src/hpc/log_parser.py`` still exposes offset helpers via re-import (backward compat)
  - Both parent packages (src.simulation, src.hpc) expose the new names
  - Both files are below 900 lines (the Phase 12 goal)
"""

import importlib
import inspect


# ---------------------------------------------------------------------------
# Phase 12a — agent_sampler.py sub-module
# ---------------------------------------------------------------------------


def test_agent_sampler_module_exists():
    """y_web.src.simulation.agent_sampler must be importable."""
    mod = importlib.import_module("y_web.src.simulation.agent_sampler")
    assert mod is not None


def test_agent_sampler_exposes_get_users_per_hour():
    mod = importlib.import_module("y_web.src.simulation.agent_sampler")
    assert callable(getattr(mod, "get_users_per_hour", None))


def test_agent_sampler_exposes_sample_agents():
    mod = importlib.import_module("y_web.src.simulation.agent_sampler")
    assert callable(getattr(mod, "sample_agents", None))


def test_agent_sampler_exposes_ensure_agents_have_archetype():
    mod = importlib.import_module("y_web.src.simulation.agent_sampler")
    assert callable(getattr(mod, "ensure_agents_have_archetype", None))


def test_agent_sampler_exposes_process_agent():
    mod = importlib.import_module("y_web.src.simulation.agent_sampler")
    assert callable(getattr(mod, "process_agent", None))


def test_agent_sampler_all_list():
    """__all__ (if defined) must include the four public functions."""
    mod = importlib.import_module("y_web.src.simulation.agent_sampler")
    expected = {
        "get_users_per_hour",
        "sample_agents",
        "ensure_agents_have_archetype",
        "process_agent",
    }
    if hasattr(mod, "__all__"):
        assert expected.issubset(set(mod.__all__))
    else:
        for name in expected:
            assert hasattr(mod, name)


# ---------------------------------------------------------------------------
# Phase 12a — process_runner.py backward compatibility
# ---------------------------------------------------------------------------


def test_process_runner_still_exposes_get_users_per_hour():
    mod = importlib.import_module("y_web.src.simulation.process_runner")
    fn = getattr(mod, "get_users_per_hour", None)
    assert callable(fn), "process_runner must still expose get_users_per_hour"


def test_process_runner_still_exposes_sample_agents():
    mod = importlib.import_module("y_web.src.simulation.process_runner")
    fn = getattr(mod, "sample_agents", None)
    assert callable(fn), "process_runner must still expose sample_agents"


def test_process_runner_still_exposes_ensure_agents_have_archetype():
    mod = importlib.import_module("y_web.src.simulation.process_runner")
    fn = getattr(mod, "ensure_agents_have_archetype", None)
    assert callable(fn), "process_runner must still expose ensure_agents_have_archetype"


def test_process_runner_still_exposes_process_agent():
    mod = importlib.import_module("y_web.src.simulation.process_runner")
    fn = getattr(mod, "process_agent", None)
    assert callable(fn), "process_runner must still expose process_agent"


def test_process_runner_identity_with_agent_sampler():
    """process_runner symbols must be the same objects as agent_sampler ones."""
    pr = importlib.import_module("y_web.src.simulation.process_runner")
    asm = importlib.import_module("y_web.src.simulation.agent_sampler")
    for name in ("get_users_per_hour", "sample_agents", "ensure_agents_have_archetype", "process_agent"):
        assert getattr(pr, name) is getattr(asm, name), (
            f"process_runner.{name} must be the same object as agent_sampler.{name}"
        )


# ---------------------------------------------------------------------------
# Phase 12a — process_runner.py line-count goal
# ---------------------------------------------------------------------------


def test_process_runner_line_count_reduced():
    """process_runner.py must be under 900 lines after the Phase 12a split."""
    import os

    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "simulation",
        "process_runner.py",
    )
    with open(os.path.abspath(path)) as fh:
        lines = fh.readlines()
    assert len(lines) < 900, (
        f"process_runner.py has {len(lines)} lines; expected < 900 after Phase 12a"
    )


# ---------------------------------------------------------------------------
# Phase 12a — src.simulation package re-exports
# ---------------------------------------------------------------------------


def test_simulation_package_lazy_exports_agent_sampler_names():
    """src.simulation.__init__ must lazily export the agent_sampler public names."""
    pkg = importlib.import_module("y_web.src.simulation")
    for name in ("get_users_per_hour", "sample_agents", "ensure_agents_have_archetype", "process_agent"):
        fn = getattr(pkg, name, None)
        assert callable(fn), f"y_web.src.simulation.{name} not accessible"


# ---------------------------------------------------------------------------
# Phase 12b — log_offset.py sub-module
# ---------------------------------------------------------------------------


def test_log_offset_module_exists():
    """y_web.src.hpc.log_offset must be importable."""
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert mod is not None


def test_log_offset_exposes_ensure_session_clean():
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert callable(getattr(mod, "_ensure_session_clean", None))


def test_log_offset_exposes_commit_with_retry():
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert callable(getattr(mod, "_commit_with_retry", None))


def test_log_offset_exposes_get_log_file_offset():
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert callable(getattr(mod, "get_log_file_offset", None))


def test_log_offset_exposes_update_log_file_offset():
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert callable(getattr(mod, "update_log_file_offset", None))


def test_log_offset_exposes_reset_hpc_client_metrics():
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert callable(getattr(mod, "reset_hpc_client_metrics", None))


def test_log_offset_exposes_reset_hpc_server_metrics():
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert callable(getattr(mod, "reset_hpc_server_metrics", None))


def test_log_offset_exposes_max_retries():
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert hasattr(mod, "MAX_RETRIES"), "log_offset must define MAX_RETRIES"


def test_log_offset_exposes_retry_delay():
    mod = importlib.import_module("y_web.src.hpc.log_offset")
    assert hasattr(mod, "RETRY_DELAY"), "log_offset must define RETRY_DELAY"


# ---------------------------------------------------------------------------
# Phase 12b — log_parser.py backward compatibility
# ---------------------------------------------------------------------------


def test_log_parser_still_exposes_get_log_file_offset():
    mod = importlib.import_module("y_web.src.hpc.log_parser")
    fn = getattr(mod, "get_log_file_offset", None)
    assert callable(fn), "log_parser must still expose get_log_file_offset"


def test_log_parser_still_exposes_update_log_file_offset():
    mod = importlib.import_module("y_web.src.hpc.log_parser")
    fn = getattr(mod, "update_log_file_offset", None)
    assert callable(fn), "log_parser must still expose update_log_file_offset"


def test_log_parser_still_exposes_reset_hpc_client_metrics():
    mod = importlib.import_module("y_web.src.hpc.log_parser")
    fn = getattr(mod, "reset_hpc_client_metrics", None)
    assert callable(fn), "log_parser must still expose reset_hpc_client_metrics"


def test_log_parser_still_exposes_reset_hpc_server_metrics():
    mod = importlib.import_module("y_web.src.hpc.log_parser")
    fn = getattr(mod, "reset_hpc_server_metrics", None)
    assert callable(fn), "log_parser must still expose reset_hpc_server_metrics"


def test_log_parser_identity_with_log_offset():
    """log_parser symbols must be the same objects as log_offset ones."""
    lp = importlib.import_module("y_web.src.hpc.log_parser")
    lo = importlib.import_module("y_web.src.hpc.log_offset")
    for name in (
        "get_log_file_offset",
        "update_log_file_offset",
        "reset_hpc_client_metrics",
        "reset_hpc_server_metrics",
        "_ensure_session_clean",
        "_commit_with_retry",
    ):
        assert getattr(lp, name) is getattr(lo, name), (
            f"log_parser.{name} must be the same object as log_offset.{name}"
        )


# ---------------------------------------------------------------------------
# Phase 12b — log_parser.py line-count goal
# ---------------------------------------------------------------------------


def test_log_parser_line_count_reduced():
    """log_parser.py must be under 900 lines after the Phase 12b split."""
    import os

    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "hpc",
        "log_parser.py",
    )
    with open(os.path.abspath(path)) as fh:
        lines = fh.readlines()
    assert len(lines) < 900, (
        f"log_parser.py has {len(lines)} lines; expected < 900 after Phase 12b"
    )


# ---------------------------------------------------------------------------
# Phase 12b — src.hpc package re-exports
# ---------------------------------------------------------------------------


def test_hpc_package_exposes_log_offset_names():
    """src.hpc.__init__ must export the log_offset public names."""
    pkg = importlib.import_module("y_web.src.hpc")
    for name in (
        "get_log_file_offset",
        "update_log_file_offset",
        "reset_hpc_client_metrics",
        "reset_hpc_server_metrics",
    ):
        fn = getattr(pkg, name, None)
        assert callable(fn), f"y_web.src.hpc.{name} not accessible"


# ---------------------------------------------------------------------------
# Regression — existing public names still accessible
# ---------------------------------------------------------------------------


def test_hpc_package_still_exposes_log_parser_names():
    pkg = importlib.import_module("y_web.src.hpc")
    for name in (
        "parse_server_log_incremental",
        "parse_client_log_incremental",
        "get_rotating_log_files",
        "has_server_log_files",
    ):
        fn = getattr(pkg, name, None)
        assert callable(fn), f"y_web.src.hpc.{name} no longer accessible after Phase 12"


def test_process_runner_still_exposes_start_client_process():
    mod = importlib.import_module("y_web.src.simulation.process_runner")
    fn = getattr(mod, "start_client_process", None)
    assert callable(fn), "process_runner must still expose start_client_process"


def test_process_runner_still_exposes_run_simulation():
    mod = importlib.import_module("y_web.src.simulation.process_runner")
    fn = getattr(mod, "run_simulation", None)
    assert callable(fn), "process_runner must still expose run_simulation"
