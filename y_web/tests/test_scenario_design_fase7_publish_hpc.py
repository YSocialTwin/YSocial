"""Integration test: Fase 7 validate/preview/publish (endpoints 18-20) on
a real create_app() boot against an HPC experiment -- exercises the real
``HpcMaterializationAdapter`` (adapters/hpc.py) against a real HPC
physical schema (YSimulator's own ORM models, not db_exp's Integer-typed
core models): real ``Post`` rows created with UUID ids, the
thread_id/comment_to propagation invariant (piano tecnico §13) verified
on real materialized data with string ids, one topic metadata row,
fingerprint mismatch rejection, and parametrized fault injection with
full rollback verification across *both* halves of the atomic write
(real content and sd_publication/sd_id_mapping bookkeeping -- see
decisions.md §F7.2 for why this needed a different atomicity design than
Standard's).

Same sandbox sqlite-write limitation as every integration test in this
module (ScenarioDesign/docs/decisions.md §F1.4/§F1.5/§F3.x/§F6.10): every
test here needs a real per-experiment sqlite file and skips cleanly via
``_can_actually_write_sqlite_files()`` in this environment. Re-run in a
real dev environment (where external/YSimulator is checked out and
sqlite file writes under y_web/experiments/ are not restricted) for full
coverage.

Piano di implementazione, Fase 7.
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
        os.path.join("y_web", "experiments", f"_probe_fase7_{uuid.uuid4().hex}")
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


def _make_hpc_exp(app, name="sd-fase7-exp"):
    """Create an ``Exps`` row with ``simulator_type="HPC"`` *and* seed its
    physical sqlite file with YSimulator's real schema (``Base.metadata.
    create_all``) at the same path ``resolve_experiment_db_path`` will
    later resolve -- the dual-schema-same-file design this adapter relies
    on (decisions.md §F7.2), not a separate database.
    """
    import os

    from sqlalchemy import create_engine

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    folder = get_writable_path(os.path.join("y_web", "experiments", name))
    os.makedirs(folder, exist_ok=True)
    db_path = os.path.join(folder, "database_server.db")

    from YSimulator.YServer.classes.models import Base as HpcBase

    engine = create_engine(f"sqlite:///{db_path}")
    HpcBase.metadata.create_all(engine)
    engine.dispose()

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            simulator_type="HPC",
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


def _seed_hpc_content(app, exp_id, *, username="hpc_author"):
    """Insert one HPC ``User_mgmt`` row (author) and one ``Interest`` row
    (topic metadata), directly through ``hpc_session`` -- the same path
    ``adapters/hpc.py`` itself uses, exercising the real bootstrap.
    """
    import uuid

    from YSimulator.YServer.classes.models import Interest as HpcInterest
    from YSimulator.YServer.classes.models import User_mgmt as HpcUser

    from modules.scenario_editor.backend.hpc_session import hpc_session
    from y_web.src.models import Exps

    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        user_id = str(uuid.uuid4())
        topic_id = str(uuid.uuid4())
        with hpc_session(exp) as hsession:
            hsession.add(HpcUser(id=user_id, username=username))
            hsession.add(HpcInterest(iid=topic_id, interest="politics"))
            hsession.commit()
        return user_id, topic_id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


pytestmark = pytest.mark.integration


@pytest.fixture
def sd_app():
    if not _suite_is_installed():
        pytest.skip("ScenarioDesign suite not checked out in this environment")
    if not _ysimulator_is_installed():
        pytest.skip("external/YSimulator not checked out in this environment")
    if not _can_actually_write_sqlite_files():
        pytest.skip(
            "Sandbox cannot commit new sqlite files under this repo's "
            "y_web/experiments/ subtree in this environment (known "
            "limitation, ScenarioDesign/docs/decisions.md §F1.4/§F1.5/"
            "§F3.x/§F7.7) -- re-run in a real dev environment to exercise "
            "this module."
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
        admin_user = User_mgmt(
            username="fase7_admin",
            email="fase7_admin@test.com",
            password=generate_password_hash("test123"),
            joined_on=1234567890,
        )
        db.session.add(admin_user)
        db.session.commit()
        admin_id = admin_user.id
    _login(client, admin_id)
    return client, admin_id


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


def _publish(client, exp_id, scenario_id, *, idempotency_key=None, json_body=None):
    headers = {}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/publish",
        json=json_body or {},
        headers=headers,
    )


def test_hpc_publish_materializes_real_uuid_rows_with_correct_thread_propagation(
    sd_app, sd_client
):
    """root -> child -> grandchild, one topic metadata row on the root;
    asserts every materialized id is a real UUID string (never an int),
    and that the grandchild's ``thread_id`` equals the *root's* real id,
    not its immediate parent's (piano tecnico §13, same invariant as
    Fase 6, now verified against HPC's own physical schema)."""
    import uuid as uuid_module

    from YSimulator.YServer.classes.models import Post as HpcPost

    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, "sd-fase7-exp-success")
    author_user_id, topic_id = _seed_hpc_content(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)

    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=author_user_id, content="root",
    )
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="c1", parent_tmp_id="root", author_user_id=author_user_id, content="child",
    )
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="c1a", parent_tmp_id="c1", author_user_id=author_user_id, content="grandchild",
    )

    with sd_app.app_context():
        from modules.scenario_editor.backend.models import (
            ScenarioDesignDraftMetadata,
            ScenarioDesignDraftPost,
        )

        root_draft = db.session.query(ScenarioDesignDraftPost).filter_by(tmp_id="root").first()
        db.session.add(
            ScenarioDesignDraftMetadata(
                draft_post_id=root_draft.id,
                metadata_type="topic",
                metadata_value=f'{{"topic_id": "{topic_id}"}}',
            )
        )
        db.session.commit()

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 201, resp.data
    body = resp.get_json()
    assert body["publication"]["post_count_created"] == 3
    assert body["publication"]["metadata_count_created"] == 1

    id_mapping = body["id_mapping"]
    for tmp_id, real_id in id_mapping.items():
        assert isinstance(real_id, str)
        uuid_module.UUID(real_id)  # raises ValueError if not a real UUID

    with sd_app.app_context():
        from modules.scenario_editor.backend.hpc_session import hpc_session
        from y_web.src.models import Exps

        exp = db.session.get(Exps, exp_id)
        with hpc_session(exp) as hsession:
            root_real_id = id_mapping["root"]
            grandchild_real_id = id_mapping["c1a"]
            grandchild_post = hsession.get(HpcPost, grandchild_real_id)
            assert grandchild_post.thread_id == root_real_id
            assert grandchild_post.comment_to == id_mapping["c1"]


@pytest.mark.parametrize("fail_after_step", [9, 13, 17])
def test_hpc_fault_injection_rolls_back_both_halves_of_the_atomic_write(
    sd_app, sd_client, fail_after_step
):
    """Same principle as Fase 6's fault injection test, but verifies the
    HPC-specific atomicity design (§F7.2): a failure after step 9/13/17
    must roll back *both* the real content (Post rows, via hpc_session)
    *and* the sd_publication/sd_id_mapping bookkeeping together, since
    both are written through the same session/transaction."""
    from modules.scenario_editor.backend.adapters.base import get_adapter_for
    from modules.scenario_editor.backend.hpc_session import hpc_session
    from modules.scenario_editor.backend.models import ScenarioDesignIdMapping, ScenarioDesignPublication
    from y_web.src.models import Exps
    from YSimulator.YServer.classes.models import Post as HpcPost

    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, f"sd-fase7-exp-fault-{fail_after_step}")
    author_user_id, _topic_id = _seed_hpc_content(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=author_user_id, content="root",
    )
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="c1", parent_tmp_id="root", author_user_id=author_user_id, content="child",
    )

    with sd_app.app_context():
        from modules.scenario_editor.backend.models import ScenarioDesignScenario

        exp = db.session.get(Exps, exp_id)
        scenario = db.session.get(ScenarioDesignScenario, scenario_id)

        with hpc_session(exp) as hsession:
            post_count_before = hsession.query(HpcPost).count()
        publication_count_before = db.session.query(ScenarioDesignPublication).count()
        mapping_count_before = db.session.query(ScenarioDesignIdMapping).count()

        adapter = get_adapter_for(exp)
        with pytest.raises(RuntimeError):
            adapter.publish(
                scenario,
                requested_by_user_id=admin_id,
                _fail_after_step=fail_after_step,
            )

        with hpc_session(exp) as hsession:
            assert hsession.query(HpcPost).count() == post_count_before
        db.session.expire_all()
        assert db.session.query(ScenarioDesignPublication).count() == publication_count_before
        assert db.session.query(ScenarioDesignIdMapping).count() == mapping_count_before


def test_hpc_fingerprint_mismatch_rejects_publish(sd_app, sd_client):
    from y_web.src.models import Exps

    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, "sd-fase7-exp-fingerprint")
    author_user_id, _topic_id = _seed_hpc_content(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=author_user_id, content="root",
    )

    # Simulate the base experiment changing after the scenario was opened
    # by inserting a new real Round into the HPC physical schema.
    import uuid

    from YSimulator.YServer.classes.models import Round as HpcRound
    from modules.scenario_editor.backend.hpc_session import hpc_session

    with sd_app.app_context():
        exp = db.session.get(Exps, exp_id)
        with hpc_session(exp) as hsession:
            hsession.add(HpcRound(id=str(uuid.uuid4()), day=1, hour=0))
            hsession.commit()

    resp = _publish(client, exp_id, scenario_id)
    assert resp.status_code == 409, resp.data
    assert resp.get_json()["error"]["code"] == "fingerprint_mismatch"


def test_hpc_idempotency_key_replay_does_not_duplicate(sd_app, sd_client):
    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, "sd-fase7-exp-idempotency")
    author_user_id, _topic_id = _seed_hpc_content(sd_app, exp_id)
    scenario_id = _create_scenario(client, exp_id)
    thread_id = _create_thread(client, exp_id, scenario_id)
    _add_post(
        client, exp_id, scenario_id, thread_id,
        tmp_id="root", parent_tmp_id=None, author_user_id=author_user_id, content="root",
    )

    key = "fase7-idem-key-1"
    first = _publish(client, exp_id, scenario_id, idempotency_key=key)
    assert first.status_code == 201, first.data
    second = _publish(client, exp_id, scenario_id, idempotency_key=key)
    assert second.status_code == 200, second.data  # idempotent replay -> 200, not 201
    assert first.get_json()["publication"]["id"] == second.get_json()["publication"]["id"]
    assert first.get_json()["id_mapping"] == second.get_json()["id_mapping"]

    with sd_app.app_context():
        from YSimulator.YServer.classes.models import Post as HpcPost
        from modules.scenario_editor.backend.hpc_session import hpc_session
        from y_web.src.models import Exps

        exp = db.session.get(Exps, exp_id)
        with hpc_session(exp) as hsession:
            assert hsession.query(HpcPost).count() == 1
