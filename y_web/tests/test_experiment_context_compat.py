import types

import pytest
from flask import g, request

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

    fake_db = types.SimpleNamespace(
        session=FakeSession(), get_engine=fake_get_engine, engines={}
    )

    monkeypatch.setattr(context, "db", fake_db)
    monkeypatch.setattr(
        "y_web.src.experiment.schema.ensure_experiment_schema_for_uri",
        lambda uri: None,
    )

    with app.app_context():
        original_db_exp = app.config["SQLALCHEMY_BINDS"]["db_exp"]
        fake_db.engines["db_exp"] = FakeEngine(original_db_exp)
        app.config["SQLALCHEMY_BINDS"]["db_exp_4"] = "sqlite:////tmp/exp_4.db"

        original_bind, original_engine, refreshed_engine = (
            context._activate_db_exp_bind(4)
        )

        assert original_bind == original_db_exp
        assert original_engine.url == original_db_exp
        # refreshed_engine is a REAL engine built by _activate_db_exp_bind()
        # via sqlalchemy.create_engine(...) (see that function's own
        # docstring for why: Flask-SQLAlchemy 3.x's db.get_engine() never
        # re-reads SQLALCHEMY_BINDS, so a fresh engine has to be built and
        # written into db.engines directly). Its .url is therefore a real
        # sqlalchemy.engine.URL object, which SQLAlchemy 2.x does not
        # compare equal to a plain string -- str() it first.
        assert str(refreshed_engine.url) == app.config["SQLALCHEMY_BINDS"]["db_exp"]
        assert fake_db.session.remove_calls == 1

        # refreshed_engine is a real sqlalchemy.engine.Engine (see above) --
        # it has no .disposed flag the way the old FakeEngine stand-in did,
        # so track the real .dispose() call instead of reading a
        # bookkeeping attribute that only ever existed on the mock.
        dispose_calls = {"count": 0}
        original_dispose = refreshed_engine.dispose

        def _tracking_dispose():
            dispose_calls["count"] += 1
            return original_dispose()

        monkeypatch.setattr(refreshed_engine, "dispose", _tracking_dispose)

        context._restore_db_exp_bind(original_bind, original_engine, refreshed_engine)

        assert app.config["SQLALCHEMY_BINDS"]["db_exp"] == original_db_exp
        assert dispose_calls["count"] == 1
        assert fake_db.session.remove_calls == 2


def test_setup_experiment_context_uses_get_engine_compat_path(app, monkeypatch):
    from y_web.src.experiment import context

    class FakeEngine:
        def __init__(self, url):
            self.url = url

        def dispose(self):
            pass

    class FakeSession:
        def remove(self):
            pass

    def fake_get_engine(bind=None):
        bind_key = bind or "db_exp"
        return FakeEngine(app.config["SQLALCHEMY_BINDS"][bind_key])

    fake_db = types.SimpleNamespace(
        session=FakeSession(), get_engine=fake_get_engine, engines={}
    )

    monkeypatch.setattr(context, "db", fake_db)
    monkeypatch.setattr(
        "y_web.src.experiment.schema.ensure_experiment_schema_for_uri",
        lambda uri: None,
    )

    with app.test_request_context("/admin/experiment_clients/4"):
        request.view_args = {"exp_id": 4}
        original_db_exp = app.config["SQLALCHEMY_BINDS"]["db_exp"]
        fake_db.engines["db_exp"] = FakeEngine(original_db_exp)
        app.config["SQLALCHEMY_BINDS"]["db_exp_4"] = "sqlite:////tmp/exp_4.db"

        context.setup_experiment_context()

        assert g.current_exp_id == 4
        assert g.current_db_bind == "db_exp_4"
        # Same real-engine/.url-is-a-URL-object situation as above --
        # g.current_db_exp_engine is built the same way by
        # setup_experiment_context() -> _activate_db_exp_bind().
        assert str(g.current_db_exp_engine.url) == "sqlite:////tmp/exp_4.db"
        assert g.original_db_exp_engine.url == original_db_exp

        context.teardown_experiment_context()
