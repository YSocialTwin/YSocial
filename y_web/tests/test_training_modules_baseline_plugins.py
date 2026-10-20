"""
Phase 0 characterization tests for the TrainingModules plugin (point [NV] b).

[NV] (b): what happens to the routes of a backend plugin whose repository is
removed from disk (Plugin Manager "delete" = rmtree) while the process keeps
running.  The tests use Scenario Design as the only backend plugin that exists
today and skip cleanly when it is not checked out
(claude/testing-conventions.md).
"""

import dataclasses
import uuid

import pytest
from werkzeug.security import generate_password_hash

REPO_KEY = "scenario_design"
SD_ROUTE = "/admin/scenario_design/app"


def _suite_is_installed():
    from y_web.src.external_runtime import registry

    return registry.runtime_spec(REPO_KEY).path.exists()


@pytest.fixture
def sd_app():
    if not _suite_is_installed():
        pytest.skip("ScenarioDesign suite not checked out in this environment")
    from y_web import create_app

    app = create_app(db_type="sqlite")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


@pytest.fixture
def repo_removed(monkeypatch, tmp_path):
    """Simulate delete_runtime_repo(): the spec points at a path that is gone."""
    from y_web.src.external_runtime import registry

    spec = registry.runtime_spec(REPO_KEY)
    monkeypatch.setitem(
        registry.SUPPORTED_EXTERNAL_REPOS,
        REPO_KEY,
        dataclasses.replace(spec, path=tmp_path / "removed"),
    )


def _login_admin(app):
    from y_web import db
    from y_web.src.models import Admin_users

    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        row = Admin_users(
            username=f"a{tag}",
            email=f"a{tag}@example.test",
            password=generate_password_hash("Passw0rd!"),
            last_seen="2026-01-01",
            role="admin",
        )
        db.session.add(row)
        db.session.commit()
        user_id = row.get_id()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user_id
        sess["_fresh"] = True
    return client


def test_blueprint_routes_are_registered_at_startup_when_installed(sd_app):
    rules = {r.rule for r in sd_app.url_map.iter_rules()}
    assert SD_ROUTE in rules


def test_removing_the_repository_hides_the_suite_but_not_its_routes(
    sd_app, repo_removed
):
    from y_web.src.external_runtime import backend_plugins

    report = backend_plugins.validate_backend_suite(REPO_KEY)
    assert report["installed"] is False
    assert backend_plugins.backend_suite_availability()[REPO_KEY] is False

    with sd_app.test_request_context("/"):
        entries = backend_plugins.backend_suite_sidebar_entries()
    assert REPO_KEY not in [e["repo_key"] for e in entries]

    # The url_map is built once at startup and Flask cannot unregister a
    # blueprint: the plugin's rule is still there after the "delete".
    rules = {r.rule for r in sd_app.url_map.iter_rules()}
    assert SD_ROUTE in rules


def test_route_of_a_removed_repository_still_answers_until_restart(
    sd_app, repo_removed
):
    client = _login_admin(sd_app)
    response = client.get(SD_ROUTE)
    # Characterized today: served normally (200), not 404.
    assert response.status_code == 200
