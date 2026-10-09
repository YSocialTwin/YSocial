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

User-reported (2026-10-08, "yes please" to extending the fase3 fix): this
file had three distinct problems, on top of the shared login-identity bug
(see test_scenario_design_fase3_threads.py's docstring for the full
root-cause explanation of why a User_mgmt login specifically breaks under
the db_exp bind swap -- the same fix applies here: an Admin_users login).
The other two are specific to this file:

1. ``YSimulator`` is never on ``sys.path`` by default -- production
   never imports it in-process except through ``hpc_session.py``'s own
   ``_ensure_ysimulator_on_path()`` bootstrap (see that function's
   docstring: "YSimulator is never imported in-process by YWeb core...").
   Every direct ``from YSimulator...`` import in this file needs that
   same bootstrap called first.
2. Same ``modules.scenario_editor.backend...`` namespace-import issue as
   test_scenario_design_fase4_llm.py and test_scenario_design_fase6_
   publish.py: fixed the same way, via ``_import_from_suite``.

(The experiment-folder-collision issue fixed in the sibling files doesn't
reapply its random-suffix fix verbatim here, since ``_make_hpc_exp``
also seeds a *specific* physical sqlite file at a path derived from the
same name -- the random suffix is still applied, just computed once and
threaded through both the Exps row and the physical schema seeding.)

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


def _scenario_design_module(dotted_path):
    """See this module's docstring (point 2): the plugin's own backend
    package is never importable as a plain top-level ``modules...``
    dotted path (production deliberately avoids adding the suite's repo
    to sys.path, see backend_plugins.py's module docstring) -- it is
    imported under a private, suite-scoped synthetic namespace instead."""
    from y_web.src.external_runtime.backend_plugins import _import_from_suite

    return _import_from_suite("scenario_design", dotted_path)


def _hpc_session_module():
    return _scenario_design_module("modules.scenario_editor.backend.hpc_session")


def _ensure_ysimulator_importable():
    """See this module's docstring (point 1): reuses hpc_session.py's own
    sys.path bootstrap so this test file's direct ``from YSimulator...``
    imports work too. Idempotent and safe to call repeatedly."""
    _hpc_session_module()._ensure_ysimulator_on_path()


def _make_hpc_exp(app, name="sd-fase7-exp"):
    """Create an ``Exps`` row with ``simulator_type="HPC"`` *and* seed its
    physical sqlite file with YSimulator's real schema (``Base.metadata.
    create_all``) at the same path ``resolve_experiment_db_path`` will
    later resolve -- the dual-schema-same-file design this adapter relies
    on (decisions.md §F7.2), not a separate database.

    Random suffix avoids colliding with a previous run's leftover,
    gitignored experiment folder on disk (y_web/experiments/ is real,
    persistent state -- see test_scenario_design_fase3_threads.py)."""
    import os
    import uuid

    from sqlalchemy import create_engine

    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    _ensure_ysimulator_importable()

    folder_name = f"{name}-{uuid.uuid4().hex[:8]}"
    folder = get_writable_path(os.path.join("y_web", "experiments", folder_name))
    os.makedirs(folder, exist_ok=True)
    db_path = os.path.join(folder, "database_server.db")

    from YSimulator.YServer.classes.models import Base as HpcBase

    engine = create_engine(f"sqlite:///{db_path}")
    HpcBase.metadata.create_all(engine)
    engine.dispose()

    # User-reported (2026-10-08): without a server_config.json marker file,
    # _create_single_experiment_copy() (y_web/routes/admin/sub/experiments/
    # _crud.py, reused by routes_publish.py's _create_published_experiment
    # to materialize the published copy) can't tell this is an HPC
    # experiment and misclassifies it as Standard -- which then
    # unconditionally overwrites the already-correct, already-copied HPC
    # physical db file with a copy of Standard's own clean-schema
    # template, corrupting it ("database disk image is malformed" on the
    # next schema check). Every real HPC experiment created through the
    # UI always has this file; this test fixture is the only thing that
    # was skipping it (see test_scenario_design_fase6_publish.py's
    # _make_exp() for the equivalent Standard-family fix,
    # config_server.json).
    import json

    with open(os.path.join(folder, "server_config.json"), "w") as f:
        json.dump(
            {
                "experiment_name": folder_name,
                "server": {"port": 5000},
                "database_uri": db_path,
            },
            f,
        )

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            simulator_type="HPC",
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


def _seed_hpc_content(app, exp_id, *, username="hpc_author"):
    """Insert one HPC ``User_mgmt`` row (author) and one ``Interest`` row
    (topic metadata), directly through ``hpc_session`` -- the same path
    ``adapters/hpc.py`` itself uses, exercising the real bootstrap.

    User-reported (2026-10-08): YSimulator's own ``User_mgmt.password``
    column is ``nullable=False`` (external/YSimulator/YSimulator/YServer/
    classes/models.py) -- unlike the Standard-family db_exp bind's
    User_mgmt, which has no such requirement in practice here. Omitting it
    raised a NOT NULL IntegrityError on every single test in this module,
    masked until now behind the import-path bugs fixed above.
    """
    import uuid

    from werkzeug.security import generate_password_hash
    from YSimulator.YServer.classes.models import Interest as HpcInterest
    from YSimulator.YServer.classes.models import User_mgmt as HpcUser

    from y_web.src.models import Exps

    hpc_session = _hpc_session_module().hpc_session

    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        user_id = str(uuid.uuid4())
        topic_id = str(uuid.uuid4())
        with hpc_session(exp) as hsession:
            hsession.add(
                HpcUser(
                    id=user_id,
                    username=username,
                    password=generate_password_hash("test123"),
                )
            )
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
    """Logs in as a real Admin_users account (see this module's docstring,
    and test_scenario_design_fase3_threads.py, for the full root-cause
    explanation of why a User_mgmt login specifically breaks under the
    db_exp bind swap)."""
    from y_web.src.models import Admin_users

    client = sd_app.test_client()
    with sd_app.app_context():
        admin_user = Admin_users(
            username="sd_fase7_admin",
            email="sd_fase7_admin@test.com",
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


def _publish(client, exp_id, scenario_id, *, idempotency_key=None, json_body=None):
    import uuid

    headers = {}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    body = (
        json_body
        if json_body is not None
        else {"published_experiment_name": f"fase7-published-{uuid.uuid4().hex[:8]}"}
    )
    return client.post(
        f"/admin/scenario_design/api/experiments/{exp_id}/scenarios/{scenario_id}/publish",
        json=body,
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

    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, "sd-fase7-exp-success")
    author_user_id, topic_id = _seed_hpc_content(sd_app, exp_id)
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
        tmp_id="c1",
        parent_tmp_id="root",
        author_user_id=author_user_id,
        content="child",
    )
    _add_post(
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="c1a",
        parent_tmp_id="c1",
        author_user_id=author_user_id,
        content="grandchild",
    )

    with sd_app.app_context():
        # As in test_scenario_design_fase6_publish.py: the db_exp bind
        # left over from the last request is already gone by the time
        # this runs (teardown_experiment_context() restores it at the
        # end of every request, test-client ones included), so this
        # direct query needs its own bind activation.
        from y_web.src.experiment.context import _activate_db_exp_bind

        _activate_db_exp_bind(exp_id)
        models = _scenario_design_module("modules.scenario_editor.backend.models")
        ScenarioDesignDraftMetadata = models.ScenarioDesignDraftMetadata
        ScenarioDesignDraftPost = models.ScenarioDesignDraftPost

        root_draft = (
            db.session.query(ScenarioDesignDraftPost).filter_by(tmp_id="root").first()
        )
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
        from YSimulator.YServer.classes.models import Post as HpcPost

        from y_web.src.models import Exps

        hpc_session = _hpc_session_module().hpc_session

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
    from YSimulator.YServer.classes.models import Post as HpcPost

    from y_web.src.models import Exps

    get_adapter_for = _scenario_design_module(
        "modules.scenario_editor.backend.adapters.base"
    ).get_adapter_for
    hpc_session = _hpc_session_module().hpc_session
    models = _scenario_design_module("modules.scenario_editor.backend.models")
    ScenarioDesignIdMapping = models.ScenarioDesignIdMapping
    ScenarioDesignPublication = models.ScenarioDesignPublication
    ScenarioDesignScenario = models.ScenarioDesignScenario

    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, f"sd-fase7-exp-fault-{fail_after_step}")
    author_user_id, _topic_id = _seed_hpc_content(sd_app, exp_id)
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
        tmp_id="c1",
        parent_tmp_id="root",
        author_user_id=author_user_id,
        content="child",
    )

    with sd_app.app_context():
        from y_web.src.experiment.context import _activate_db_exp_bind

        _activate_db_exp_bind(exp_id)
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
        assert (
            db.session.query(ScenarioDesignPublication).count()
            == publication_count_before
        )
        assert db.session.query(ScenarioDesignIdMapping).count() == mapping_count_before


def test_hpc_fingerprint_mismatch_rejects_publish(sd_app, sd_client):
    from y_web.src.models import Exps

    client, admin_id = sd_client
    exp_id = _make_hpc_exp(sd_app, "sd-fase7-exp-fingerprint")
    author_user_id, _topic_id = _seed_hpc_content(sd_app, exp_id)
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

    # Simulate the base experiment changing after the scenario was opened
    # by inserting a new real Round into the HPC physical schema.
    import uuid

    from YSimulator.YServer.classes.models import Round as HpcRound

    hpc_session = _hpc_session_module().hpc_session

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
        client,
        exp_id,
        scenario_id,
        thread_id,
        tmp_id="root",
        parent_tmp_id=None,
        author_user_id=author_user_id,
        content="root",
    )

    key = "fase7-idem-key-1"
    body = {"published_experiment_name": "fase7-idem-published"}
    first = _publish(client, exp_id, scenario_id, idempotency_key=key, json_body=body)
    assert first.status_code == 201, first.data
    second = _publish(client, exp_id, scenario_id, idempotency_key=key, json_body=body)
    assert second.status_code == 200, second.data  # idempotent replay -> 200, not 201
    assert (
        first.get_json()["publication"]["id"] == second.get_json()["publication"]["id"]
    )
    assert first.get_json()["id_mapping"] == second.get_json()["id_mapping"]

    with sd_app.app_context():
        from YSimulator.YServer.classes.models import Post as HpcPost

        from y_web.src.models import Exps

        hpc_session = _hpc_session_module().hpc_session

        exp = db.session.get(Exps, exp_id)
        with hpc_session(exp) as hsession:
            assert hsession.query(HpcPost).count() == 1
