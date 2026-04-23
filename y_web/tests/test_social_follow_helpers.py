from types import SimpleNamespace

import pytest

from y_web.src.data_access import users as users_module


pytestmark = pytest.mark.unit


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

    followers, followees, number_followers, number_followees = (
        users_module.get_user_friends("target-1", limit=10, page=1)
    )

    assert number_followers == 1
    assert number_followees == 2
    assert {item["id"] for item in followers} == {"target-3"}
    assert {item["id"] for item in followees} == {"actor-1", "actor-2"}
