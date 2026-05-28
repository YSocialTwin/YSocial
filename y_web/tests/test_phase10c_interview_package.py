"""Structural validation tests for Phase 10c: interview sub-package."""

import importlib
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_interview_importable():
    import y_web.routes.api.interview as pkg

    assert isinstance(pkg, types.ModuleType)


def test_api_interview_blueprint():
    from flask import Blueprint

    from y_web.routes.api import interview

    assert isinstance(interview.api_interview, Blueprint)
    assert interview.api_interview.name == "api_interview"
    assert interview.api_interview.url_prefix == "/api/interview"


def test_pick_listening_port_accessible():
    from y_web.routes.api import interview

    assert callable(interview._pick_listening_port)


def test_server_base_url_accessible():
    from y_web.routes.api import interview

    assert callable(interview._server_base_url)


def test_discover_runtime_port_accessible():
    from y_web.routes.api import interview

    assert callable(interview._discover_runtime_port_for_experiment_process)


def test_listening_ports_for_pid_accessible():
    from y_web.routes.api import interview

    assert callable(interview._listening_ports_for_pid)


def test_get_latest_experiment_runtime_accessible():
    from y_web.routes.api import interview

    assert callable(interview._get_latest_experiment_runtime)


def test_submodules_exist():
    for mod_name in [
        "_blueprint",
        "_helpers",
        "_server",
        "_memory",
        "_facts",
        "_llm",
        "_routes",
    ]:
        mod = importlib.import_module(f"y_web.routes.api.interview.{mod_name}")
        assert isinstance(mod, types.ModuleType), f"{mod_name} not importable"


def test_is_package():
    import y_web.routes.api.interview as pkg

    assert hasattr(pkg, "__path__"), "interview should be a package"


def test_interview_routes_and_helpers_support_uuid_user_ids():
    routes = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/api/interview/_routes.py"
    ).read_text(encoding="utf-8")
    helpers = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/api/interview/_helpers.py"
    ).read_text(encoding="utf-8")
    memory = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/api/interview/_memory.py"
    ).read_text(encoding="utf-8")
    facts = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/api/interview/_facts.py"
    ).read_text(encoding="utf-8")

    assert "def _coerce_experiment_user_id(value: Any) -> Any:" in helpers
    assert 'return _json_error("agent_user_id must be an int"' not in routes
    assert '"user_id": _coerce_experiment_user_id(u.id)' in routes
    assert "agent_user_id = _coerce_experiment_user_id(agent_user_id)" in routes
    assert 'str(_coerce_experiment_user_id(obj.get("agent_user_id")))' in memory
    assert (
        "normalized_agent_user_id = _coerce_experiment_user_id(agent_user_id)" in facts
    )


def test_interview_session_creation_binds_experiment_db_before_agent_lookup():
    routes = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/api/interview/_routes.py"
    ).read_text(encoding="utf-8")

    assert "_ensure_experiment_db_bind(exp)" in routes
    assert routes.index("_ensure_experiment_db_bind(exp)") < routes.index(
        "agent_user = User_mgmt.query.get(agent_user_id)"
    )


def test_interview_frontend_preserves_uuid_agent_ids():
    script = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/interview.js"
    ).read_text(encoding="utf-8")

    assert "const agentUserId = String(agentSelect.value || '').trim()" in script
    assert "parseInt(agentSelect.value, 10)" not in script
    assert "String(a.user_id) === agentUserId" in script


def test_interview_unavailable_memory_snapshot_preserves_uuid_agent_ids():
    server = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/api/interview/_server.py"
    ).read_text(encoding="utf-8")

    assert (
        "normalized_agent_user_id = _coerce_experiment_user_id(agent_user_id)" in server
    )
    assert '"agent_user_id": normalized_agent_user_id' in server
    assert '"agent_user_id": int(agent_user_id)' not in server


def test_interview_facts_and_legacy_memory_preserve_uuid_user_ids():
    facts = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/api/interview/_facts.py"
    ).read_text(encoding="utf-8")
    memory = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/api/interview/_memory.py"
    ).read_text(encoding="utf-8")

    assert '_coerce_experiment_user_id(getattr(rp, "user_id", None))' in facts
    assert '_coerce_experiment_user_id(getattr(pp, "user_id", None))' in facts
    assert '_coerce_experiment_user_id(getattr(op, "user_id", None))' in facts
    assert 'actor = _coerce_experiment_user_id(ev.get("actor_user_id"))' in memory
    assert 'target = _coerce_experiment_user_id(ev.get("target_user_id"))' in memory
    assert '"other_user_id": _coerce_experiment_user_id(other_id)' in memory
