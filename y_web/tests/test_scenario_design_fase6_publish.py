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


def _make_exp(app, name="sd-fase6-exp"):
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
    from y_web.src.models import User_mgmt

    client = sd_app.test_client()
    with sd_app.app_context():
        test_user = User_mgmt(
            username="fase6_author",
            email="fase6_author@test.com",
            password=generate_password_hash("test123"),
            joined_on=1234567890,
        )
        db.session.add(test_user)
        db.session.commit()
        user_id = test_user.id
    _login(client, user_id)
    return client, user_id


def _create_scenario(client, exp_id, name="S1"):
    resp = client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios", json={"name": name}
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


def _add_post(client, exp_id, scenario_id, thread_id, *, tmp_id, parent_tmp_id, author_user_id, content=""):
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


def _seed_vocab(app):
    """Insert one Interests row and one Emotions row into the
    currently-bound db_exp (must be called right after a request already
    scoped the bind to the target experiment -- see module docstring in
    ``adapters/fingerprint.py`` for the ``db_exp`` activation mechanism).
    """
    from y_web.src.models import Emotions, Interests

    with app.app_context():
        interest = Interests(interest="politics")
        emotion = Emotions(emotion="joy", icon="smile")
        db.session.add_all([interest, emotion])
        db.session.commit()
        return interest.iid, emotion.id


def _publish(client, exp_id, scenario_id, *, idempotency_key=None, json_body=None):
    headers = {}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/publish",
        json=json_body or {},
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
    from y_web.src.models import Post
    from y_web.src.models import Post_topics, Post_Toxicity

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase6-exp-success")
    scenario_id = _create_scenario(client, exp_id)
    topic_id, _emotion_id = _seed_vocab(sd_app)

    thread_id = _create_thread(client, exp_id, scenario_id)
    root_id = _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=user_id, content="root content",
    )
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="c1", parent_tmp_id="root", author_user_id=user_id, content="child content",
    )
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="c1a", parent_tmp_id="c1", author_user_id=user_id, content="grandchild content",
    )

    with sd_app.app_context():
        from modules.scenario_editor.backend.models import ScenarioDesignDraftMetadata, ScenarioDesignDraftPost

        root_draft = db.session.query(ScenarioDesignDraftPost).filter_by(tmp_id="root").first()
        grandchild_draft = db.session.query(ScenarioDesignDraftPost).filter_by(tmp_id="c1a").first()
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

        toxicity_row = db.session.query(Post_Toxicity).filter_by(post_id=real_root_id).first()
        assert toxicity_row is not None
        assert toxicity_row.toxicity == 0.9

        topic_row = db.session.query(Post_topics).filter_by(post_id=real_grandchild_id).first()
        assert topic_row is not None
        assert topic_row.topic_id == topic_id

        from modules.scenario_editor.backend.models import STATUS_PUBLISHED, ScenarioDesignScenario

        scenario = db.session.get(ScenarioDesignScenario, scenario_id)
        assert scenario.status == STATUS_PUBLISHED
        assert scenario.lock_token is None


@pytest.mark.parametrize("fail_after_step", [9, 13, 17])
def test_fault_injection_rolls_back_completely(sd_app, sd_client, fail_after_step):
    """Piano di implementazione Fase 6 risk mitigation: the fault
    injection test must be parametrized across several of the 21 steps,
    not just one fixed point."""
    from y_web.src.models import Post

    from modules.scenario_editor.backend.adapters.standard import StandardMaterializationAdapter
    from modules.scenario_editor.backend.models import (
        ScenarioDesignIdMapping,
        ScenarioDesignPublication,
        ScenarioDesignScenario,
    )

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, f"sd-fase6-exp-fault-{fail_after_step}")
    scenario_id = _create_scenario(client, exp_id)
    topic_id, _emotion_id = _seed_vocab(sd_app)

    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=user_id, content="root",
    )

    with sd_app.app_context():
        from modules.scenario_editor.backend.models import ScenarioDesignDraftMetadata, ScenarioDesignDraftPost

        root_draft = db.session.query(ScenarioDesignDraftPost).filter_by(tmp_id="root").first()
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
        with pytest.raises(RuntimeError, match=f"injected test failure after step {fail_after_step}"):
            adapter.publish(
                scenario, requested_by_user_id=user_id, _fail_after_step=fail_after_step
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
    from y_web.src.models import Post, Rounds

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase6-exp-fingerprint")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=user_id,
    )

    # Simulate "the base experiment changed since this scenario was last
    # opened" by inserting unrelated content directly, bypassing Scenario
    # Design entirely (as the real simulation would).
    with sd_app.app_context():
        db.session.add(Rounds(day=1, hour=1))
        db.session.add(Post(tweet="unrelated real content", round=1, user_id=user_id))
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

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase6-exp-running")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=user_id,
    )

    with sd_app.app_context():
        exp = db.session.get(Exps, exp_id)
        exp.running = 1
        db.session.commit()

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 409, resp.data
    assert resp.get_json()["error"]["code"] == "experiment_running"


def test_idempotency_key_replay_does_not_duplicate(sd_app, sd_client):
    from y_web.src.models import Post

    client, user_id = sd_client
    exp_id = _make_exp(sd_app, "sd-fase6-exp-idempotent")
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=user_id,
    )

    key = "fase6-idem-key-1"
    first = _publish(client, exp_id, scenario_id, idempotency_key=key)
    assert first.status_code == 201, first.data
    first_publication_id = first.get_json()["publication"]["id"]

    second = _publish(client, exp_id, scenario_id, idempotency_key=key)
    assert second.status_code == 200, second.data
    second_body = second.get_json()
    assert second_body["publication"]["idempotent_replay"] is True
    assert second_body["publication"]["id"] == first_publication_id

    with sd_app.app_context():
        assert db.session.query(Post).count() == 1
