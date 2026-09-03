from types import SimpleNamespace

import pytest

from y_web.routes.interactions import common as interactions_common
from y_web.src.data_access import users as users_module

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

def test_reduce_latest_follow_map_preserves_uuid_keys():
    events = [
        SimpleNamespace(
            user_id="actor-1",
            follower_id="target-1",
            action="follow",
        ),
        SimpleNamespace(
            user_id="actor-1",
            follower_id="target-1",
            action="unfollow",
        ),
        SimpleNamespace(
            user_id="actor-2",
            follower_id="target-2",
            action="follow",
        ),
    ]

    latest = users_module._reduce_latest_follow_map(
        events,
        source_attr="user_id",
        target_attr="follower_id",
    )

    assert latest[("actor-1", "target-1")][1] == "unfollow"
    assert latest[("actor-2", "target-2")][1] == "follow"


def test_count_follow_helpers_use_correct_direction_with_uuid_ids(monkeypatch):
    monkeypatch.setattr(
        users_module,
        "_active_follow_pairs",
        lambda: {
            ("target-1", "actor-1"),
            ("target-1", "actor-2"),
            ("target-3", "target-1"),
        },
    )

    assert users_module.count_followers("target-1") == 1
    assert users_module.count_followees("target-1") == 2


def test_get_user_friends_returns_uuid_followers_and_followees(monkeypatch):
    monkeypatch.setattr(
        users_module,
        "_active_follow_pairs",
        lambda: {
            ("target-1", "actor-1"),
            ("target-1", "actor-2"),
            ("target-3", "target-1"),
        },
    )
    monkeypatch.setattr(
        users_module,
        "_lookup_user_by_id",
        lambda user_id: SimpleNamespace(
            id=user_id,
            username=f"user-{user_id}",
            is_page=0,
        ),
    )
    monkeypatch.setattr(
        users_module,
        "Reactions",
        SimpleNamespace(
            query=SimpleNamespace(
                filter_by=lambda **kwargs: SimpleNamespace(count=lambda: 0)
            )
        ),
    )
    monkeypatch.setattr(
        users_module,
        "Agent",
        SimpleNamespace(
            query=SimpleNamespace(
                filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None)
            )
        ),
    )
    monkeypatch.setattr(
        users_module,
        "Admin_users",
        SimpleNamespace(
            query=SimpleNamespace(
                filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None)
            )
        ),
    )
    monkeypatch.setattr(
        users_module,
        "Page",
        SimpleNamespace(
            query=SimpleNamespace(
                filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None)
            )
        ),
    )
    monkeypatch.setattr(users_module, "select", lambda *a, **kw: _FakeSelect(*a))
    monkeypatch.setattr(users_module, "db", SimpleNamespace(session=_SelectRoutingSession()))

    followers, followees, number_followers, number_followees = (
        users_module.get_user_friends("target-1", limit=10, page=1)
    )

    assert number_followers == 1
    assert number_followees == 2
    assert {item["id"] for item in followers} == {"target-3"}
    assert {item["id"] for item in followees} == {"actor-1", "actor-2"}


def test_build_follow_payload_uses_uuid_for_hpc_experiments(monkeypatch):
    monkeypatch.setattr(interactions_common.uuid, "uuid4", lambda: "uuid-follow-id")

    payload = interactions_common._build_follow_payload(
        exp=SimpleNamespace(simulator_type="HPC"),
        source_user_id="source",
        target_user_id="target",
        action="follow",
        round_id="round-1",
    )

    assert payload == {
        "user_id": "source",
        "follower_id": "target",
        "action": "follow",
        "round": "round-1",
        "id": "uuid-follow-id",
    }


def test_build_follow_payload_keeps_non_hpc_ids_autogenerated():
    payload = interactions_common._build_follow_payload(
        exp=SimpleNamespace(simulator_type="forum"),
        source_user_id=1,
        target_user_id=2,
        action="follow",
        round_id=3,
    )

    assert payload == {
        "user_id": 1,
        "follower_id": 2,
        "action": "follow",
        "round": 3,
    }


def test_build_follow_payload_uses_uuid_for_photo_sharing_experiments(
    monkeypatch,
):
    monkeypatch.setattr(interactions_common.uuid, "uuid4", lambda: "photo-uuid")

    payload = interactions_common._build_follow_payload(
        exp=SimpleNamespace(simulator_type="Standard", platform_type="photo_sharing"),
        source_user_id="source",
        target_user_id="target",
        action="follow",
        round_id="round-1",
    )

    assert payload == {
        "user_id": "source",
        "follower_id": "target",
        "action": "follow",
        "round": "round-1",
        "id": "photo-uuid",
    }
