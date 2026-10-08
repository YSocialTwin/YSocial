"""Integration test: Fase 3 thread/post CRUD end-to-end on a real
create_app() boot, with the Scenario Design suite installed — exercises
the actual db_exp bind activation (via exp_id in the URL, see
docs/decisions.md in external/ScenarioDesign for why endpoints 11/12
deviate from piano tecnico §15's literal path), real User_mgmt author
validation, and the thread invariants (single root, acyclic, no orphan
parent) through real HTTP requests, not just the unit-level
test_thread_invariants.py in the ScenarioDesign repo.

Piano di implementazione, Fase 3.

User-reported (2026-10-08, "digg into it and fix the tests"): every test
below that hit an ``/experiments/<exp_id>/...`` URL was 302-redirecting
to ``/login`` instead of exercising the route at all. Root cause (two
layers, both fixed here):

1. The login identity was a ``User_mgmt`` row, which is
   ``__bind_key__ = "db_exp"``. ``setup_experiment_context()`` (a
   ``before_request`` hook) repoints the shared ``db_exp`` bind at the
   *specific* experiment named by ``exp_id`` in the URL for the
   duration of that request. So the very first request carrying an
   ``exp_id`` swapped ``db_exp`` away from wherever the fixture's
   ``User_mgmt`` row actually lived, and Flask-Login's
   ``load_user()`` -- which looks that id up via ``db.session.get
   (User_mgmt, user_id)`` -- correctly found no such row in *that*
   experiment's own database and returned ``None``, failing
   ``@login_required``. ``Admin_users`` (``__bind_key__ = "db_admin"``)
   is never touched by that swap, so logging in as an admin -- which is
   also what these admin-only scenario_design routes are actually for
   in production -- is stable across every request regardless of which
   exp_id is in the URL.
2. Once login was fixed, a *second*, pre-existing issue surfaced: the
   per-experiment ``user_mgmt`` table's real schema (hand-written raw
   SQL in ``y_web/src/experiment/schema.py``, not SQLAlchemy's default
   autoincrement) declares ``id TEXT PRIMARY KEY`` with no autoincrement
   semantics at all, and production code
   (``y_web/src/experiment/helpers.py``) always supplies an explicit
   ``id=`` when creating one. A ``User_mgmt(...)`` row created without
   an explicit ``id`` silently gets ``id=NULL`` and is unreachable the
   moment SQLAlchemy's post-commit attribute expiry tries to reload it.
   Every author fixture below now passes an explicit, small numeric
   string id, mirroring production.
"""
import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.src.external_runtime import registry


def _suite_is_installed():
    return registry.runtime_spec("scenario_design").path.exists()


def _can_actually_write_sqlite_files() -> bool:
    """Probe for the known sandbox limitation already documented in
    ScenarioDesign/docs/decisions.md §F1.4/§F1.5: the remote-devices
    bridge's connected-folder restrictions can make a *new* sqlite file's
    journal commit fail with ``disk I/O error`` under this repo's
    ``y_web/experiments/`` subtree specifically (confirmed NOT a general
    sqlite/sandbox restriction -- the identical write succeeds fine under
    a plain ``/tmp`` directory; it is specific to this connected-folder
    mount), even though the plain ``open()``/``os.makedirs()`` calls that
    create the file and its parent directory succeed. This is an
    environment artifact, not a code defect -- every test in this module
    depends on register_experiment_database() actually creating a real
    per-experiment sqlite file under that exact subtree on first request,
    so the probe must test that exact subtree, not a generic temp dir.
    """
    import os
    import uuid

    from y_web.src.system.path_utils import get_writable_path

    probe_dir = get_writable_path(os.path.join("y_web", "experiments", f"_probe_{uuid.uuid4().hex}"))
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


def _make_exp(app, name="sd-fase3-exp"):
    """Create a real Exps row with its own on-disk database file.

    A real create_app() boot's setup_experiment_context() actually calls
    register_experiment_database() -> ensure_experiment_schema_for_uri(),
    which creates the sqlite file on disk at db_name's path (resolved via
    get_writable_path(), i.e. relative to the repo root in dev mode) the
    first time a request names this exp_id in its URL. Each test gets its
    own subfolder (keyed by *name*) so distinct tests never share one
    physical database file -- but these subfolders are real, persistent,
    gitignored files on disk, not an ephemeral per-test temp dir, so a
    fixed *name* across repeated runs of this suite would otherwise
    collide with whatever a previous run left behind (e.g. the fixed
    "testuser" row _make_author below inserts). A short random suffix
    keeps every run's folder -- and so every run's author rows --
    independent of whatever earlier runs left on disk.
    """
    import os
    import uuid

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    folder_name = f"{name}-{uuid.uuid4().hex[:8]}"
    folder = get_writable_path(os.path.join("y_web", "experiments", folder_name))
    os.makedirs(folder, exist_ok=True)

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
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


def _make_author(app, exp_id, username="testuser", user_id="1"):
    """Create a real User_mgmt row inside *exp_id*'s own per-experiment
    database -- not the shared default db_exp bind -- so it is actually
    reachable as an author (author_user_id validation, the authors/search
    endpoint) once a request for that exp_id activates its bind.

    experiment_db_bind() is the same helper production code uses to do
    this outside of a live request (see
    y_web/src/experiment/context.py); it activates the per-experiment
    bind for the duration of the ``with`` block and restores the
    previous one afterwards, exactly like setup_experiment_context()
    does per-request.

    An explicit *user_id* is required: the real per-experiment
    ``user_mgmt`` table is ``id TEXT PRIMARY KEY`` with no autoincrement
    (see this module's docstring) -- production always supplies one
    (y_web/src/experiment/helpers.py), and a row inserted without one
    gets id=NULL and is unreachable.
    """
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


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


pytestmark = pytest.mark.integration


@pytest.fixture
def sd_app():
    """A real create_app() boot (not the minimal `app` fixture): the
    Scenario Design blueprint is only registered by the actual
    register_backend_plugin_suites() call inside create_app(), so Fase 3's
    routes do not exist at all on the generic `app` fixture's bare Flask
    instance.
    """
    if not _suite_is_installed():
        pytest.skip("ScenarioDesign suite not checked out in this environment")
    if not _can_actually_write_sqlite_files():
        pytest.skip(
            "Sandbox cannot commit new sqlite files under this repo's "
            "y_web/experiments/ subtree in this environment (known "
            "limitation, ScenarioDesign/docs/decisions.md §F1.4/§F1.5/§F3.x) "
            "-- re-run in a real dev environment to exercise this module."
        )

    from y_web import create_app

    boot_app = create_app(db_type="sqlite")
    boot_app.config["TESTING"] = True
    boot_app.config["WTF_CSRF_ENABLED"] = False
    return boot_app


@pytest.fixture
def sd_client(sd_app):
    """Logs in as a real Admin_users account -- these are admin-only
    routes in production, and (unlike a User_mgmt participant row,
    __bind_key__ = "db_exp") Admin_users is __bind_key__ = "db_admin",
    which setup_experiment_context() never repoints per-request, so the
    login survives every exp_id-scoped request regardless of which
    experiment it names (see this module's docstring)."""
    from y_web.src.models import Admin_users

    client = sd_app.test_client()
    with sd_app.app_context():
        admin_user = Admin_users(
            username="sd_fase3_admin",
            email="sd_fase3_admin@test.com",
            password=generate_password_hash("test123"),
            last_seen="",
            role="admin",
        )
        db.session.add(admin_user)
        db.session.commit()
        admin_id = admin_user.id
    _login(client, f"admin_{admin_id}")
    return client


def _create_scenario(client, exp_id, name="S1"):
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios",
        json={"name": name},
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["scenario"]["id"]


def test_thread_and_root_post_lifecycle(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app)
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)

    create_thread = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1", "title": "Thread 1"},
    )
    assert create_thread.status_code == 201, create_thread.data
    thread_id = create_thread.get_json()["thread"]["id"]

    add_root = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/threads/{thread_id}/posts",
        json={"tmp_id": "root", "parent_tmp_id": None, "author_user_id": author_id, "content": "hello"},
    )
    assert add_root.status_code == 201, add_root.data

    get_thread = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads/{thread_id}"
    )
    assert get_thread.status_code == 200
    posts = get_thread.get_json()["posts"]
    assert [p["tmp_id"] for p in posts] == ["root"]


def test_second_root_rejected_with_409(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-2root")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1"},
    ).get_json()["thread"]["id"]

    base = f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads/{thread_id}/posts"
    r1 = client.post(base, json={"tmp_id": "root1", "parent_tmp_id": None, "author_user_id": author_id})
    assert r1.status_code == 201
    r2 = client.post(base, json={"tmp_id": "root2", "parent_tmp_id": None, "author_user_id": author_id})
    assert r2.status_code == 409
    assert r2.get_json()["error"]["code"] == "thread_second_root"


def test_cycle_rejected_at_write_time(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-cycle")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1"},
    ).get_json()["thread"]["id"]

    base = f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads/{thread_id}/posts"
    client.post(base, json={"tmp_id": "root", "parent_tmp_id": None, "author_user_id": author_id})
    client.post(base, json={"tmp_id": "a", "parent_tmp_id": "root", "author_user_id": author_id})

    # Attempt to make 'root' a child of 'a' -- a direct cycle.
    resp = client.put(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/posts/root",
        json={"parent_tmp_id": "a"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "thread_cycle_detected"


def test_orphan_parent_rejected(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-orphan")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1"},
    ).get_json()["thread"]["id"]

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/threads/{thread_id}/posts",
        json={"tmp_id": "a", "parent_tmp_id": "does_not_exist", "author_user_id": author_id},
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "thread_orphan_parent"


def test_nonexistent_author_rejected(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-author")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1"},
    ).get_json()["thread"]["id"]

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/threads/{thread_id}/posts",
        json={"tmp_id": "root", "parent_tmp_id": None, "author_user_id": 999999},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "author_not_found"


def test_delete_subtree_removes_exact_descendant_count(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-subtree")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1"},
    ).get_json()["thread"]["id"]

    base = f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads/{thread_id}/posts"
    client.post(base, json={"tmp_id": "root", "parent_tmp_id": None, "author_user_id": author_id})
    client.post(base, json={"tmp_id": "child", "parent_tmp_id": "root", "author_user_id": author_id})
    client.post(base, json={"tmp_id": "grandchild", "parent_tmp_id": "child", "author_user_id": author_id})
    client.post(base, json={"tmp_id": "sibling", "parent_tmp_id": "root", "author_user_id": author_id})

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        "/posts/child/delete_subtree"
    )
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["deleted_count"] == 2  # 'child' + 'grandchild', not 'root'/'sibling'
    assert set(body["deleted_tmp_ids"]) == {"child", "grandchild"}

    get_thread = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads/{thread_id}"
    )
    remaining = {p["tmp_id"] for p in get_thread.get_json()["posts"]}
    assert remaining == {"root", "sibling"}


def test_delete_subtree_already_deleted_is_idempotent_404(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-idempotent")
    scenario_id = _create_scenario(client, exp_id)

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        "/posts/never_existed/delete_subtree"
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "post_not_found"


def test_bulk_delete_threads_removes_all(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-bulk")
    scenario_id = _create_scenario(client, exp_id)
    client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t1"},
    )
    client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": "t2"},
    )
    # Fase 8: reinforced confirmation (piano tecnico §21) -- a bulk delete
    # without the scenario's exact name typed back is rejected, server-side,
    # before anything is deleted.
    mismatch_resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/bulk_delete_threads",
        json={"confirm_name": "wrong name"},
    )
    assert mismatch_resp.status_code == 400
    assert mismatch_resp.get_json()["error"]["code"] == "confirmation_mismatch"

    listing_before = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads"
    )
    assert len(listing_before.get_json()["threads"]) == 2  # nothing deleted yet

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/bulk_delete_threads",
        json={"confirm_name": "S1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["deleted_thread_count"] == 2

    listing = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads"
    )
    assert listing.get_json()["threads"] == []


def test_post_not_reachable_through_a_different_scenario(sd_app, sd_client):
    """tmp_id isolation (_post_or_404 is scoped by scenario_id, not just a
    global tmp_id lookup) -- a post belonging to scenario A's thread must
    not be editable/deletable through scenario B's URL."""
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-isolation")
    author_id = _make_author(sd_app, exp_id)
    scenario_a = _create_scenario(client, exp_id, name="A")
    scenario_b = _create_scenario(client, exp_id, name="B")

    thread_id = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_a}/threads",
        json={"tmp_id": "t1"},
    ).get_json()["thread"]["id"]
    client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_a}"
        f"/threads/{thread_id}/posts",
        json={"tmp_id": "root", "parent_tmp_id": None, "author_user_id": author_id},
    )

    # Attempt to edit scenario A's post through scenario B's URL.
    resp = client.put(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_b}/posts/root",
        json={"content": "hijacked"},
    )
    assert resp.status_code == 404


def test_vocab_and_roles_endpoints(sd_app, sd_client):
    client = sd_client
    topics_resp = client.get("/admin/scenario_design/api/vocab/topics")
    assert topics_resp.status_code == 200
    assert "technology" in topics_resp.get_json()["topics"]

    roles_resp = client.get("/admin/scenario_design/api/roles")
    assert roles_resp.status_code == 200
    roles = roles_resp.get_json()["roles"]
    assert any(r["key"] == "standard" for r in roles)


def test_vocab_topics_and_emotions_read_the_real_experiment_tables(sd_app, sd_client):
    """User-reported 2026-10-03: the generation panel's "Topic" field was
    backed by a hardcoded 8-item list with no relationship to any given
    simulation's actual topics ("Topic should be chosen among the ones
    available in the simulation"); emotions needed the same per-experiment,
    real-table treatment ("using tag system based on the values present in
    the admin database relevant tables"). These two new, additive,
    experiment-scoped endpoints read the real ``interests``/``emotions``
    tables instead of any hardcoded vocabulary."""
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-vocab")
    # First request against this exp_id triggers register_experiment_database()
    # -- same bootstrap authors/search already relies on.
    client.get(f"/admin/scenario_design/api/experiments/{exp_id}/authors/search")

    from y_web.src.experiment.context import experiment_db_bind
    from y_web.src.experiment.helpers import _ensure_experiment_orm_tables
    from y_web.src.models import Emotions, Interests

    with sd_app.app_context():
        # Interests/Emotions are __bind_key__ = "db_exp" too -- same
        # per-experiment-bind requirement as the author rows above, so
        # this insert must go through the same exp_id-scoped bind the
        # requests below will read back from, not whatever db_exp
        # happens to point at outside of a request.
        with experiment_db_bind(exp_id):
            # Unlike user_mgmt (hand-written raw SQL, see this module's
            # docstring), interests/emotions are plain SQLAlchemy models
            # with no raw-SQL DDL of their own -- a freshly created
            # per-experiment sqlite file doesn't have them yet.
            # Production never hits this gap because
            # open_experiment_session() (y_web/src/experiment/helpers.py)
            # always calls this same helper before any ORM access; do the
            # same here instead of assuming the table exists.
            _ensure_experiment_orm_tables(db.engines["db_exp"])
            db.session.add(Interests(interest="quantum computing"))
            db.session.add(Emotions(emotion="curiosity", icon="🤔"))
            db.session.commit()

    topics_resp = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/vocab/topics"
    )
    assert topics_resp.status_code == 200
    assert topics_resp.get_json()["topics"] == ["quantum computing"]

    emotions_resp = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/vocab/emotions"
    )
    assert emotions_resp.status_code == 200
    assert emotions_resp.get_json()["emotions"] == ["curiosity"]


def test_author_search_filters_by_query(sd_app, sd_client):
    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase3-exp-authors")
    _make_author(sd_app, exp_id)
    resp = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/authors/search",
        query_string={"q": "testuser"},
    )
    assert resp.status_code == 200
    authors = resp.get_json()["authors"]
    assert any(a["username"] == "testuser" for a in authors)

    resp_no_match = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/authors/search",
        query_string={"q": "no_such_user_xyz"},
    )
    assert resp_no_match.get_json()["authors"] == []
