"""Integration test: Fase 6 validate/preview/publish/audit (endpoints
18-21) end-to-end on a real create_app() boot, with the Scenario Design
suite installed -- exercises the real Standard materialization adapter
(adapters/standard.py) against a real db_exp sqlite file: real Post rows
created, real satellite rows (Post_Toxicity/Post_topics) created, the
thread_id/comment_to propagation invariant (piano tecnico §13) verified
on real materialized data, fingerprint/running/lock rejections, parametrized
fault injection with full rollback verification, and X-Idempotency-Key
replay.

Same sandbox sqlite-write limitation as every other integration test in
this module (ScenarioDesign/docs/decisions.md §F1.4/§F1.5/§F3.x): every
test here needs a real per-experiment sqlite file and skips cleanly via
``_can_actually_write_sqlite_files()`` in this environment.

User-reported (2026-10-08, "yes please" to extending the fase3 fix): this
file had the same login-identity bug as
test_scenario_design_fase3_threads.py (see that module's docstring for the
full explanation), plus two further issues specific to this file:

1. Every ``with sd_app.app_context(): ...`` block below that queries or
   inserts a ``db_exp``-bound model (``Post``, ``Rounds``, ``Post_topics``,
   ``Post_Toxicity``, or any ``ScenarioDesign*`` plugin model) was relying
   on the ``db_exp`` bind still pointing at the target experiment from a
   *previous* request -- but ``teardown_experiment_context()`` (a
   ``teardown_request`` hook) restores the previous bind at the end of
   *every* request, including ones made through the Flask test client, so
   by the time that code ran the bind had already been reset. Fixed by
   calling ``_activate_db_exp_bind(exp_id)`` (the same helper
   ``setup_experiment_context()`` uses per-request) before each such
   block, mirroring what production does for every exp_id-scoped request.
2. ``modules.scenario_editor.backend.models`` is never importable as a
   plain top-level dotted path -- production deliberately does not add
   the suite's repo to ``sys.path`` (see
   ``y_web/src/external_runtime/backend_plugins.py``'s module docstring)
   and instead imports it under a private, suite-scoped synthetic
   namespace. Fixed by reusing that same ``_import_from_suite`` helper,
   as in ``test_scenario_design_fase4_llm.py``.

Piano di implementazione, Fase 6.
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


def _scenario_design_models():
    """See this module's docstring (point 2) for why this indirection is
    required instead of a plain ``import modules...``."""
    from y_web.src.external_runtime.backend_plugins import _import_from_suite

    return _import_from_suite(
        "scenario_design", "modules.scenario_editor.backend.models"
    )


def _standard_adapter_module():
    from y_web.src.external_runtime.backend_plugins import _import_from_suite

    return _import_from_suite(
        "scenario_design", "modules.scenario_editor.backend.adapters.standard"
    )


def _make_exp(app, name="sd-fase6-exp"):
    """Random suffix avoids colliding with a previous run's leftover,
    gitignored experiment folder on disk (y_web/experiments/ is real,
    persistent state -- see test_scenario_design_fase3_threads.py).

    Also writes a minimal ``config_server.json`` into the folder.
    User-reported (2026-10-08): without this, every /publish test here
    failed downstream with "published_experiment_copy_failed" --
    ``_create_single_experiment_copy()`` (the real production helper this
    endpoint reuses to materialize the published copy,
    y_web/routes/admin/sub/experiments/_crud.py) requires this file to
    exist in the SOURCE experiment's folder and bails out with False (no
    exception, just a silent False) the moment it is missing. Every real
    experiment created through the UI always has one; this test fixture
    is the only thing that was skipping it. The exact field values don't
    matter here -- the copy helper overwrites name/port/database_uri/
    data_path unconditionally -- only that the file exists and is valid
    JSON (see a real experiment folder under y_web/experiments/ for the
    full real-world shape)."""
    import json
    import os
    import uuid

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    folder_name = f"{name}-{uuid.uuid4().hex[:8]}"
    folder = get_writable_path(os.path.join("y_web", "experiments", folder_name))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "config_server.json"), "w") as f:
        json.dump(
            {
                "platform_type": "microblogging",
                "name": folder_name,
                "port": 5000,
                "database_uri": os.path.join(folder, "database_server.db"),
                "data_path": folder + os.sep,
            },
            f,
        )

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


def _make_author(app, exp_id, username="fase6_author", user_id="1"):
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
    """Logs in as a real Admin_users account (see this module's docstring,
    and test_scenario_design_fase3_threads.py, for the full root-cause
    explanation of why a User_mgmt login specifically breaks under the
    db_exp bind swap)."""
    from y_web.src.models import Admin_users

    client = sd_app.test_client()
    with sd_app.app_context():
        admin_user = Admin_users(
            username="sd_fase6_admin",
            email="sd_fase6_admin@test.com",
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


def _seed_vocab(app, exp_id):
    """Insert one Interests row and one Emotions row into *exp_id*'s own
    per-experiment database.

    Both models are ``db_exp``-bound (y_web/src/models/experiment.py), so
    (unlike Exps, which is db_admin-bound) this must go through
    ``experiment_db_bind(exp_id)`` explicitly -- the ambient bind left
    over from any earlier request is already gone by the time this runs,
    since ``teardown_experiment_context()`` restores it at the end of
    *every* request, test-client ones included (see this module's
    docstring).
    """
    from y_web.src.experiment.context import experiment_db_bind
    from y_web.src.models import Emotions, Interests

    with app.app_context():
        with experiment_db_bind(exp_id):
            interest = Interests(interest="politics")
            emotion = Emotions(emotion="joy", icon="smile")
            db.session.add_all([interest, emotion])
            db.session.commit()
            return interest.iid, emotion.id


def _publish(client, exp_id, scenario_id, *, idempotency_key=None, json_body=None):
    """``published_experiment_name`` is a required field (see
    routes_publish.py's ``publish_scenario``: "A name for the published
    experiment is required"), uncovered until the login fix above let
    this endpoint run far enough to actually reach that check. Default to
    a fresh, random name per call so repeated calls (e.g. idempotency-key
    replay, or separate test runs) never collide on
    ``experiment_name_exists`` unless the test is specifically asserting
    repeated use of the exact same body (idempotent replay passes its own
    ``json_body`` with a fixed name, by design)."""
    import uuid

    headers = {}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    body = (
        json_body
        if json_body is not None
        else {"published_experiment_name": f"fase6-published-{uuid.uuid4().hex[:8]}"}
    )
    return client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/publish",
        json=body,
        headers=headers,
    )


def test_validate_preview_and_publish_materialize_real_rows_with_correct_thread_propagation(
    sd_app, sd_client
):
    """Covers the plan's "pubblicazione riuscita" and "thread_id/comment_to"
    test rows in one scenario: root -> child -> grandchild, one toxicity
    metadata row and one topic metadata row, verifies preview == real
    counts, and asserts the grandchild's materialized ``thread_id`` equals
    the *root's* real id, not its immediate parent's (piano tecnico §13).
    """
    from y_web.src.experiment.context import _activate_db_exp_bind
    from y_web.src.models import Post, Post_topics, Post_Toxicity

    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase6-exp-success")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    topic_id, _emotion_id = _seed_vocab(sd_app, exp_id)

    thread_id = _create_thread(client, exp_id, scenario_id)
    root_id = _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=author_id,
        content="root content",
    )
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="c1",
        parent_tmp_id="root",
        author_user_id=author_id,
        content="child content",
    )
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="c1a",
        parent_tmp_id="c1",
        author_user_id=author_id,
        content="grandchild content",
    )

    with sd_app.app_context():
        _activate_db_exp_bind(exp_id)
        models = _scenario_design_models()
        ScenarioDesignDraftMetadata = models.ScenarioDesignDraftMetadata
        ScenarioDesignDraftPost = models.ScenarioDesignDraftPost

        root_draft = (
            db.session.query(ScenarioDesignDraftPost).filter_by(tmp_id="root").first()
        )
        grandchild_draft = (
            db.session.query(ScenarioDesignDraftPost).filter_by(tmp_id="c1a").first()
        )
        db.session.add(
            ScenarioDesignDraftMetadata(
                draft_post_id=root_draft.id,
                metadata_type="toxicity",
                metadata_value='{"toxicity": 0.9}',
            )
        )
        db.session.add(
            ScenarioDesignDraftMetadata(
                draft_post_id=grandchild_draft.id,
                metadata_type="topic",
                metadata_value=f'{{"topic_id": {topic_id}}}',
            )
        )
        db.session.commit()

    validate_resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/validate"
    )
    assert validate_resp.status_code == 200, validate_resp.data
    assert validate_resp.get_json()["valid"] is True, validate_resp.get_json()

    preview_resp = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/publish/preview"
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.get_json()["preview"]
    assert preview == {"thread_count": 1, "post_count": 3, "metadata_count": 2}

    publish_resp = _publish(client, exp_id, scenario_id)
    assert publish_resp.status_code == 201, publish_resp.data
    body = publish_resp.get_json()
    assert body["publication"]["post_count_created"] == 3
    assert body["publication"]["metadata_count_created"] == 2
    assert body["publication"]["idempotent_replay"] is False
    id_mapping = body["id_mapping"]
    assert set(id_mapping.keys()) == {"root", "c1", "c1a"}

    with sd_app.app_context():
        _activate_db_exp_bind(exp_id)
        real_root_id = int(id_mapping["root"])
        real_c1_id = int(id_mapping["c1"])
        real_grandchild_id = int(id_mapping["c1a"])

        root_post = db.session.get(Post, real_root_id)
        child_post = db.session.get(Post, real_c1_id)
        grandchild_post = db.session.get(Post, real_grandchild_id)

        assert root_post.thread_id == root_post.id
        assert root_post.comment_to == -1
        # The key invariant (piano tecnico §13): every descendant's
        # thread_id is the ROOT's real id, never the immediate parent's,
        # regardless of nesting depth.
        assert child_post.thread_id == root_post.id
        assert grandchild_post.thread_id == root_post.id
        assert child_post.comment_to == root_post.id
        assert grandchild_post.comment_to == child_post.id

        toxicity_row = (
            db.session.query(Post_Toxicity).filter_by(post_id=real_root_id).first()
        )
        assert toxicity_row is not None
        assert toxicity_row.toxicity == 0.9

        topic_row = (
            db.session.query(Post_topics).filter_by(post_id=real_grandchild_id).first()
        )
        assert topic_row is not None
        assert topic_row.topic_id == topic_id

        models = _scenario_design_models()
        STATUS_PUBLISHED = models.STATUS_PUBLISHED
        ScenarioDesignScenario = models.ScenarioDesignScenario

        scenario = db.session.get(ScenarioDesignScenario, scenario_id)
        assert scenario.status == STATUS_PUBLISHED
        assert scenario.lock_token is None


@pytest.mark.parametrize("fail_after_step", [9, 13, 17])
def test_fault_injection_rolls_back_completely(sd_app, sd_client, fail_after_step):
    """Piano di implementazione Fase 6 risk mitigation: the fault
    injection test must be parametrized across several of the 21 steps,
    not just one fixed point."""
    from y_web.src.experiment.context import _activate_db_exp_bind
    from y_web.src.models import Post

    client = sd_client
    exp_id = _make_exp(sd_app, f"sd-fase6-exp-fault-{fail_after_step}")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    topic_id, _emotion_id = _seed_vocab(sd_app, exp_id)

    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=author_id,
        content="root",
    )

    with sd_app.app_context():
        _activate_db_exp_bind(exp_id)
        models = _scenario_design_models()
        ScenarioDesignDraftMetadata = models.ScenarioDesignDraftMetadata
        ScenarioDesignDraftPost = models.ScenarioDesignDraftPost
        ScenarioDesignIdMapping = models.ScenarioDesignIdMapping
        ScenarioDesignPublication = models.ScenarioDesignPublication
        ScenarioDesignScenario = models.ScenarioDesignScenario
        StandardMaterializationAdapter = (
            _standard_adapter_module().StandardMaterializationAdapter
        )

        root_draft = (
            db.session.query(ScenarioDesignDraftPost).filter_by(tmp_id="root").first()
        )
        db.session.add(
            ScenarioDesignDraftMetadata(
                draft_post_id=root_draft.id,
                metadata_type="topic",
                metadata_value=f'{{"topic_id": {topic_id}}}',
            )
        )
        db.session.commit()

        post_count_before = db.session.query(Post).count()
        mapping_count_before = db.session.query(ScenarioDesignIdMapping).count()
        publication_count_before = db.session.query(ScenarioDesignPublication).count()

        scenario = db.session.get(ScenarioDesignScenario, scenario_id)
        adapter = StandardMaterializationAdapter()
        with pytest.raises(
            RuntimeError, match=f"injected test failure after step {fail_after_step}"
        ):
            adapter.publish(
                scenario,
                requested_by_user_id=author_id,
                _fail_after_step=fail_after_step,
            )

        db.session.expire_all()
        post_count_after = db.session.query(Post).count()
        mapping_count_after = db.session.query(ScenarioDesignIdMapping).count()
        publication_count_after = db.session.query(ScenarioDesignPublication).count()

        assert post_count_after == post_count_before
        assert mapping_count_after == mapping_count_before
        assert publication_count_after == publication_count_before

        scenario = db.session.get(ScenarioDesignScenario, scenario_id)
        assert scenario.status != "published"
        assert scenario.lock_token is None
        assert scenario.locked_by is None


def test_fingerprint_mismatch_rejects_publish(sd_app, sd_client):
    from y_web.src.experiment.context import _activate_db_exp_bind
    from y_web.src.models import Post, Rounds

    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase6-exp-fingerprint")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=author_id,
    )

    # Simulate "the base experiment changed since this scenario was last
    # opened" by inserting unrelated content directly, bypassing Scenario
    # Design entirely (as the real simulation would).
    with sd_app.app_context():
        _activate_db_exp_bind(exp_id)
        db.session.add(Rounds(day=1, hour=1))
        db.session.add(Post(tweet="unrelated real content", round=1, user_id=author_id))
        db.session.commit()

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 409, resp.data
    assert resp.get_json()["error"]["code"] == "fingerprint_mismatch"

    # Re-opening the scenario (GET) resyncs the fingerprint; publish then
    # succeeds (piano tecnico §12: "ricarica lo scenario").
    reload_resp = client.get(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}"
    )
    assert reload_resp.status_code == 200
    retry_resp = _publish(client, exp_id, scenario_id)
    assert retry_resp.status_code == 201, retry_resp.data


def test_running_experiment_rejects_publish(sd_app, sd_client):
    from y_web.src.models import Exps

    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase6-exp-running")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=author_id,
    )

    with sd_app.app_context():
        # Exps is db_admin-bound (y_web/src/models/admin.py), never
        # touched by the db_exp swap, so no experiment_db_bind needed here.
        exp = db.session.get(Exps, exp_id)
        exp.running = 1
        db.session.commit()

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 409, resp.data
    assert resp.get_json()["error"]["code"] == "experiment_running"


def test_idempotency_key_replay_does_not_duplicate(sd_app, sd_client):
    from y_web.src.experiment.context import _activate_db_exp_bind
    from y_web.src.models import Post

    client = sd_client
    exp_id = _make_exp(sd_app, "sd-fase6-exp-idempotent")
    author_id = _make_author(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=author_id,
    )

    key = "fase6-idem-key-1"
    body = {"published_experiment_name": "fase6-idem-published"}
    first = _publish(client, exp_id, scenario_id, idempotency_key=key, json_body=body)
    assert first.status_code == 201, first.data
    first_publication_id = first.get_json()["publication"]["id"]

    second = _publish(client, exp_id, scenario_id, idempotency_key=key, json_body=body)
    assert second.status_code == 200, second.data
    second_body = second.get_json()
    assert second_body["publication"]["idempotent_replay"] is True
    assert second_body["publication"]["id"] == first_publication_id

    with sd_app.app_context():
        _activate_db_exp_bind(exp_id)
        assert db.session.query(Post).count() == 1
