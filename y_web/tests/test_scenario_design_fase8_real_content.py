"""Integration test: Fase 8 modify/delete of already-published real
content (``routes_real_content.py``) end-to-end on a real create_app()
boot, for both families -- publishes a small thread first (reusing the
Fase 6/7 publish flow to get real materialized rows), then exercises:

* ``PUT .../real_posts/<id>`` -- content/author update on a real post.
* ``DELETE .../real_posts/<id>`` -- single-post delete, refused
  (``post_has_descendants``) when the post has replies, accepted when it
  does not.
* ``POST .../real_posts/<id>/delete_subtree`` -- cascade delete of a real
  post and its real descendants, verified against the full satellite-row
  count (Post_Toxicity/Post_topics for Standard; PostToxicity/PostTopic
  for HPC), not just the Post rows themselves.
* ``experiment_running`` rejection on all three operations.
* ``author_not_found`` rejection on an update naming a non-existent
  author.

Same sandbox sqlite-write limitation as every other integration test in
this module (ScenarioDesign/docs/decisions.md §F1.4/§F1.5/§F3.x/§F7.7):
every test here needs a real per-experiment sqlite file and skips
cleanly via ``_can_actually_write_sqlite_files()`` in this environment.

User-reported (2026-10-08, "yes please" to extending the fase3 fix): this
file had the same bugs as its fase6/fase7 siblings -- see
test_scenario_design_fase3_threads.py's docstring for the login-identity
root cause (fixed the same way, Admin_users instead of User_mgmt),
test_scenario_design_fase6_publish.py for the db_exp-bind-restored-after-
every-request issue and the config_server.json requirement, and
test_scenario_design_fase7_publish_hpc.py for the YSimulator sys.path
bootstrap, the server_config.json requirement, and the HPC User_mgmt
password NOT NULL constraint. One further, file-specific bug: the
original ``author_user_id`` passed into every post was the *login user's
own id* (a User_mgmt/Admin_users row that was never created inside the
target experiment's own database at all) -- fixed with a proper
_make_author()/HPC author helper, mirroring fase3/4/6.

Piano di implementazione, Fase 8 (decisions.md §F8.5/§F8.6).
"""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.src.external_runtime import registry


def _suite_is_installed():
    return registry.runtime_spec("scenario_design").path.exists()


def _ysimulator_is_installed():
    import os

    from y_web.src.system.path_utils import get_base_path

    return os.path.isdir(
        os.path.join(get_base_path(), "external", "YSimulator", "YSimulator")
    )


def _can_actually_write_sqlite_files() -> bool:
    import os
    import uuid

    from y_web.src.system.path_utils import get_writable_path

    probe_dir = get_writable_path(
        os.path.join("y_web", "experiments", f"_probe_fase8_{uuid.uuid4().hex}")
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


def _scenario_design_module(dotted_path):
    from y_web.src.external_runtime.backend_plugins import _import_from_suite

    return _import_from_suite("scenario_design", dotted_path)


def _hpc_session_module():
    return _scenario_design_module("modules.scenario_editor.backend.hpc_session")


def _ensure_ysimulator_importable():
    _hpc_session_module()._ensure_ysimulator_on_path()


def _make_exp(app, name="sd-fase8-exp", simulator_type="Standard"):
    """Random suffix avoids colliding with a previous run's leftover,
    gitignored experiment folder on disk (see
    test_scenario_design_fase3_threads.py). Writes config_server.json
    (Standard) / server_config.json (HPC) so the /publish flow's
    _create_single_experiment_copy() can correctly classify and copy this
    experiment (see test_scenario_design_fase6_publish.py and
    test_scenario_design_fase7_publish_hpc.py)."""
    import json
    import os
    import uuid

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    folder_name = f"{name}-{uuid.uuid4().hex[:8]}"
    folder = get_writable_path(os.path.join("y_web", "experiments", folder_name))
    os.makedirs(folder, exist_ok=True)
    db_path = os.path.join(folder, "database_server.db")

    if simulator_type != "Standard":
        _ensure_ysimulator_importable()

        from sqlalchemy import create_engine
        from YSimulator.YServer.classes.models import Base as HpcBase

        engine = create_engine(f"sqlite:///{db_path}")
        HpcBase.metadata.create_all(engine)
        engine.dispose()

        with open(os.path.join(folder, "server_config.json"), "w") as f:
            json.dump(
                {
                    "experiment_name": folder_name,
                    "server": {"port": 5000},
                    "database_uri": db_path,
                },
                f,
            )
    else:
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
            simulator_type=simulator_type,
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


def _make_author(app, exp_id, username="fase8_author", user_id="1"):
    """Create a real User_mgmt row inside *exp_id*'s own per-experiment
    database (see test_scenario_design_fase3_threads.py's ``_make_author``
    for the full rationale). Standard family only -- HPC uses
    ``_seed_hpc_author`` below instead."""
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


def _seed_hpc_author(app, exp_id, *, username="hpc_author"):
    """User-reported (2026-10-08): YSimulator's own User_mgmt.password
    column is nullable=False -- see test_scenario_design_fase7_publish_hpc.py."""
    import uuid

    from YSimulator.YServer.classes.models import User_mgmt as HpcUser

    from y_web.src.models import Exps

    hpc_session = _hpc_session_module().hpc_session

    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        user_id = str(uuid.uuid4())
        with hpc_session(exp) as hsession:
            hsession.add(
                HpcUser(
                    id=user_id,
                    username=username,
                    password=generate_password_hash("test123"),
                )
            )
            hsession.commit()
        return user_id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


pytestmark = pytest.mark.integration


@pytest.fixture
def sd_app():
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
    """Logs in as a real Admin_users account (see
    test_scenario_design_fase3_threads.py for why)."""
    from y_web.src.models import Admin_users

    client = sd_app.test_client()
    with sd_app.app_context():
        admin_user = Admin_users(
            username="sd_fase8_admin",
            email="sd_fase8_admin@test.com",
            password=generate_password_hash("test123"),
            last_seen="",
            role="admin",
        )
        db.session.add(admin_user)
        db.session.commit()
        admin_id = admin_user.id
    _login(client, f"admin_{admin_id}")
    return client, admin_id


def _create_scenario(client, exp_id, name="S1"):
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios",
        json={"name": name},
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["scenario"]["id"]


def _create_thread(client, exp_id, scenario_id, tmp_id="t1"):
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/threads",
        json={"tmp_id": tmp_id},
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["thread"]["id"]


def _add_post(
    client,
    exp_id,
    scenario_id,
    thread_id,
    *,
    tmp_id,
    parent_tmp_id,
    author_user_id,
    content="",
):
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
        f"/threads/{thread_id}/posts",
        json={
            "tmp_id": tmp_id,
            "parent_tmp_id": parent_tmp_id,
            "author_user_id": author_user_id,
            "content": content,
        },
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()["post"]["id"]


def _publish(client, exp_id, scenario_id):
    import uuid

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/publish",
        json={"published_experiment_name": f"fase8-published-{uuid.uuid4().hex[:8]}"},
    )
    assert resp.status_code == 201, resp.data
    return resp.get_json()


def _publish_root_child_grandchild(
    client, exp_id, author_user_id, *, simulator_type="Standard"
):
    """Publish a three-level real thread (root -> child -> grandchild)
    and return ``{tmp_id: real_post_id}`` from the publish response's
    id_mapping -- the shared setup for every test below. Values are
    coerced to ``int`` for Standard (``id_mapping`` carries them as
    strings, same as the Fase 6 publish test) and left as the opaque
    UUID string for HPC."""
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=author_user_id,
        content="root",
    )
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="child",
        parent_tmp_id="root",
        author_user_id=author_user_id,
        content="child",
    )
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="grandchild",
        parent_tmp_id="child",
        author_user_id=author_user_id,
        content="grandchild",
    )
    body = _publish(client, exp_id, scenario_id)
    id_mapping = body["id_mapping"]
    if simulator_type == "Standard":
        return {tmp_id: int(real_id) for tmp_id, real_id in id_mapping.items()}
    return id_mapping


# ---------------------------------------------------------------------
# Standard family
# ---------------------------------------------------------------------


def test_update_real_post_content_and_author_standard(sd_app, sd_client):
    from y_web.src.experiment.context import _activate_db_exp_bind, experiment_db_bind
    from y_web.src.models import Post, User_mgmt

    client, _admin_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase8-std-update")
    author_id = _make_author(sd_app, exp_id)
    mapping = _publish_root_child_grandchild(client, exp_id, author_id)
    real_root_id = mapping["root"]

    with sd_app.app_context():
        with experiment_db_bind(exp_id):
            other_author = User_mgmt(
                id="2",
                username="other_author",
                email="other_author@test.com",
                password=generate_password_hash("x"),
                joined_on=1,
            )
            db.session.add(other_author)
            db.session.commit()
            other_author_id = other_author.id

    resp = client.put(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{real_root_id}",
        json={"content": "edited root content", "author_user_id": other_author_id},
    )
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["post"]["content"] == "edited root content"

    with sd_app.app_context():
        _activate_db_exp_bind(exp_id)
        post = db.session.get(Post, real_root_id)
        assert post.tweet == "edited root content"
        assert str(post.user_id) == str(other_author_id)


def test_update_real_post_rejects_unknown_author_standard(sd_app, sd_client):
    client, _admin_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase8-std-bad-author")
    author_id = _make_author(sd_app, exp_id)
    mapping = _publish_root_child_grandchild(client, exp_id, author_id)

    resp = client.put(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['root']}",
        json={"author_user_id": 999999},
    )
    assert resp.status_code == 400, resp.data
    assert resp.get_json()["error"]["code"] == "author_not_found"


def test_delete_real_post_with_descendants_is_refused_standard(sd_app, sd_client):
    client, _admin_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase8-std-del-refused")
    author_id = _make_author(sd_app, exp_id)
    mapping = _publish_root_child_grandchild(client, exp_id, author_id)

    resp = client.delete(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['root']}"
    )
    assert resp.status_code == 409, resp.data
    assert resp.get_json()["error"]["code"] == "post_has_descendants"


def test_delete_leaf_real_post_succeeds_standard(sd_app, sd_client):
    from y_web.src.experiment.context import _activate_db_exp_bind
    from y_web.src.models import Post

    client, _admin_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase8-std-del-leaf")
    author_id = _make_author(sd_app, exp_id)
    mapping = _publish_root_child_grandchild(client, exp_id, author_id)

    resp = client.delete(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['grandchild']}"
    )
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["deleted"] is True

    with sd_app.app_context():
        _activate_db_exp_bind(exp_id)
        assert db.session.get(Post, mapping["grandchild"]) is None
        assert db.session.get(Post, mapping["child"]) is not None


def test_delete_subtree_cascades_across_satellite_tables_standard(sd_app, sd_client):
    from y_web.src.experiment.context import _activate_db_exp_bind, experiment_db_bind
    from y_web.src.models import Post, Post_topics, Post_Toxicity

    client, _admin_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase8-std-del-subtree")
    author_id = _make_author(sd_app, exp_id)
    mapping = _publish_root_child_grandchild(client, exp_id, author_id)

    with sd_app.app_context():
        with experiment_db_bind(exp_id):
            from y_web.src.experiment.helpers import _ensure_experiment_orm_tables
            from y_web.src.models import Interests

            # Interests has no raw-SQL DDL entry (see
            # test_scenario_design_fase3_threads.py's
            # test_vocab_topics_and_emotions_read_the_real_experiment_tables) --
            # a freshly materialized experiment db doesn't have it yet.
            _ensure_experiment_orm_tables(db.engines["db_exp"])
            interest = Interests(interest="politics")
            db.session.add(interest)
            db.session.commit()
            db.session.add(Post_topics(post_id=mapping["child"], topic_id=interest.iid))
            db.session.add(Post_Toxicity(post_id=mapping["grandchild"], toxicity=0.9))
            db.session.commit()

    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['root']}/delete_subtree"
    )
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["deleted_count"] == 3
    assert set(body["deleted_ids"]) == {
        str(mapping["root"]),
        str(mapping["child"]),
        str(mapping["grandchild"]),
    }

    with sd_app.app_context():
        _activate_db_exp_bind(exp_id)
        assert db.session.get(Post, mapping["root"]) is None
        assert db.session.get(Post, mapping["child"]) is None
        assert db.session.get(Post, mapping["grandchild"]) is None
        assert (
            db.session.query(Post_topics).filter_by(post_id=mapping["child"]).count()
            == 0
        )
        assert (
            db.session.query(Post_Toxicity)
            .filter_by(post_id=mapping["grandchild"])
            .count()
            == 0
        )


def test_real_content_operations_blocked_while_experiment_running_standard(
    sd_app, sd_client
):
    from y_web.src.models import Exps

    client, _admin_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase8-std-running")
    author_id = _make_author(sd_app, exp_id)
    mapping = _publish_root_child_grandchild(client, exp_id, author_id)

    with sd_app.app_context():
        # Exps is db_admin-bound, never touched by the db_exp swap.
        exp = db.session.get(Exps, exp_id)
        exp.running = 1
        db.session.commit()

    put_resp = client.put(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['grandchild']}",
        json={"content": "nope"},
    )
    assert put_resp.status_code == 409
    assert put_resp.get_json()["error"]["code"] == "experiment_running"

    delete_resp = client.delete(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['grandchild']}"
    )
    assert delete_resp.status_code == 409
    assert delete_resp.get_json()["error"]["code"] == "experiment_running"

    subtree_resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['root']}/delete_subtree"
    )
    assert subtree_resp.status_code == 409
    assert subtree_resp.get_json()["error"]["code"] == "experiment_running"


# ---------------------------------------------------------------------
# HPC family
# ---------------------------------------------------------------------


@pytest.fixture
def hpc_only():
    if not _ysimulator_is_installed():
        pytest.skip("external/YSimulator not checked out in this environment")


def test_update_and_delete_subtree_real_posts_hpc(sd_app, sd_client, hpc_only):
    from y_web.src.models import Exps

    client, _admin_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase8-hpc-exp", simulator_type="HPC")
    hpc_author_id = _seed_hpc_author(sd_app, exp_id)
    mapping = _publish_root_child_grandchild(
        client, exp_id, hpc_author_id, simulator_type="HPC"
    )

    from YSimulator.YServer.classes.models import Post as HpcPost
    from YSimulator.YServer.classes.models import PostToxicity as HpcPostToxicity

    hpc_session = _hpc_session_module().hpc_session

    with sd_app.app_context():
        exp = db.session.get(Exps, exp_id)
        with hpc_session(exp) as hsession:
            # HpcPostToxicity.id has no default/autoincrement declared in
            # YSimulator's own schema -- an explicit id is required, same
            # as every other HPC-family row in these tests.
            import uuid as _uuid

            hsession.add(
                HpcPostToxicity(
                    id=str(_uuid.uuid4()), post_id=mapping["grandchild"], toxicity=0.5
                )
            )
            hsession.commit()

    update_resp = client.put(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['root']}",
        json={"content": "edited HPC root"},
    )
    assert update_resp.status_code == 200, update_resp.data
    assert update_resp.get_json()["post"]["content"] == "edited HPC root"

    subtree_resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/real_posts/{mapping['root']}/delete_subtree"
    )
    assert subtree_resp.status_code == 200, subtree_resp.data
    assert subtree_resp.get_json()["deleted_count"] == 3

    with sd_app.app_context():
        exp = db.session.get(Exps, exp_id)
        with hpc_session(exp) as hsession:
            assert hsession.get(HpcPost, mapping["root"]) is None
            assert hsession.get(HpcPost, mapping["child"]) is None
            assert hsession.get(HpcPost, mapping["grandchild"]) is None
            assert (
                hsession.query(HpcPostToxicity)
                .filter_by(post_id=mapping["grandchild"])
                .count()
                == 0
            )
