"""C7 (migration 0006) - the ``plugin_state`` table and its Alembic revision."""

import os

from sqlalchemy import inspect, text

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401

REV_0005 = "0005_rename_educatyon_to_frontend_adds_on"
REV_0006 = "0006_add_plugin_state_table"


def _tables(app):
    from y_web import db

    return set(inspect(db.engines["db_admin"]).get_table_names())


def _head_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    import y_web

    cfg = Config()
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(y_web.__file__), "alembic")
    )
    return ScriptDirectory.from_config(cfg).get_heads()


def test_alembic_has_a_single_head_and_0006_is_in_its_history():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    import y_web

    assert _head_revision() == ["0007_sync_legacy_dashboard_schema"]
    cfg = Config()
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(y_web.__file__), "alembic")
    )
    history = [r.revision for r in ScriptDirectory.from_config(cfg).walk_revisions()]
    assert REV_0006 in history and history.index(REV_0006) == 1


def test_startup_creates_plugin_state(core_app):
    with core_app.app_context():
        assert "plugin_state" in _tables(core_app)


def test_downgrade_then_upgrade_is_clean_and_idempotent(core_app):
    from flask_migrate import downgrade, upgrade

    from y_web import db

    with core_app.app_context():
        downgrade(directory=core_app.extensions["migrate"].directory, revision=REV_0005)
        assert "plugin_state" not in _tables(core_app)
        upgrade(directory=core_app.extensions["migrate"].directory)
        assert "plugin_state" in _tables(core_app)
        upgrade(directory=core_app.extensions["migrate"].directory)  # no-op
        cols = {
            c["name"]
            for c in inspect(db.engines["db_admin"]).get_columns("plugin_state")
        }
        assert cols == {"repo_key", "enabled", "updated_at", "updated_by"}


def test_upgrade_is_a_noop_when_create_all_already_built_the_table(core_app):
    """Fresh databases get the table from db.create_all(); 0006 must not fail there."""
    from flask_migrate import downgrade, upgrade

    from y_web import db

    with core_app.app_context():
        directory = core_app.extensions["migrate"].directory
        downgrade(directory=directory, revision=REV_0005)
        db.metadata.create_all(
            bind=db.engines["db_admin"],
            tables=[db.metadatas["db_admin"].tables["plugin_state"]],
        )
        upgrade(directory=directory)
        with db.engines["db_admin"].connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM plugin_state")).scalar() == 0


def test_missing_row_means_enabled_default_is_true(core_app):
    from y_web import db
    from y_web.src.models import PluginState

    with core_app.app_context():
        db.session.add(PluginState(repo_key="x_plugin"))
        db.session.commit()
        assert db.session.get(PluginState, "x_plugin").enabled is True
