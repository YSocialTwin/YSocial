"""
Phase 10b validation tests.

Verifies that the ``routes/admin/sub/clients`` god-object file has been
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


def test_clients_is_a_package():
    """The clients module must be a package (directory), not a flat file."""
    pkg = importlib.import_module("y_web.routes.admin.sub.clients")
    assert hasattr(pkg, "__path__"), "clients should be a package with __path__"


def test_sub_modules_exist():
    """All expected sub-modules must be importable."""
    sub_modules = [
        "y_web.routes.admin.sub.clients._blueprint",
        "y_web.routes.admin.sub.clients._helpers",
        "y_web.routes.admin.sub.clients._execution",
        "y_web.routes.admin.sub.clients._crud",
        "y_web.routes.admin.sub.clients._details",
        "y_web.routes.admin.sub.clients._agents",
        "y_web.routes.admin.sub.clients._recsys",
        "y_web.routes.admin.sub.clients._opinion",
    ]
    for mod_name in sub_modules:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"Sub-module {mod_name} could not be imported"


# ---------------------------------------------------------------------------
# 2. Blueprint export
# ---------------------------------------------------------------------------


def test_blueprint_exported_from_package():
    """The package __init__ must export the ``clientsr`` Blueprint."""
    from y_web.routes.admin.sub.clients import clientsr as bp

    assert bp.name == "clientsr", "Blueprint name must remain 'clientsr'"


def test_blueprint_singleton():
    """The Blueprint object from _blueprint.py and __init__.py must be the same."""
    from y_web.routes.admin.sub.clients import clientsr as bp_pkg
    from y_web.routes.admin.sub.clients._blueprint import clientsr as bp_raw

    assert bp_pkg is bp_raw, "All imports should return the same Blueprint object"


def test_routes_are_registered():
    """At least 30 route-decorator functions must be registered on the Blueprint."""
    from y_web.routes.admin.sub.clients import clientsr as bp

    assert (
        len(bp.deferred_functions) >= 30
    ), f"Expected ≥30 registered route handlers, got {len(bp.deferred_functions)}"


# ---------------------------------------------------------------------------
# 3. Key functions accessible from sub-modules
# ---------------------------------------------------------------------------


def test_helpers_module_has_key_functions():
    """Core helper functions must be present in _helpers."""
    from y_web.routes.admin.sub.clients import _helpers

    for fn_name in [
        "_forum_effective_link_share",
        "allocate_topics_by_percentage",
    ]:
        assert hasattr(_helpers, fn_name), f"_helpers missing: {fn_name}"
        assert callable(getattr(_helpers, fn_name)), f"{fn_name} must be callable"


def test_execution_module_has_key_functions():
    """Lifecycle route functions must be in _execution."""
    from y_web.routes.admin.sub.clients import _execution

    for fn_name in [
        "reset_client",
        "extend_simulation",
        "run_client",
        "resume_client",
        "pause_client",
        "stop_client",
    ]:
        assert hasattr(_execution, fn_name), f"_execution missing: {fn_name}"


def test_crud_module_has_key_functions():
    """Main CRUD functions must be in _crud."""
    from y_web.routes.admin.sub.clients import _crud

    for fn_name in [
        "clients",
        "create_client",
        "delete_client",
        "_build_client_creation_context",
    ]:
        assert hasattr(_crud, fn_name), f"_crud missing: {fn_name}"


def test_details_module_has_key_functions():
    """Detail view functions must be in _details."""
    from y_web.routes.admin.sub.clients import _details

    for fn_name in [
        "client_details",
        "get_progress",
        "set_network",
        "upload_network",
        "download_agent_list",
    ]:
        assert hasattr(_details, fn_name), f"_details missing: {fn_name}"


def test_agents_module_has_key_functions():
    """Agent management functions must be in _agents."""
    from y_web.routes.admin.sub.clients import _agents

    for fn_name in [
        "update_agents_activity",
        "reset_agents_activity",
        "update_agent_archetypes",
        "reset_agent_archetypes",
    ]:
        assert hasattr(_agents, fn_name), f"_agents missing: {fn_name}"


def test_recsys_module_has_key_functions():
    """Recommender system functions must be in _recsys."""
    from y_web.routes.admin.sub.clients import _recsys

    for fn_name in [
        "update_recsys",
        "update_llm",
        "_update_recsys_internal",
    ]:
        assert hasattr(_recsys, fn_name), f"_recsys missing: {fn_name}"


def test_opinion_module_has_key_functions():
    """Opinion configuration functions must be in _opinion."""
    from y_web.routes.admin.sub.clients import _opinion

    for fn_name in [
        "opinion_configuration",
        "set_opinion_distributions",
        "_build_topic_segment_distributions",
    ]:
        assert hasattr(_opinion, fn_name), f"_opinion missing: {fn_name}"


# ---------------------------------------------------------------------------
# 4. No duplicate Blueprint definitions
# ---------------------------------------------------------------------------


def test_no_duplicate_blueprint_definitions():
    """No sub-module except _blueprint.py should define a Blueprint named 'clientsr'."""
    from flask import Blueprint

    sub_modules = ["_execution", "_crud", "_details", "_agents", "_recsys", "_opinion"]
    for mod_name in sub_modules:
        mod = importlib.import_module(f"y_web.routes.admin.sub.clients.{mod_name}")
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if isinstance(obj, Blueprint) and attr_name == "clientsr":
                from y_web.routes.admin.sub.clients._blueprint import (
                    clientsr as canonical,
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
    from y_web.routes.admin.sub.clients._blueprint import (
        DISTRIBUTION_SCALE_FACTOR,
    )

    assert isinstance(DISTRIBUTION_SCALE_FACTOR, float)
    assert DISTRIBUTION_SCALE_FACTOR == 10.0
