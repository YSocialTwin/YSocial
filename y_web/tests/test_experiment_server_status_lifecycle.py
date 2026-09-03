"""
Regression tests for experiment running and status synchronization.

Ensures that when an experiment server starts or stops:
1. exp.running and exp.exp_status are properly updated in server lifecycle helpers.
2. In-memory Exps instances and database rows remain synchronized.
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit



# ---------------------------------------------------------------------------
# SA2 test stubs — bypass select() ORM validation for unit-test stubs
# ---------------------------------------------------------------------------
class _FakeSelect:
    """Captures model/args without invoking SQLAlchemy ORM coercions."""
    def __init__(self, *models, **kw):
        self._models = models
        self._kw = {}
    def filter_by(self, **kw): self._kw = kw; return self
    def filter(self, *a): return self
    def select_from(self, m): return self
    def where(self, *a): return self
    def order_by(self, *a): return self
    def limit(self, n): return self

class _ScalarsResult:
    """Wraps a legacy query so .all()/.first() work uniformly."""
    def __init__(self, q): self._q = q
    def all(self):
        return self._q.all() if hasattr(self._q, 'all') else []
    def first(self):
        return self._q.first() if hasattr(self._q, 'first') else None
    def one_or_none(self):
        return self._q.one_or_none() if hasattr(self._q, 'one_or_none') else None
    def one(self):
        return self._q.one() if hasattr(self._q, 'one') else None

class _SelectRoutingSession:
    """Routes scalars(select(Model).filter_by(…)) → Model.query.filter_by(…)."""
    def __init__(self, inner=None): self._inner = inner
    def scalars(self, stmt):
        if isinstance(stmt, _FakeSelect) and stmt._models:
            model = stmt._models[0]
            q = getattr(model, 'query', None)
            if q is not None:
                if stmt._kw:
                    q = q.filter_by(**stmt._kw)
                return _ScalarsResult(q)
        return _ScalarsResult(
            type('_Empty', (), {'all': lambda s: [], 'first': lambda s: None,
                                'one_or_none': lambda s: None})()
        )
    def scalar(self, stmt): return None
    def __getattr__(self, name):
        if self._inner is not None:
            return getattr(self._inner, name)
        raise AttributeError(f'_SelectRoutingSession has no attribute {name!r}')

def test_start_experiment_updates_running_and_exp_status(monkeypatch):
    from y_web.routes.admin.sub.experiments import _crud as mod

    exp = SimpleNamespace(
        idexp=1,
        running=0,
        exp_status="stopped",
        is_remote=0,
    )

    started_servers = []
    committed = []

    class _FakeSession:
        def query(self, model):
            return self

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return exp

        def update(self, values):
            for k, v in values.items():
                setattr(exp, getattr(k, "key", str(k)), v)
            return 1

        def commit(self):
            committed.append(True)

    fake_session = _FakeSession()
    monkeypatch.setattr(mod, "check_privileges", lambda username: None)
    monkeypatch.setattr(mod, "current_user", SimpleNamespace(username="admin"))
    monkeypatch.setattr(
        mod, "_current_admin_user_or_none", lambda: SimpleNamespace(username="admin")
    )
    monkeypatch.setattr(mod, "user_can_view_experiment", lambda admin_user, exp: True)
    monkeypatch.setattr(
        mod, "_experiment_configuration_update_required", lambda exp: False
    )
    monkeypatch.setattr(
        mod,
        "start_server_for_experiment",
        lambda exp: started_servers.append(exp.idexp),
    )
    monkeypatch.setattr(mod, "experiment_details", lambda uid: f"details:{uid}")
    monkeypatch.setattr(mod, "select", lambda *a, **kw: _FakeSelect(*a))
    monkeypatch.setattr(mod, "db", SimpleNamespace(session=_SelectRoutingSession(fake_session)))
    monkeypatch.setattr(
        mod,
        "Exps",
        SimpleNamespace(query=fake_session, running="running", exp_status="exp_status"),
    )

    result = mod.start_experiment.__wrapped__(1)

    assert result == "details:1"
    assert exp.running == 1
    assert exp.exp_status == "active"
    assert started_servers == [1]
    assert len(committed) >= 1


def test_stop_experiment_updates_running_and_exp_status(monkeypatch):
    from y_web.routes.admin.sub.experiments import _crud as mod

    exp = SimpleNamespace(
        idexp=1,
        exp_name="TestExp",
        running=1,
        exp_status="active",
        simulator_type="Standard",
        is_remote=0,
    )

    stopped_servers = []
    committed = []

    class _FakeSession:
        def query(self, model):
            return self

        def filter_by(self, **kwargs):
            return self

        def all(self):
            return []

        def first(self):
            return exp

        def update(self, values):
            for k, v in values.items():
                setattr(exp, getattr(k, "key", str(k)), v)
            return 1

        def commit(self):
            committed.append(True)

    fake_session = _FakeSession()
    monkeypatch.setattr(mod, "check_privileges", lambda username: None)
    monkeypatch.setattr(mod, "current_user", SimpleNamespace(username="admin"))
    monkeypatch.setattr(
        mod, "_current_admin_user_or_none", lambda: SimpleNamespace(username="admin")
    )
    monkeypatch.setattr(mod, "user_can_manage_experiment", lambda admin_user, exp: True)
    monkeypatch.setattr(
        mod, "_experiment_configuration_update_required", lambda exp: False
    )
    monkeypatch.setattr(
        mod, "stop_server_for_experiment", lambda exp: stopped_servers.append(exp.idexp)
    )
    monkeypatch.setattr(mod, "experiment_details", lambda uid: f"details:{uid}")
    monkeypatch.setattr(mod, "select", lambda *a, **kw: _FakeSelect(*a))
    monkeypatch.setattr(mod, "db", SimpleNamespace(session=_SelectRoutingSession(fake_session)))
    monkeypatch.setattr(
        mod,
        "Exps",
        SimpleNamespace(query=fake_session, running="running", exp_status="exp_status"),
    )
    monkeypatch.setattr(mod, "Client", SimpleNamespace(query=fake_session))

    class _FakeScheduleQuery:
        def first(self):
            return None

    monkeypatch.setattr(
        mod, "ExperimentScheduleStatus", SimpleNamespace(query=_FakeScheduleQuery())
    )

    result = mod.stop_experiment.__wrapped__(1)

    assert result == "details:1"
    assert exp.running == 0
    assert exp.exp_status == "stopped"
    assert stopped_servers == [1]
