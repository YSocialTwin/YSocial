"""
Tests for the EducatYon frontend plugin suite integration.

Covers:
  * manifest discovery/validation (y_web.src.external_runtime.frontend_plugins)
  * suite/blueprint registration + static asset serving (plugin_loader)
  * the JIT per-experiment schema migration (external/EducatYon/.../migrations.py)
  * the "zero impact when not enabled" guarantee for active_modules_context()
  * the minimal post_annotation API end-to-end (enable -> create -> list)

These tests exercise the REAL external/EducatYon repo scaffolded alongside
this change (not a mock), since discovery/validation intentionally reads
manifests live from disk rather than from a cache.
"""
import json
import os
import sqlite3
import tempfile

import pytest
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.src.external_runtime import frontend_plugins
from y_web.src.external_runtime import plugin_loader


# ---------------------------------------------------------------------------
# Manifest discovery / validation
# ---------------------------------------------------------------------------
def test_discover_frontend_modules_finds_post_annotation():
    modules = frontend_plugins.discover_frontend_modules("educatyon")
    module_ids = [m.get("module_id") for m in modules]
    assert "post_annotation" in module_ids


def test_validate_frontend_suite_valid_for_educatyon():
    report = frontend_plugins.validate_frontend_suite("educatyon")
    assert report["installed"] is True
    assert report["valid"] is True, report["errors"]
    assert report["suite"]["suite_id"] == "educatyon"
    module_ids = [m["module_id"] for m in report["modules"]]
    assert "post_annotation" in module_ids
    post_annotation = next(m for m in report["modules"] if m["module_id"] == "post_annotation")
    assert post_annotation["valid"] is True, post_annotation["errors"]


def test_validate_frontend_suite_unknown_repo_key():
    report = frontend_plugins.validate_frontend_suite("not_a_real_repo_key")
    assert report["installed"] is False
    assert report["valid"] is False
    assert report["errors"]


def test_frontend_plugin_repo_keys_includes_educatyon():
    assert "educatyon" in frontend_plugins.frontend_plugin_repo_keys()


# ---------------------------------------------------------------------------
# JIT migration (module's own schema, applied to one experiment DB)
# ---------------------------------------------------------------------------
def test_post_annotation_migration_creates_tables():
    module = plugin_loader._import_from_suite("educatyon", "modules.post_annotation.backend.migrations")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        # Start from an empty-but-valid sqlite file (as a real experiment DB would be).
        sqlite3.connect(db_path).close()

        assert module.migrate_sqlite_server(db_path, quiet=True) is True

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "plugin_educatyon_post_annotation" in tables
        assert "plugin_educatyon_post_annotation_topic" in tables

        # Idempotent: calling it again must not error or duplicate anything.
        assert module.migrate_sqlite_server(db_path, quiet=True) is True
    finally:
        os.unlink(db_path)


def test_ensure_module_schema_targets_the_right_experiment_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        sqlite3.connect(db_path).close()
        monkeypatch.setattr(plugin_loader, "_experiment_db_path", lambda exp_id: db_path)

        assert plugin_loader.ensure_module_schema("educatyon", "post_annotation", exp_id=999, quiet=True) is True

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "plugin_educatyon_post_annotation" in tables
    finally:
        os.unlink(db_path)


def test_ensure_module_schema_unknown_module_returns_false():
    assert plugin_loader.ensure_module_schema("educatyon", "does_not_exist", exp_id=1) is False


# ---------------------------------------------------------------------------
# Blueprint / static asset registration
# ---------------------------------------------------------------------------
def test_register_frontend_plugin_suites_registers_blueprint_and_static_route(app):
    report = plugin_loader.register_frontend_plugin_suites(app)
    assert report["suites"]["educatyon"]["installed"] is True
    assert report["suites"]["educatyon"]["valid"] is True
    assert "post_annotation" in report["suites"]["educatyon"]["registered_modules"]
    assert plugin_loader.is_module_available("educatyon", "post_annotation") is True

    assert "educatyon_post_annotation" in app.blueprints
    assert "educatyon_static_educatyon" in app.blueprints

    client = app.test_client()
    resp = client.get("/plugins/educatyon/post_annotation/static/modules/post_annotation/frontend/plugin.js")
    assert resp.status_code == 200
    assert b"EducatYon" in resp.data

    # Path traversal must be refused, not silently served.
    resp2 = client.get("/plugins/educatyon/post_annotation/static/../../../../etc/passwd")
    assert resp2.status_code == 404

    # An unknown module_id under a valid suite must 404, not serve anything.
    resp3 = client.get("/plugins/educatyon/does_not_exist/static/modules/post_annotation/frontend/plugin.js")
    assert resp3.status_code == 404


# ---------------------------------------------------------------------------
# active_modules_context(): the "zero impact unless enabled" choke point
# ---------------------------------------------------------------------------
def _make_exp(app):
    from y_web.src.models import Exps

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            exp_name="edu-test-exp",
            db_name="experiments/edu-test/database_server.db",
            owner="admin",
            exp_descr="test",
            status=1,
            running=0,
            port=5000,
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


def test_active_modules_context_empty_without_registered_suite(app):
    # Fresh module-level state: nothing registered yet in this process for
    # a throwaway repo key that will never validate.
    plugin_loader._REGISTERED_SUITES.clear()
    with app.app_context():
        assert plugin_loader.active_modules_context(exp_id=1) == []


def test_active_modules_context_empty_when_module_not_enabled(app):
    plugin_loader.register_frontend_plugin_suites(app)
    with app.app_context():
        exp_id = _make_exp(app)
        assert plugin_loader.active_modules_context(exp_id) == []


def test_active_modules_context_returns_module_when_enabled(app):
    plugin_loader.register_frontend_plugin_suites(app)
    from y_web.src.models import EducatyonExpModuleSettings

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id,
            module_id="post_annotation",
            enabled=True,
            config_json=json.dumps({"opinion_scale": "binary"}),
        ))
        db.session.commit()

        modules = plugin_loader.active_modules_context(exp_id)
        assert len(modules) == 1
        assert modules[0]["module_id"] == "post_annotation"
        assert modules[0]["api_base"] == f"/{exp_id}/api/plugins/educatyon/post_annotation"
        assert modules[0]["frontend_entry"].endswith("modules/post_annotation/frontend/plugin.js")
        assert modules[0]["config"]["opinion_scale"] == "binary"
        # Untouched parameters still carry their manifest default.
        assert modules[0]["config"]["annotate_posts"] is True


# ---------------------------------------------------------------------------
# End-to-end API flow: enable -> create annotation -> list it back
# ---------------------------------------------------------------------------
@pytest.fixture
def educatyon_app(app):
    """The shared `app` fixture, with the post_annotation blueprint registered.

    Registering the suite imports the module's model classes for the first
    time in this process, so we re-run create_all() afterwards to create
    their tables in the fixture's temp db_exp file — create_all() is
    additive/idempotent, so this never touches the tables already created
    by the base `app` fixture.
    """
    plugin_loader.register_frontend_plugin_suites(app)
    with app.app_context():
        try:
            db.create_all(bind_key="__all__")
        except TypeError:
            db.create_all()
    return app


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_post_annotation_api_end_to_end(educatyon_app):
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True, config_json="{}",
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    # Not enabled for a *different* experiment -> 404, never a silent 200.
    resp_disabled = client.get(f"/999999/api/plugins/educatyon/post_annotation/topics")
    assert resp_disabled.status_code == 404

    # Create an annotation on the enabled experiment.
    create_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": 42,
            "topics": [{"label": "Climate change", "opinion": 1.0}],
        },
    )
    assert create_resp.status_code == 200, create_resp.data
    payload = create_resp.get_json()
    assert payload["ok"] is True
    annotation_id = payload["annotation_id"]
    assert annotation_id

    list_resp = client.get(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        query_string={"target_type": "post", "target_id": 42},
    )
    assert list_resp.status_code == 200
    listed = list_resp.get_json()
    assert listed["ok"] is True
    assert listed["count"] == 1
    assert listed["annotations"][0]["topics"][0]["label"] == "Climate change"
    assert listed["annotations"][0]["topics"][0]["opinion_value"] == 1.0


def test_post_annotation_rejects_disabled_target_type(educatyon_app):
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id,
            module_id="post_annotation",
            enabled=True,
            config_json=json.dumps({"annotate_comments": False}),
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={"target_type": "comment", "target_id": 1, "topics": [{"label": "x", "opinion": 0}]},
    )
    assert resp.status_code == 403



def test_post_annotation_accepts_uuid_target_id_hpc_style(educatyon_app):
    """HPC-simulator experiments identify posts/comments by UUID, not by a
    numeric Post id (Standard-simulator experiments use numeric ids). The
    module must accept either without ever coercing target_id to int.
    """
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    uuid_target_id = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True, config_json="{}",
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    create_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": uuid_target_id,
            "topics": [{"label": "Climate change", "opinion": 1.0}],
        },
    )
    assert create_resp.status_code == 200, create_resp.data
    assert create_resp.get_json()["ok"] is True

    list_resp = client.get(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        query_string={"target_type": "post", "target_id": uuid_target_id},
    )
    assert list_resp.status_code == 200
    listed = list_resp.get_json()
    assert listed["ok"] is True
    assert listed["count"] == 1


def test_post_annotation_create_upserts_instead_of_duplicating(educatyon_app):
    """A user may hold at most one annotation per target: annotating the
    same post twice must edit the existing row (and its topics) in place,
    never insert a second one. Verified directly against the DB row count,
    not just through the API's own responses.
    """
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True, config_json="{}",
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    first_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": 77,
            "topics": [{"label": "Climate change", "opinion": 1.0}],
        },
    )
    assert first_resp.status_code == 200, first_resp.data
    first_payload = first_resp.get_json()
    assert first_payload["ok"] is True
    assert first_payload["updated"] is False
    first_annotation_id = first_payload["annotation_id"]

    # Re-annotate the SAME target with a different topic selection.
    second_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": 77,
            "topics": [{"label": "Vaccines", "opinion": -1.0}],
        },
    )
    assert second_resp.status_code == 200, second_resp.data
    second_payload = second_resp.get_json()
    assert second_payload["ok"] is True
    assert second_payload["updated"] is True
    assert second_payload["annotation_id"] == first_annotation_id

    with app.app_context():
        backend_module = plugin_loader._import_from_suite(
            "educatyon", "modules.post_annotation.backend"
        )
        PluginEducatyonPostAnnotation = backend_module.PluginEducatyonPostAnnotation
        PluginEducatyonPostAnnotationTopic = backend_module.PluginEducatyonPostAnnotationTopic

        rows = PluginEducatyonPostAnnotation.query.filter_by(
            target_type="post", target_id="77",
        ).all()
        assert len(rows) == 1, "annotating the same target twice must not duplicate the row"
        topics = PluginEducatyonPostAnnotationTopic.query.filter_by(
            annotation_id=rows[0].id
        ).all()
        assert [t.topic_label for t in topics] == ["Vaccines"], (
            "the old topic set must be replaced, not appended to"
        )

    # The list endpoint agrees: still exactly one annotation for this target.
    list_resp = client.get(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        query_string={"target_type": "post", "target_id": 77},
    )
    listed = list_resp.get_json()
    assert listed["count"] == 1
    assert listed["annotations"][0]["topics"][0]["label"] == "Vaccines"


def test_my_annotations_hydrates_existing_annotation(educatyon_app):
    """/my_annotations is the batched lookup the frontend calls on every
    fresh page load to know which targets the current user already
    annotated — this is what makes an annotation survive a page refresh
    (the client never trusts anything left over in the DOM/JS state; it
    always re-asks this endpoint). A target the user never annotated must
    simply be absent from the response, not present with an empty shell.
    """
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True, config_json="{}",
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    create_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": 101,
            "topics": [{"label": "Climate change", "opinion": 2.0}],
        },
    )
    assert create_resp.status_code == 200, create_resp.data

    # Simulate a fresh page load asking, in one batched call, about several
    # posts on the page — only one of which was ever annotated.
    hydrate_resp = client.get(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/my_annotations",
        query_string={"target_type": "post", "target_ids": "101,202,303"},
    )
    assert hydrate_resp.status_code == 200
    hydrated = hydrate_resp.get_json()
    assert hydrated["ok"] is True
    assert set(hydrated["annotations"].keys()) == {"101"}
    assert hydrated["annotations"]["101"]["topics"][0]["label"] == "Climate change"
    assert hydrated["annotations"]["101"]["topics"][0]["opinion_value"] == 2.0

    # Missing/required params are rejected cleanly, never a silent empty 200.
    bad_resp = client.get(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/my_annotations",
        query_string={"target_type": "post"},
    )
    assert bad_resp.status_code == 400


def test_migration_dedupes_pre_existing_duplicates_before_unique_index():
    """A database whose module was enabled before the "one annotation per
    user per target" rule existed may already hold duplicate rows for the
    same (target_type, target_id, annotator_user_id). The migration must
    collapse those down to one (keeping the most recent) — and drop their
    now-orphaned topic rows — before it can safely add the unique index
    that enforces the rule going forward.
    """
    module = plugin_loader._import_from_suite("educatyon", "modules.post_annotation.backend.migrations")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Simulate the OLD schema (no updated_at, no unique index) already
        # holding a pre-existing duplicate for the same user/target.
        cursor.execute(
            """
            CREATE TABLE plugin_educatyon_post_annotation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                annotator_user_id TEXT NOT NULL,
                annotator_username TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE plugin_educatyon_post_annotation_topic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                annotation_id INTEGER NOT NULL REFERENCES plugin_educatyon_post_annotation(id),
                topic_label TEXT NOT NULL,
                topic_id INTEGER,
                opinion_scale TEXT NOT NULL,
                opinion_value REAL NOT NULL
            )
            """
        )
        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation (id, target_type, target_id, annotator_user_id) "
            "VALUES (1, 'post', '42', 'user-1')"
        )
        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation (id, target_type, target_id, annotator_user_id) "
            "VALUES (2, 'post', '42', 'user-1')"
        )
        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation_topic "
            "(annotation_id, topic_label, opinion_scale, opinion_value) VALUES (1, 'Old topic', '5point', 0)"
        )
        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation_topic "
            "(annotation_id, topic_label, opinion_scale, opinion_value) VALUES (2, 'New topic', '5point', 1)"
        )
        conn.commit()
        conn.close()

        assert module.migrate_sqlite_server(db_path, quiet=True) is True

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(plugin_educatyon_post_annotation)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "updated_at" in columns

        cursor.execute(
            "SELECT id FROM plugin_educatyon_post_annotation "
            "WHERE target_type='post' AND target_id='42' AND annotator_user_id='user-1'"
        )
        remaining_ids = [row[0] for row in cursor.fetchall()]
        assert remaining_ids == [2], "the dedupe pass must keep the most recent row, not both"

        cursor.execute("SELECT topic_label FROM plugin_educatyon_post_annotation_topic")
        remaining_topics = [row[0] for row in cursor.fetchall()]
        assert remaining_topics == ["New topic"], (
            "orphaned topic rows belonging to the deleted duplicate must be removed too"
        )

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        assert "uq_plugin_educatyon_post_annotation_target_user" in indexes

        # A different user annotating the same target is untouched by the
        # dedupe pass (it only ever collapses rows sharing the full triple).
        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation (target_type, target_id, annotator_user_id) "
            "VALUES ('post', '42', 'user-2')"
        )
        conn.commit()
        conn.close()

        # Idempotent, and the real unique index now rejects an actual duplicate.
        assert module.migrate_sqlite_server(db_path, quiet=True) is True

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO plugin_educatyon_post_annotation (target_type, target_id, annotator_user_id) "
                "VALUES ('post', '42', 'user-1')"
            )
        conn.close()
    finally:
        os.unlink(db_path)


def test_post_annotation_all_four_dimensions_round_trip(educatyon_app):
    """With every dimension enabled, a single annotation can carry a topic
    (with its opinion), an overall sentiment, one or more elicited
    emotions, and a perceived-toxicity value all at once — and every field
    comes back correctly from the POST response itself, from GET
    .../annotations, and from GET .../my_annotations (the hydration
    endpoint), all three using the same serialization.
    """
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True,
            config_json=json.dumps({
                "enable_topic_annotation": True,
                "enable_opinion_annotation": True,
                "enable_sentiment_annotation": True,
                "enable_emotion_annotation": True,
                "enable_toxicity_annotation": True,
            }),
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    create_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": 55,
            "topics": [{"label": "Climate change", "opinion": 1.0}],
            "sentiment": -1.0,
            "emotions": ["Joy", "Trust"],
            "toxicity": 2.0,
        },
    )
    assert create_resp.status_code == 200, create_resp.data
    created = create_resp.get_json()["annotation"]
    assert created["topics"][0]["label"] == "Climate change"
    assert created["topics"][0]["opinion_value"] == 1.0
    assert created["sentiment"] == {"scale": "3point", "value": -1.0}
    assert sorted(created["emotions"]) == ["Joy", "Trust"]
    assert created["toxicity"] == {"scale": "3point", "value": 2.0}

    list_resp = client.get(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        query_string={"target_type": "post", "target_id": 55},
    )
    listed = list_resp.get_json()["annotations"][0]
    assert listed["sentiment"]["value"] == -1.0
    assert listed["toxicity"]["value"] == 2.0
    assert sorted(listed["emotions"]) == ["Joy", "Trust"]

    hydrate_resp = client.get(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/my_annotations",
        query_string={"target_type": "post", "target_ids": "55"},
    )
    hydrated = hydrate_resp.get_json()["annotations"]["55"]
    assert hydrated["sentiment"]["value"] == -1.0
    assert hydrated["toxicity"]["value"] == 2.0
    assert sorted(hydrated["emotions"]) == ["Joy", "Trust"]
    assert hydrated["topics"][0]["opinion_value"] == 1.0


def test_post_annotation_topic_without_opinion_when_disabled(educatyon_app):
    """When the "opinion" sub-dimension is disabled, tagging a topic must
    store the topic label with no opinion value/scale at all — not a
    zero or a default, an actual NULL — even if the client sends one
    anyway (a stale/misconfigured client should never leak that data in).
    """
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True,
            config_json=json.dumps({
                "enable_topic_annotation": True,
                "enable_opinion_annotation": False,
            }),
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    create_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": 66,
            # A client that still sends an opinion despite the dimension
            # being disabled must be ignored, not stored.
            "topics": [{"label": "Vaccines", "opinion": 1.0}],
        },
    )
    assert create_resp.status_code == 200, create_resp.data
    topic = create_resp.get_json()["annotation"]["topics"][0]
    assert topic["label"] == "Vaccines"
    assert topic["opinion_value"] is None
    assert topic["opinion_scale"] is None


def test_post_annotation_disabled_dimensions_are_ignored_not_stored(educatyon_app):
    """A payload carrying sentiment/emotions/toxicity for an experiment
    that never enabled those dimensions must have them silently dropped —
    the module keeps its "zero impact unless enabled" guarantee at the
    data layer, not just at the config-UI layer.
    """
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True, config_json="{}",
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    create_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": 71,
            "topics": [{"label": "Climate change", "opinion": 1.0}],
            "sentiment": -1.0,
            "emotions": ["Joy"],
            "toxicity": 2.0,
        },
    )
    assert create_resp.status_code == 200, create_resp.data
    annotation = create_resp.get_json()["annotation"]
    assert annotation["sentiment"] is None
    assert annotation["emotions"] == []
    assert annotation["toxicity"] is None
    assert annotation["topics"][0]["label"] == "Climate change"


def test_post_annotation_rejects_empty_content(educatyon_app):
    """An annotation must have content in at least one enabled dimension —
    a payload with nothing usable (e.g. topics enabled but none selected,
    and no other dimension enabled) is rejected rather than silently
    stored as an empty row.
    """
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True, config_json="{}",
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={"target_type": "post", "target_id": 88, "topics": []},
    )
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_post_annotation_sentiment_only_annotation_needs_no_topic(educatyon_app):
    """When sentiment annotation is enabled (topic annotation disabled),
    a sentiment-only submission is valid on its own — the "at least one
    dimension" rule is about the whole annotation, not specifically topics.
    """
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True,
            config_json=json.dumps({
                "enable_topic_annotation": False,
                "enable_sentiment_annotation": True,
            }),
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={"target_type": "post", "target_id": 99, "sentiment": 1.0},
    )
    assert resp.status_code == 200, resp.data
    annotation = resp.get_json()["annotation"]
    assert annotation["sentiment"] == {"scale": "3point", "value": 1.0}
    assert annotation["topics"] == []


def test_migration_adds_new_dimension_columns_and_relaxes_topic_nullability():
    """A database whose module was enabled before sentiment/emotions/
    toxicity existed (and before topics could be tagged without an
    opinion) must be upgradeable in place: new columns/table appear, and
    the topic table's opinion columns become nullable so a topic can be
    inserted without one — all without touching pre-existing data.
    """
    module = plugin_loader._import_from_suite("educatyon", "modules.post_annotation.backend.migrations")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # The OLDEST schema shape: no updated_at, no sentiment/toxicity
        # columns, and opinion_scale/opinion_value declared NOT NULL.
        cursor.execute(
            """
            CREATE TABLE plugin_educatyon_post_annotation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                annotator_user_id TEXT NOT NULL,
                annotator_username TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE plugin_educatyon_post_annotation_topic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                annotation_id INTEGER NOT NULL REFERENCES plugin_educatyon_post_annotation(id),
                topic_label TEXT NOT NULL,
                topic_id INTEGER,
                opinion_scale TEXT NOT NULL,
                opinion_value REAL NOT NULL
            )
            """
        )
        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation (id, target_type, target_id, annotator_user_id) "
            "VALUES (1, 'post', '9', 'user-1')"
        )
        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation_topic "
            "(annotation_id, topic_label, opinion_scale, opinion_value) VALUES (1, 'Old topic', '5point', 1.0)"
        )
        conn.commit()
        conn.close()

        assert module.migrate_sqlite_server(db_path, quiet=True) is True

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(plugin_educatyon_post_annotation)")
        columns = {row[1] for row in cursor.fetchall()}
        assert {"updated_at", "sentiment_scale", "sentiment_value", "toxicity_scale", "toxicity_value"} <= columns

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "plugin_educatyon_post_annotation_emotion" in tables

        # Pre-existing topic row must have survived the table rebuild intact.
        cursor.execute("SELECT topic_label, opinion_value FROM plugin_educatyon_post_annotation_topic WHERE id = 1")
        row = cursor.fetchone()
        assert row == ("Old topic", 1.0)

        # The opinion columns are now nullable: inserting a topic with no
        # opinion (the "opinion" dimension disabled case) must succeed,
        # where it would have violated NOT NULL before the rebuild.
        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation_topic (annotation_id, topic_label) VALUES (1, 'No-opinion topic')"
        )
        conn.commit()

        cursor.execute(
            "INSERT INTO plugin_educatyon_post_annotation_emotion (annotation_id, emotion_label) VALUES (1, 'Joy')"
        )
        conn.commit()
        conn.close()

        # Idempotent: a second pass over an already-upgraded database
        # must not error and must not re-rebuild the topic table.
        assert module.migrate_sqlite_server(db_path, quiet=True) is True
    finally:
        os.unlink(db_path)
