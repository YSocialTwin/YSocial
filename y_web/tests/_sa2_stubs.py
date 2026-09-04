"""
Shared SA2 compatibility stubs for unit tests.

These stubs allow test doubles (SimpleNamespace, MagicMock) to be used in
place of real SQLAlchemy ORM models when the production code under test calls
the SA2 ``db.session.scalars(select(Model).filter_by(...))`` pattern.

Usage in a test::

    from y_web.tests._sa2_stubs import _FakeSelect, _ScalarsResult, _SelectRoutingSession

    monkeypatch.setattr(mod, "select", lambda *a, **kw: _FakeSelect(*a))
    monkeypatch.setattr(mod, "db", SimpleNamespace(session=_SelectRoutingSession()))

Migration note
--------------
These stubs are a **migration aid** and should be removed once every test that
uses them has been rewritten to mock ``db.session.scalars`` directly:

    mock_session.scalars.return_value.first.return_value = my_obj

Tracked in: C4 (SA2 migration — https://github.com/YSocialTwin/YSocial)
"""


class _FakeSelect:
    """Captures model/args without invoking SQLAlchemy ORM coercions."""

    def __init__(self, *models, **kw):
        self._models = models
        self._kw = {}

    def filter_by(self, **kw):
        self._kw = kw
        return self

    def filter(self, *a):
        return self

    def select_from(self, m):
        return self

    def where(self, *a):
        return self

    def order_by(self, *a):
        return self

    def limit(self, n):
        return self


class _ScalarsResult:
    """Wraps a legacy query so .all()/.first() work uniformly."""

    def __init__(self, q):
        self._q = q

    def all(self):
        return self._q.all() if hasattr(self._q, "all") else []

    def first(self):
        return self._q.first() if hasattr(self._q, "first") else None

    def one_or_none(self):
        return self._q.one_or_none() if hasattr(self._q, "one_or_none") else None

    def one(self):
        return self._q.one() if hasattr(self._q, "one") else None


class _SelectRoutingSession:
    """Routes scalars(select(Model).filter_by(…)) → Model.query.filter_by(…).

    Pass an optional *inner* session to fall back to for attributes not
    handled here (e.g. ``db.session.query``, ``db.session.commit``).
    """

    def __init__(self, inner=None):
        self._inner = inner

    def scalars(self, stmt):
        if isinstance(stmt, _FakeSelect) and stmt._models:
            model = stmt._models[0]
            q = getattr(model, "query", None)
            if q is not None:
                if stmt._kw:
                    q = q.filter_by(**stmt._kw)
                return _ScalarsResult(q)
        return _ScalarsResult(
            type(
                "_Empty",
                (),
                {
                    "all": lambda s: [],
                    "first": lambda s: None,
                    "one_or_none": lambda s: None,
                },
            )()
        )

    def scalar(self, stmt):
        return None

    def __getattr__(self, name):
        if self._inner is not None:
            return getattr(self._inner, name)
        raise AttributeError(f"_SelectRoutingSession has no attribute {name!r}")
