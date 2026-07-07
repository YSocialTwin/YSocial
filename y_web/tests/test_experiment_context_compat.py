import types

import pytest

pytestmark = pytest.mark.unit


def test_experiment_db_bind_refresh_works_without_db_engines(app, monkeypatch):
    from y_web.src.experiment import context

    class FakeEngine:
        def __init__(self, url):
            self.url = url
            self.disposed = False

        def dispose(self):
            self.disposed = True

    class FakeSession:
        def __init__(self):
            self.remove_calls = 0

        def remove(self):
            self.remove_calls += 1

    def fake_get_engine(bind=None):
        bind_key = bind or "db_exp"
        return FakeEngine(app.config["SQLALCHEMY_BINDS"][bind_key])

    fake_db = types.SimpleNamespace(session=FakeSession(), get_engine=fake_get_engine)

    monkeypatch.setattr(context, "db", fake_db)
    monkeypatch.setattr(
        "y_web.src.experiment.schema.ensure_experiment_schema_for_uri",
        lambda uri: None,
    )

    with app.app_context():
        original_db_exp = app.config["SQLALCHEMY_BINDS"]["db_exp"]
        app.config["SQLALCHEMY_BINDS"]["db_exp_4"] = "sqlite:////tmp/exp_4.db"

        original_bind, original_engine, refreshed_engine = context._activate_db_exp_bind(
            4
        )

        assert original_bind == original_db_exp
        assert original_engine.url == original_db_exp
        assert refreshed_engine.url == app.config["SQLALCHEMY_BINDS"]["db_exp"]
        assert fake_db.session.remove_calls == 1

        context._restore_db_exp_bind(original_bind, original_engine, refreshed_engine)

        assert app.config["SQLALCHEMY_BINDS"]["db_exp"] == original_db_exp
        assert refreshed_engine.disposed is True
        assert fake_db.session.remove_calls == 2
