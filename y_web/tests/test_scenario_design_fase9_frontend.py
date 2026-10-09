"""Integration tests for Fase 9's frontend additions:

* ``GET /admin/scenario_design/app`` (``app_shell`` view) -- a brand-new,
  separate route from the pre-existing JSON health-check ``index()`` (see
  ``modules/scenario_editor/backend/__init__.py``'s module docstring and
  ``docs/decisions.md`` for why the two were kept apart: ``index()`` is
  relied on by this suite's own standalone, flask-login-free test,
  ``tests/test_blueprint_registration.py``, so it stays untouched and
  unauthenticated while the real admin UI lives behind ``@login_required``
  at its own path).
* ``GET .../publications/<id>/id_mapping`` -- the Fase 9 read-only endpoint
  added to ``routes_publish.py`` so the new "Real Content" tab can resolve
  a publication's ``tmp_id -> real_id`` pairs after the fact (no prior
  endpoint exposed this).

Piano di implementazione, Fase 9 (decisions.md, frontend subsection).
"""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.src.external_runtime import registry


def _suite_is_installed():
    return registry.runtime_spec("scenario_design").path.exists()


def _can_actually_write_sqlite_files() -> bool:
    import os
    import uuid

    from y_web.src.system.path_utils import get_writable_path

    probe_dir = get_writable_path(
        os.path.join("y_web", "experiments", f"_probe_fase9_{uuid.uuid4().hex}")
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
def sd_app():
    if not _suite_is_installed():
        pytest.skip("ScenarioDesign suite not checked out in this environment")

    from y_web import create_app

    boot_app = create_app(db_type="sqlite")
    boot_app.config["TESTING"] = True
    boot_app.config["WTF_CSRF_ENABLED"] = False
    return boot_app


@pytest.fixture
def sd_client(sd_app):
    """Returns (client, admin_id) *without* logging in -- the app_shell()
    tests below need to exercise both the anonymous and logged-in cases
    on the same client, so login stays an explicit, separate step (see
    test_app_shell_serves_html_shell_when_logged_in).

    User-reported (2026-10-08, "yes please" to extending the fase3 fix):
    this is an Admin_users account, not a User_mgmt one -- see
    test_scenario_design_fase3_threads.py for the full root-cause
    explanation of why a User_mgmt login specifically breaks under the
    db_exp bind swap, which matters here too: both id_mapping tests
    below hit exp_id-scoped routes."""
    from y_web.src.models import Admin_users

    client = sd_app.test_client()
    with sd_app.app_context():
        admin_user = Admin_users(
            username="sd_fase9_admin",
            email="sd_fase9_admin@test.com",
            password=generate_password_hash("test123"),
            last_seen="",
            role="admin",
        )
        db.session.add(admin_user)
        db.session.commit()
        admin_id = admin_user.id
    return client, f"admin_{admin_id}"


# ---------------------------------------------------------------------
# app_shell()
# ---------------------------------------------------------------------


def test_app_shell_requires_login_redirects_when_anonymous(sd_client):
    client, _admin_id = sd_client
    resp = client.get("/admin/scenario_design/app")
    # flask-login's default unauthorized handler redirects to the login
    # view rather than returning a bare 401 -- this is what distinguishes
    # app_shell() from the deliberately-unauthenticated index() route.
    assert resp.status_code in (301, 302, 303, 308)


def test_app_shell_serves_html_shell_when_logged_in(sd_client):
    client, admin_id = sd_client
    _login(client, admin_id)
    resp = client.get("/admin/scenario_design/app")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    body = resp.data.decode("utf-8")
    assert 'id="sd-root"' in body
    # The static-asset URL convention this suite's own registry test
    # (test_backend_plugins_registry.py) pins down: the route is
    # /plugins/<repo_key>/<module_id>/static/<full repo-relative path>,
    # not a module-local static subfolder.
    assert (
        "/plugins/scenario_design/scenario_editor/static/modules/scenario_editor/static/js/editor.js"
        in body
    )


def test_index_health_check_still_unauthenticated_after_app_shell_addition(sd_client):
    """Non-regression: adding app_shell() must not have touched index()."""
    client, _admin_id = sd_client
    resp = client.get("/admin/scenario_design/")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "ok"
    assert payload["suite"] == "scenario_design"


# ---------------------------------------------------------------------
# publication_id_mapping()
# ---------------------------------------------------------------------


def _make_exp(app, name="sd-fase9-exp"):
    """Random suffix avoids colliding with a previous run's leftover,
    gitignored experiment folder on disk (see
    test_scenario_design_fase3_threads.py)."""
    import os
    import uuid

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    folder_name = f"{name}-{uuid.uuid4().hex[:8]}"
    folder = get_writable_path(os.path.join("y_web", "experiments", folder_name))
    os.makedirs(folder, exist_ok=True)
    db_path = os.path.join(
        folder, "database_server.db"
    )  # noqa: F841 (created lazily by the app)

    # Required by the /publish flow's _create_single_experiment_copy()
    # (see test_scenario_design_fase6_publish.py's _make_exp()).
    import json

    with open(os.path.join(folder, "config_server.json"), "w") as f:
        json.dump(
            {
                "platform_type": "microblogging",
                "name": folder_name,
                "port": 5000,
                "database_uri": db_path,
                "data_path": folder + os.sep,
            },
            f,
        )

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            simulator_type="Standard",
            exp_name=folder_name,
            db_name=f"experiments/{folder_name}/database_server.db",
            owner="admin",
            exp_descr="test",
            status=1,
            running=0,
            port=5000,
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


def _make_author(app, exp_id, username="fase9_author", user_id="1"):
    """Create a real User_mgmt row inside *exp_id*'s own per-experiment
    database (see test_scenario_design_fase3_threads.py's ``_make_author``
    for the full rationale)."""
    from y_web.src.experiment.context import experiment_db_bind
    from y_web.src.models import User_mgmt

    with app.app_context():
        with experiment_db_bind(exp_id):
            author = User_mgmt(
                id=user_id,
                username=username,
                email=f"{username}@test.com",
                password=generate_password_hash("test123"),
                joined_on=1234567890,
            )
            db.session.add(author)
            db.session.commit()
    return user_id


@pytest.mark.skipif(
    not _can_actually_write_sqlite_files(),
    reason=(
        "Sandbox cannot commit new sqlite files under this repo's "
        "y_web/experiments/ subtree in this environment (known "
        "limitation, ScenarioDesign/docs/decisions.md §F1.4/§F1.5/§F3.x) "
        "-- re-run in a real dev environment to exercise this endpoint."
    ),
)
def test_publication_id_mapping_matches_publish_response(sd_app, sd_client):
    client, admin_id = sd_client
    _login(client, admin_id)
    exp_id = _make_exp(sd_app, "sd-fase9-id-mapping")
    author_id = _make_author(sd_app, exp_id)

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios",
        json={"name": "S1"},
    )
    assert resp.status_code == 201, resp.data
    scenario_id = resp.get_json()["scenario"]["id"]

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1"},
    )
    assert resp.status_code == 201, resp.data
    thread_id = resp.get_json()["thread"]["id"]

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/threads/{thread_id}/posts",
        json={
            "tmp_id": "root",
            "parent_tmp_id": None,
            "author_user_id": author_id,
            "content": "hello",
        },
    )
    assert resp.status_code == 201, resp.data

    import uuid

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/publish",
        json={"published_experiment_name": f"fase9-published-{uuid.uuid4().hex[:8]}"},
    )
    assert resp.status_code == 201, resp.data
    publish_body = resp.get_json()
    publication_id = publish_body["publication"]["id"]
    expected_mapping = publish_body["id_mapping"]

    resp = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/publications/{publication_id}/id_mapping"
    )
    assert resp.status_code == 200, resp.data
    rows = resp.get_json()["id_mapping"]
    assert {r["tmp_id"]: r["real_id"] for r in rows} == {
        tmp_id: str(real_id) for tmp_id, real_id in expected_mapping.items()
    }


@pytest.mark.skipif(
    not _can_actually_write_sqlite_files(),
    reason=(
        "Sandbox cannot commit new sqlite files under this repo's "
        "y_web/experiments/ subtree in this environment (known "
        "limitation, ScenarioDesign/docs/decisions.md §F1.4/§F1.5/§F3.x) "
        "-- re-run in a real dev environment to exercise this endpoint."
    ),
)
def test_publication_id_mapping_404_for_unknown_publication(sd_app, sd_client):
    client, admin_id = sd_client
    _login(client, admin_id)
    exp_id = _make_exp(sd_app, "sd-fase9-id-mapping-404")

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios",
        json={"name": "S1"},
    )
    assert resp.status_code == 201, resp.data
    scenario_id = resp.get_json()["scenario"]["id"]

    resp = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/publications/999999/id_mapping"
    )
    assert resp.status_code == 404
