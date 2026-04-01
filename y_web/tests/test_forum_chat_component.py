"""Structural regression tests for the forum chat component."""

from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_forum_chat_models_are_bound_to_experiment_db():
    from y_web.src.models import ForumChatMessage, ForumChatSession

    assert ForumChatSession.__bind_key__ == "db_exp"
    assert ForumChatSession.__tablename__ == "forum_chat_sessions"
    assert ForumChatMessage.__bind_key__ == "db_exp"
    assert ForumChatMessage.__tablename__ == "forum_chat_messages"


def test_forum_chat_schema_tables_registered():
    from y_web.src.experiment import schema

    assert "forum_chat_sessions" in schema._SQLITE_TABLES
    assert "forum_chat_messages" in schema._SQLITE_TABLES
    assert "forum_chat_sessions" in schema._POSTGRES_TABLES
    assert "forum_chat_messages" in schema._POSTGRES_TABLES


def test_forum_chat_payload_helpers_include_expected_fields():
    from y_web.routes.api import reddit

    message = SimpleNamespace(
        id=7,
        role="assistant",
        content="Hello",
        created_at=None,
    )
    session = SimpleNamespace(
        id=4,
        target_user_id=12,
        target_username="agent12",
        target_profile_pic="/avatar.png",
        last_message_preview="Hello",
        last_message_at=None,
        created_at=None,
        updated_at=None,
        run_id="run-1",
        messages=[message],
    )

    payload = reddit._forum_chat_session_payload(session, include_messages=True)

    assert payload["id"] == 4
    assert payload["target_user_id"] == 12
    assert payload["target_username"] == "agent12"
    assert payload["messages"][0]["content"] == "Hello"


def test_forum_chat_memory_query_uses_latest_message_and_recent_history():
    from y_web.routes.api import reddit

    session = SimpleNamespace(
        target_username="agent12",
        messages=[
            SimpleNamespace(
                id=1, role="user", content="we were talking about the library vote"
            ),
            SimpleNamespace(
                id=2, role="assistant", content="yes, and the censorship issue too"
            ),
            SimpleNamespace(
                id=3, role="user", content="what about the mayor's statement?"
            ),
        ],
    )

    query = reddit._forum_chat_build_memory_query(
        session, "do you still trust the mayor on this?"
    )

    assert "do you still trust the mayor on this?" in query
    assert "what about the mayor's statement?" in query
    assert "library vote" in query


def test_forum_chat_reply_strips_hashtags():
    from y_web.routes.api import reddit

    cleaned = reddit._strip_forum_chat_hashtags(
        "i still think #politics is messy, but #war coverage matters"
    )

    assert "#" not in cleaned
    assert "politics" in cleaned
    assert "war" in cleaned


def test_forum_chat_routes_are_exposed():
    from y_web.routes.api import reddit

    route_source = Path(reddit.__file__).read_text()

    assert '@api_reddit.get("/<int:exp_id>/chat/bootstrap")' in route_source
    assert '@api_reddit.post("/<int:exp_id>/chat/session")' in route_source
    assert (
        '@api_reddit.get("/<int:exp_id>/chat/session/<int:session_id>")' in route_source
    )
    assert (
        '@api_reddit.post("/<int:exp_id>/chat/session/<int:session_id>/message")'
        in route_source
    )
    assert "Forum chat is unavailable because memory is disabled." in route_source
    assert "You can chat only with followed agents." in route_source
    assert "_forum_chat_followed_agent_ids" in route_source
    assert "_build_facts_snapshot" in route_source
    assert "_format_facts_pack" in route_source
    assert "FACTS CONTEXT" in route_source
    assert "Do not use hashtags in your replies." in route_source
    assert '"facts_snapshot_present"' in route_source
    assert "session.last_message_at =" in route_source
    assert "memory_query_text" in route_source


def test_chat_component_is_reusable_and_mounted_on_feed_and_thread():
    panel_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/forum/components/chat_panel.html"
    ).read_text()
    feed_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/forum/feed.html"
    ).read_text()
    thread_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/forum/thread.html"
    ).read_text()
    profile_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/forum/profile.html"
    ).read_text()
    notifications_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/forum/notifications.html"
    ).read_text()

    assert 'id="forum-chat-panel"' in panel_template
    assert 'id="forum-chat-collapse-badge"' in panel_template
    assert 'id="forum-chat-list"' in panel_template
    assert 'id="forum-chat-compose"' in panel_template
    assert "{% if forum_memory_enabled %}" in feed_template
    assert "{% if forum_memory_enabled %}" in thread_template
    assert "{% if forum_memory_enabled %}" in profile_template
    assert "{% if forum_memory_enabled %}" in notifications_template
    assert '{% include "forum/components/chat_panel.html" %}' in feed_template
    assert '{% include "forum/components/chat_panel.html" %}' in thread_template
    assert '{% include "forum/components/chat_panel.html" %}' in profile_template
    assert '{% include "forum/components/chat_panel.html" %}' in notifications_template
    assert "assets/js/reddit/forum-chat.js" in feed_template
    assert "assets/js/reddit/forum-chat.js" in thread_template
    assert "assets/js/reddit/forum-chat.js" in profile_template
    assert "assets/js/reddit/forum-chat.js" in notifications_template
    assert "forum-profile-follow-btn" in profile_template
    assert (
        "/{{ exp_id }}/follow/{{ user['user_data']['id'] }}/{{ logged_id }}"
        in profile_template
    )


def test_forum_chat_js_escapes_rendered_content():
    js_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/reddit/forum-chat.js"
    ).read_text()

    assert "function escapeHtml" in js_source
    assert "function formatMessageHtml" in js_source
    assert "function renderCollapsedBadge" in js_source
    assert "function markSessionRead" in js_source
    assert "function isSessionUnread" in js_source
    assert "function getUnreadSessionCount" in js_source
    assert "forum-chat-collapse-badge" in js_source
    assert "readStateKey" in js_source
    assert "replace(/^\\s+/, '')" in js_source
    assert "${escapeHtml(preview)}" in js_source
    assert "${formatMessageHtml(msg.content)}" in js_source


def test_profile_route_uses_latest_follow_event_for_forum_state():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text()

    assert "def _latest_follow_action" in source
    assert "Follow.query.filter_by(follower_id=follower_id, user_id=user_id)" in source
    assert "_latest_follow_action(follower_id=logged_id, user_id=user.id)" in source


def test_forum_profile_posts_include_community_metadata_and_feed_type():
    posts_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/src/data_access/posts.py"
    ).read_text()
    common_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text()

    assert '"primary_community": primary_community' in posts_source
    assert '"display_time": display_time if is_forum else None' in posts_source
    assert (
        "article_preview = _resolve_article(article) if is_forum else None"
        in posts_source
    )
    assert "_primary_community_payload(article_preview, topics)" in posts_source
    assert (
        "rp = get_user_recent_posts(user_id, page, 10, mode, logged_id, exp_id)"
        in common_source
    )
    assert 'feed_type="new"' in common_source
