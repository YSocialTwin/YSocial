from pathlib import Path


def test_follow_route_resolves_actor_from_logged_in_username():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/interactions/common.py"
    ).read_text(encoding="utf-8")

    assert "acting_user = User_mgmt.query.filter_by(" in source
    assert 'username=getattr(current_user, "username", "") or ""' in source
    assert "follower_id_converted = acting_user.id" in source
    assert "follower_id=follower_id_converted" in source
