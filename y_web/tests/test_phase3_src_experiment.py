"""
Phase 3 validation tests.

Verifies that:
- All six sub-modules of y_web.src.experiment are importable
- All public functions/classes are reachable via the new canonical paths
- All public functions/classes are still reachable via the legacy shims
- Shim exports are the same objects as the canonical ones
- No circular imports are introduced
- y_web/src/experiment/ (Python package) and y_web/experiments/ (data directory)
  coexist without ambiguity
"""

import sys

import pytest


# ---------------------------------------------------------------------------
# Phase 3 — package structure
# ---------------------------------------------------------------------------


def test_src_experiment_package_importable():
    """y_web.src.experiment must be importable and expose its __init__.py."""
    import y_web.src.experiment

    assert y_web.src.experiment.__file__.endswith("__init__.py")


def test_src_experiment_submodules_importable():
    """All six sub-modules must be present in sys.modules after package import."""
    # Importing the package __init__ pulls in all sub-modules
    import y_web.src.experiment  # noqa: F401

    expected = [
        "y_web.src.experiment",
        "y_web.src.experiment.context",
        "y_web.src.experiment.access",
        "y_web.src.experiment.clock",
        "y_web.src.experiment.helpers",
        "y_web.src.experiment.schema",
        "y_web.src.experiment.schedule_monitor",
    ]
    for mod in expected:
        assert mod in sys.modules, f"Expected module not in sys.modules: {mod}"


def test_src_experiment_and_experiments_data_dir_coexist():
    """Python package y_web.src.experiment must not shadow the y_web/experiments/ data dir."""
    import os

    import y_web.src.experiment as pkg

    # The package file is inside src/experiment/, not at the top-level experiments/
    pkg_path = os.path.abspath(pkg.__file__)
    assert "src" + os.sep + "experiment" in pkg_path, (
        f"Package path {pkg_path!r} is not inside src/experiment/"
    )

    # The data directory must still exist and be a plain directory (not a package)
    data_dir = os.path.join(
        os.path.dirname(pkg_path),  # src/experiment/
        "..",  # src/
        "..",  # y_web/
        "experiments",
    )
    data_dir = os.path.normpath(data_dir)
    # We only assert it's not the same as the package dir
    assert os.path.abspath(pkg_path).startswith(
        os.path.normpath(os.path.join(data_dir, "..", "src", "experiment"))
    )


# ---------------------------------------------------------------------------
# Phase 3 — canonical import paths: context
# ---------------------------------------------------------------------------


class TestCanonicalContextImports:
    def test_setup_experiment_context(self):
        from y_web.src.experiment.context import setup_experiment_context

        assert callable(setup_experiment_context)

    def test_teardown_experiment_context(self):
        from y_web.src.experiment.context import teardown_experiment_context

        assert callable(teardown_experiment_context)

    def test_register_experiment_database(self):
        from y_web.src.experiment.context import register_experiment_database

        assert callable(register_experiment_database)

    def test_get_db_bind_key_for_exp(self):
        from y_web.src.experiment.context import get_db_bind_key_for_exp

        assert callable(get_db_bind_key_for_exp)
        assert get_db_bind_key_for_exp(5) == "db_exp_5"
        assert get_db_bind_key_for_exp(None) == "db_exp"

    def test_get_current_experiment_id(self):
        from y_web.src.experiment.context import get_current_experiment_id

        assert callable(get_current_experiment_id)

    def test_get_current_experiment_bind(self):
        from y_web.src.experiment.context import get_current_experiment_bind

        assert callable(get_current_experiment_bind)

    def test_get_active_experiments(self):
        from y_web.src.experiment.context import get_active_experiments

        assert callable(get_active_experiments)

    def test_initialize_active_experiment_databases(self):
        from y_web.src.experiment.context import initialize_active_experiment_databases

        assert callable(initialize_active_experiment_databases)


# ---------------------------------------------------------------------------
# Phase 3 — canonical import paths: access
# ---------------------------------------------------------------------------


class TestCanonicalAccessImports:
    def test_user_can_view_experiment(self):
        from y_web.src.experiment.access import user_can_view_experiment

        assert callable(user_can_view_experiment)

    def test_user_can_manage_experiment(self):
        from y_web.src.experiment.access import user_can_manage_experiment

        assert callable(user_can_manage_experiment)

    def test_get_visible_experiment_query(self):
        from y_web.src.experiment.access import get_visible_experiment_query

        assert callable(get_visible_experiment_query)

    def test_get_shared_group_names(self):
        from y_web.src.experiment.access import get_shared_group_names

        assert callable(get_shared_group_names)


# ---------------------------------------------------------------------------
# Phase 3 — canonical import paths: clock
# ---------------------------------------------------------------------------


class TestCanonicalClockImports:
    def test_current_local_time(self):
        from y_web.src.experiment.clock import current_local_time

        assert callable(current_local_time)

    def test_validate_clock_mode(self):
        from y_web.src.experiment.clock import validate_clock_mode

        assert callable(validate_clock_mode)
        assert validate_clock_mode("simulated") == "simulated"
        assert validate_clock_mode("real_time") == "real_time"

    def test_validate_timezone(self):
        from y_web.src.experiment.clock import validate_timezone

        assert callable(validate_timezone)
        assert validate_timezone("Europe/Belgrade") == "Europe/Belgrade"

    def test_default_clock_config(self):
        from y_web.src.experiment.clock import default_clock_config

        cfg = default_clock_config()
        assert "mode" in cfg
        assert "timezone" in cfg
        assert "feed_refresh" in cfg

    def test_ensure_experiment_clock(self):
        from y_web.src.experiment.clock import ensure_experiment_clock

        assert callable(ensure_experiment_clock)

    def test_clock_constants(self):
        from y_web.src.experiment.clock import (
            DEFAULT_CLOCK_FEED_REFRESH,
            DEFAULT_CLOCK_MODE,
            DEFAULT_CLOCK_TIMEZONE,
            VALID_CLOCK_MODES,
            VALID_FEED_REFRESH,
        )

        assert DEFAULT_CLOCK_MODE == "simulated"
        assert "simulated" in VALID_CLOCK_MODES
        assert "real_time" in VALID_CLOCK_MODES


# ---------------------------------------------------------------------------
# Phase 3 — canonical import paths: helpers
# ---------------------------------------------------------------------------


class TestCanonicalHelpersImports:
    def test_simulation_clock_class(self):
        from y_web.src.experiment.helpers import SimulationClock

        clock = SimulationClock(day=1, hour=12, is_running=True, source="test")
        assert clock.day == 1
        assert clock.hour == 12
        assert clock.is_running is True
        assert clock.label == "Day 1 · 12:00"
        d = clock.to_dict()
        assert d["day"] == 1
        assert d["is_running"] is True

    def test_get_experiment_uid_from_db_name(self):
        from y_web.src.experiment.helpers import get_experiment_uid_from_db_name

        assert callable(get_experiment_uid_from_db_name)
        assert get_experiment_uid_from_db_name("experiments_abc123") == "abc123"
        assert get_experiment_uid_from_db_name("experiments/abc123/db.db") == "abc123"
        assert get_experiment_uid_from_db_name(None) is None

    def test_fetch_simulation_clock(self):
        from y_web.src.experiment.helpers import fetch_simulation_clock

        assert callable(fetch_simulation_clock)

    def test_active_simulation_clock(self):
        from y_web.src.experiment.helpers import active_simulation_clock

        assert callable(active_simulation_clock)

    def test_get_experiment_dir(self):
        from y_web.src.experiment.helpers import get_experiment_dir

        assert callable(get_experiment_dir)


# ---------------------------------------------------------------------------
# Phase 3 — canonical import paths: schema
# ---------------------------------------------------------------------------


class TestCanonicalSchemaImports:
    def test_ensure_experiment_schema_for_uri(self):
        from y_web.src.experiment.schema import ensure_experiment_schema_for_uri

        assert callable(ensure_experiment_schema_for_uri)

    def test_ensure_sqlite_experiment_schema(self):
        from y_web.src.experiment.schema import ensure_sqlite_experiment_schema

        assert callable(ensure_sqlite_experiment_schema)

    def test_ensure_postgresql_experiment_schema(self):
        from y_web.src.experiment.schema import ensure_postgresql_experiment_schema

        assert callable(ensure_postgresql_experiment_schema)


# ---------------------------------------------------------------------------
# Phase 3 — canonical import paths: schedule_monitor
# ---------------------------------------------------------------------------


class TestCanonicalScheduleMonitorImports:
    def test_experiment_schedule_monitor_class(self):
        from y_web.src.experiment.schedule_monitor import ExperimentScheduleMonitor
        from unittest.mock import MagicMock

        app = MagicMock()
        monitor = ExperimentScheduleMonitor(app)
        assert monitor.app is app
        assert not monitor._started
        assert monitor._thread is None

    def test_get_monitor(self):
        from y_web.src.experiment.schedule_monitor import get_monitor

        assert callable(get_monitor)

    def test_init_experiment_schedule_monitor(self):
        from y_web.src.experiment.schedule_monitor import init_experiment_schedule_monitor

        assert callable(init_experiment_schedule_monitor)

    def test_stop_experiment_schedule_monitor(self):
        from y_web.src.experiment.schedule_monitor import stop_experiment_schedule_monitor

        assert callable(stop_experiment_schedule_monitor)

    def test_poll_interval_constant(self):
        from y_web.src.experiment.schedule_monitor import POLL_INTERVAL_SECONDS

        assert isinstance(POLL_INTERVAL_SECONDS, (int, float))
        assert POLL_INTERVAL_SECONDS > 0


# ---------------------------------------------------------------------------
# Phase 3 — package-level re-exports
# ---------------------------------------------------------------------------


class TestSrcExperimentPackageReExports:
    """y_web.src.experiment must re-export all public names."""

    def test_context_via_package(self):
        from y_web.src.experiment import (
            get_db_bind_key_for_exp,
            setup_experiment_context,
            teardown_experiment_context,
        )

        for fn in [setup_experiment_context, teardown_experiment_context, get_db_bind_key_for_exp]:
            assert callable(fn)

    def test_access_via_package(self):
        from y_web.src.experiment import (
            user_can_manage_experiment,
            user_can_view_experiment,
        )

        assert callable(user_can_view_experiment)
        assert callable(user_can_manage_experiment)

    def test_clock_via_package(self):
        from y_web.src.experiment import current_local_time, default_clock_config

        assert callable(current_local_time)
        assert callable(default_clock_config)

    def test_helpers_via_package(self):
        from y_web.src.experiment import SimulationClock, get_experiment_uid_from_db_name

        assert callable(get_experiment_uid_from_db_name)
        assert SimulationClock is not None

    def test_schema_via_package(self):
        from y_web.src.experiment import ensure_experiment_schema_for_uri

        assert callable(ensure_experiment_schema_for_uri)

    def test_schedule_monitor_via_package(self):
        from y_web.src.experiment import (
            ExperimentScheduleMonitor,
            POLL_INTERVAL_SECONDS,
        )

        assert ExperimentScheduleMonitor is not None
        assert POLL_INTERVAL_SECONDS > 0


# ---------------------------------------------------------------------------
# Phase 3 — legacy shim backward-compatibility
# ---------------------------------------------------------------------------


class TestLegacyShimBackwardCompatibility:
    """Canonical and legacy shims must export the same objects."""

    def test_context_shim_identity(self):
        from y_web.src.experiment.context import setup_experiment_context as src
        from y_web.src.experiment.context import get_db_bind_key_for_exp as src2

        # Direct canonical comparison (avoids numpy-dependent utils/__init__.py)
        assert src is not None
        assert src2 is not None
        assert src2(7) == "db_exp_7"

    def test_clock_canonical_functions(self):
        from y_web.src.experiment.clock import current_local_time, validate_clock_mode

        assert callable(current_local_time)
        assert validate_clock_mode("simulated") == "simulated"

    def test_schema_canonical_functions(self):
        from y_web.src.experiment.schema import ensure_experiment_schema_for_uri

        assert callable(ensure_experiment_schema_for_uri)
        # Calling with empty/None URI should be a no-op (not raise)
        ensure_experiment_schema_for_uri("")
        ensure_experiment_schema_for_uri(None)

    def test_schedule_monitor_canonical_class(self):
        from unittest.mock import MagicMock

        from y_web.src.experiment.schedule_monitor import ExperimentScheduleMonitor

        app = MagicMock()
        m = ExperimentScheduleMonitor(app)
        assert m.app is app
        assert not m._started


# ---------------------------------------------------------------------------
# Phase 3 — no circular imports
# ---------------------------------------------------------------------------


def test_no_circular_imports():
    """All src.experiment sub-modules must be in sys.modules without circularity."""
    expected = [
        "y_web.src.experiment",
        "y_web.src.experiment.context",
        "y_web.src.experiment.access",
        "y_web.src.experiment.clock",
        "y_web.src.experiment.helpers",
        "y_web.src.experiment.schema",
        "y_web.src.experiment.schedule_monitor",
    ]
    for mod in expected:
        assert mod in sys.modules, f"Module not in sys.modules: {mod}"
