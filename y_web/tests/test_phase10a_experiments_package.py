"""
Phase 10a validation tests.

Verifies that the ``routes/admin/sub/experiments`` god-object file has been
correctly split into a proper Python sub-package while maintaining full
backward compatibility.
"""

import importlib
import inspect
import pytest
pytestmark = pytest.mark.unit



# ---------------------------------------------------------------------------
# 1. Package structure
# ---------------------------------------------------------------------------


def test_experiments_is_a_package():
    """The experiments module must be a package (directory), not a flat file."""
    # Use importlib to get the actual package module (not the re-exported Blueprint)
    pkg = importlib.import_module("y_web.routes.admin.sub.experiments")
    # Packages have a __path__; flat modules do not
    assert hasattr(pkg, "__path__"), "experiments should be a package with __path__"


def test_sub_modules_exist():
    """All expected sub-modules must be importable."""
    sub_modules = [
        "y_web.routes.admin.sub.experiments._blueprint",
        "y_web.routes.admin.sub.experiments._helpers",
        "y_web.routes.admin.sub.experiments._crud",
        "y_web.routes.admin.sub.experiments._data",
        "y_web.routes.admin.sub.experiments._hpc",
        "y_web.routes.admin.sub.experiments._feeds",
        "y_web.routes.admin.sub.experiments._notifications",
        "y_web.routes.admin.sub.experiments._schedule",
        "y_web.routes.admin.sub.experiments._opinion",
    ]
    for mod_name in sub_modules:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"Sub-module {mod_name} could not be imported"


# ---------------------------------------------------------------------------
# 2. Blueprint export
# ---------------------------------------------------------------------------


def test_blueprint_exported_from_package():
    """The package __init__ must export the ``experiments`` Blueprint."""
    from y_web.routes.admin.sub.experiments import experiments as bp

    assert bp.name == "experiments", "Blueprint name must remain 'experiments'"


def test_blueprint_singleton():
    """The Blueprint object from _blueprint.py and __init__.py must be the same."""
    from y_web.routes.admin.sub.experiments import experiments as bp_pkg
    from y_web.routes.admin.sub.experiments._blueprint import experiments as bp_raw

    assert bp_pkg is bp_raw, "All imports should return the same Blueprint object"


def test_routes_are_registered():
    """At least 100 route-decorator functions must be registered on the Blueprint."""
    from y_web.routes.admin.sub.experiments import experiments as bp

    assert len(bp.deferred_functions) >= 100, (
        f"Expected ≥100 registered route handlers, got {len(bp.deferred_functions)}"
    )


# ---------------------------------------------------------------------------
# 3. Key functions accessible from sub-modules
# ---------------------------------------------------------------------------


def test_helpers_module_has_key_functions():
    """Core helper functions must be present in _helpers."""
    from y_web.routes.admin.sub.experiments import _helpers

    for fn_name in [
        "_current_admin_user",
        "_current_admin_user_or_none",
        "_notifications_temp_data_dir",
        "_experiment_has_started_once",
        "_load_forum_experiment_context",
        "_serialize_download_notification",
        "get_experiment_uid_from_db_name",
        "get_suggested_port",
        "is_port_free",
        "is_port_valid",
    ]:
        assert hasattr(_helpers, fn_name), f"_helpers missing: {fn_name}"
        assert callable(getattr(_helpers, fn_name)), f"{fn_name} must be callable"


def test_schedule_module_has_key_functions():
    """Schedule-related functions must be in _schedule."""
    from y_web.routes.admin.sub.experiments import _schedule

    for fn_name in [
        "start_schedule",
        "stop_schedule",
        "check_schedule_progress",
        "get_schedule_groups",
        "create_schedule_group",
        "add_schedule_log",
    ]:
        assert hasattr(_schedule, fn_name), f"_schedule missing: {fn_name}"


def test_opinion_module_has_key_functions():
    """Opinion-related functions must be in _opinion."""
    from y_web.routes.admin.sub.experiments import _opinion

    for fn_name in [
        "opinion_evolution",
        "opinion_evolution_data",
        "opinion_groups_data",
        "generate_group_trends_data",
    ]:
        assert hasattr(_opinion, fn_name), f"_opinion missing: {fn_name}"


def test_feeds_module_has_key_functions():
    """Feed-related functions must be in _feeds."""
    from y_web.routes.admin.sub.experiments import _feeds

    for fn_name in [
        "rss_feeds",
        "update_rss_feeds",
        "image_feeds",
        "embedding_settings",
        "feed_limits",
    ]:
        assert hasattr(_feeds, fn_name), f"_feeds missing: {fn_name}"


def test_notifications_module_has_key_functions():
    """Notification/download functions must be in _notifications."""
    from y_web.routes.admin.sub.experiments import _notifications

    for fn_name in [
        "download_experiment_file",
        "download_notifications_page",
        "download_notifications_data",
    ]:
        assert hasattr(_notifications, fn_name), f"_notifications missing: {fn_name}"


def test_hpc_module_has_key_functions():
    """HPC-specific functions must be in _hpc."""
    from y_web.routes.admin.sub.experiments import _hpc

    for fn_name in [
        "get_hpc_monitor_settings",
        "update_hpc_monitor_settings",
        "update_remote_server",
    ]:
        assert hasattr(_hpc, fn_name), f"_hpc missing: {fn_name}"


def test_crud_module_has_key_functions():
    """Main CRUD functions must be in _crud."""
    from y_web.routes.admin.sub.experiments import _crud

    for fn_name in [
        "create_experiment",
        "delete_simulation",
        "upload_experiment",
        "settings",
        "visibility_settings",
        "copy_experiment",
    ]:
        assert hasattr(_crud, fn_name), f"_crud missing: {fn_name}"


def test_data_module_has_key_functions():
    """Data view functions must be in _data."""
    from y_web.routes.admin.sub.experiments import _data

    for fn_name in [
        "experiments_data",
        "experiment_details",
        "experiment_logs",
        "experiment_trends",
    ]:
        assert hasattr(_data, fn_name), f"_data missing: {fn_name}"


# ---------------------------------------------------------------------------
# 4. No duplicate Blueprint definitions
# ---------------------------------------------------------------------------


def test_no_duplicate_blueprint_definitions():
    """No sub-module except _blueprint.py should define a Blueprint named 'experiments'."""
    from flask import Blueprint

    sub_modules = ["_crud", "_data", "_hpc", "_feeds", "_notifications", "_schedule", "_opinion"]
    for mod_name in sub_modules:
        mod = importlib.import_module(f"y_web.routes.admin.sub.experiments.{mod_name}")
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if isinstance(obj, Blueprint) and attr_name == "experiments":
                # It must be the same shared instance (imported from _blueprint)
                from y_web.routes.admin.sub.experiments._blueprint import (
                    experiments as canonical,
                )
                assert obj is canonical, (
                    f"{mod_name}.{attr_name} is a different Blueprint object – "
                    "only _blueprint.py should define it"
                )


# ---------------------------------------------------------------------------
# 5. Constants accessible
# ---------------------------------------------------------------------------


def test_constants_in_blueprint_module():
    """Module-level constants must be present in _blueprint."""
    from y_web.routes.admin.sub.experiments._blueprint import (
        DEFAULT_FEED_LIMITS,
        DEFAULT_FORUM_AVATAR_SETTINGS,
        MAX_HPC_PER_GROUP,
        OPINION_CACHE_EXPIRY_MINUTES,
    )

    assert isinstance(OPINION_CACHE_EXPIRY_MINUTES, int)
    assert isinstance(MAX_HPC_PER_GROUP, int)
    assert isinstance(DEFAULT_FEED_LIMITS, dict)
    assert isinstance(DEFAULT_FORUM_AVATAR_SETTINGS, dict)
