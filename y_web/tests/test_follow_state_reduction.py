import pytest
pytestmark = pytest.mark.unit

from types import SimpleNamespace


def test_reduce_latest_follow_map_prefers_latest_action():
    from y_web.src.data_access.users import _reduce_latest_follow_map

    events = [
        SimpleNamespace(id=1, user_id=10, follower_id=20, action="follow"),
        SimpleNamespace(id=2, user_id=10, follower_id=30, action="follow"),
        SimpleNamespace(id=3, user_id=10, follower_id=20, action="unfollow"),
        SimpleNamespace(id=4, user_id=10, follower_id=20, action="follow"),
    ]

    latest = _reduce_latest_follow_map(
        events, source_attr="user_id", target_attr="follower_id"
    )

    assert latest[(10, 20)] == (4, "follow")
    assert latest[(10, 30)] == (2, "follow")
