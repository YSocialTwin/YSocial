"""Integration test: Fase 5 ad hoc role discovery (endpoint 16) and
role_key round-trip on draft posts, on a real create_app() boot.

Piano di implementazione, Fase 5.
"""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.src.external_runtime import registry


def _suite_is_installed():
    return registry.runtime_spec("scenario_design").path.exists()


def _agent_plugins_repo_installed():
    return registry.runtime_spec("agent_plugins").path.exists()


def _can_actually_write_sqlite_files() -> bool:
    import os
    import uuid

    from y_web.src.system.path_utils import get_writable_path

    probe_dir = get_writable_path(
        os.path.join("y_web", "experiments", f"_probe_{uuid.uuid4().hex}")
    )
    try:
        os.makedirs(probe_dir, exist_ok=True)
        db_path = os.path.join(probe_dir, "probe.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


pytestmark = pytest.mark.integration


@pytest.fixture
def boot_app():
    if not _suite_is_installed():
        pytest.skip("ScenarioDesign suite not checked out in this environment")
    from y_web import create_app

    app = create_app(db_type="sqlite")
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app


@pytest.fixture
def logged_in_client(boot_app):
    from y_web.src.models import User_mgmt

    client = boot_app.test_client()
    with boot_app.app_context():
        user = User_mgmt(
            username="roles_tester",
            email="roles_tester@test.com",
            password=generate_password_hash("test123"),
            joined_on=1234567890,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    _login(client, user_id)
    return client


def test_roles_endpoint_always_includes_standard(logged_in_client):
    """Does not need a per-experiment sqlite file (no exp_id in this
    route at all) -- always runs, regardless of the Fase 1/3/4 sandbox
    sqlite-write limitation."""
    resp = logged_in_client.get("/admin/scenario_design/api/roles")
    assert resp.status_code == 200, resp.data
    roles = resp.get_json()["roles"]
    keys = {r["key"] for r in roles}
    assert "standard" in keys
    standard = next(r for r in roles if r["key"] == "standard")
    assert standard["label"] == "Standard"


def test_roles_endpoint_merges_real_adhoc_roles_when_repo_present(logged_in_client):
    """This environment happens to have external/y_agents_plugins
    actually checked out (unlike the per-experiment sqlite limitation,
    nothing prevents exercising the real discovery path end-to-end
    here) -- asserts against its real, current registry.json rather
    than a mock, which is strictly stronger evidence than the mocked
    unit tests in ScenarioDesign/tests/test_roles.py alone.
    """
    if not _agent_plugins_repo_installed():
        pytest.skip("external/y_agents_plugins not checked out in this environment")

    resp = logged_in_client.get("/admin/scenario_design/api/roles")
    assert resp.status_code == 200, resp.data
    roles = resp.get_json()["roles"]
    keys = {r["key"] for r in roles}
    assert "standard" in keys
    assert len(keys) > 1  # at least one real ad hoc role discovered
    for role in roles:
        if role["key"] == "standard":
            continue
        assert "parameters" not in role
        assert "client_parameters" not in role
        assert set(role.keys()) == {"key", "label", "description", "prompt_hint"}


def _make_exp(app, name="sd-fase5-exp"):
    import os

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    folder = get_writable_path(os.path.join("y_web", "experiments", name))
    os.makedirs(folder, exist_ok=True)

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            exp_name=name,
            db_name=f"experiments/{name}/database_server.db",
            owner="admin",
            exp_descr="test",
            status=1,
            running=0,
            port=5000,
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


@pytest.fixture
def sd_app_with_sqlite(boot_app):
    if not _can_actually_write_sqlite_files():
        pytest.skip(
            "Sandbox cannot commit new sqlite files under this repo's "
            "y_web/experiments/ subtree in this environment (known "
            "limitation, ScenarioDesign/docs/decisions.md §F1.4/§F1.5/§F3.x) "
            "-- re-run in a real dev environment to exercise this module."
        )
    return boot_app


def test_role_key_round_trips_through_post_create_and_update(
    sd_app_with_sqlite, logged_in_client
):
    from y_web.src.models import User_mgmt

    with sd_app_with_sqlite.app_context():
        author = User_mgmt(
            username="agent_x",
            email="agent_x@test.com",
            password=generate_password_hash("x"),
            joined_on=1,
        )
        db.session.add(author)
        db.session.commit()
        author_id = author.id

    exp_id = _make_exp(sd_app_with_sqlite)
    client = logged_in_client

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios",
        json={"name": "S1"},
    )
    scenario_id = resp.get_json()["scenario"]["id"]
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1"},
    )
    thread_id = resp.get_json()["thread"]["id"]

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/threads/{thread_id}/posts",
        json={
            "tmp_id": "root",
            "author_user_id": author_id,
            "content": "root",
            "role_key": "stress_attacker",
        },
    )
    assert resp.status_code == 201, resp.data
    assert resp.get_json()["post"]["role_key"] == "stress_attacker"

    resp = client.put(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/posts/root",
        json={"role_key": "a_role_that_was_since_removed"},
    )
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["post"]["role_key"] == "a_role_that_was_since_removed"

    # A role_key that no longer matches anything discoverable is still
    # accepted and stored as-is (piano tecnico §17: never blocks editing).
    get_resp = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads/{thread_id}"
    )
    post = get_resp.get_json()["posts"][0]
    assert post["role_key"] == "a_role_that_was_since_removed"
