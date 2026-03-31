"""Structural regression tests for the microblogging chat component."""

from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_microblog_chat_blueprint_prefix():
    from flask import Blueprint

    from y_web.routes.api import api_social

    assert isinstance(api_social, Blueprint)
    assert api_social.name == "api_social"
    assert api_social.url_prefix == "/api/social"


def test_microblog_chat_models_are_bound_to_experiment_db():
    from y_web.src.models import ForumChatMessage, ForumChatSession

    assert ForumChatSession.__bind_key__ == "db_exp"
    assert ForumChatSession.__tablename__ == "forum_chat_sessions"
    assert ForumChatMessage.__bind_key__ == "db_exp"
    assert ForumChatMessage.__tablename__ == "forum_chat_messages"


def test_microblog_chat_payload_helpers_include_expected_fields():
    from y_web.routes.api import social

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

    payload = social._social_chat_session_payload(session, include_messages=True)

    assert payload["id"] == 4
    assert payload["target_user_id"] == 12
    assert payload["target_username"] == "agent12"
    assert payload["messages"][0]["content"] == "Hello"


def test_microblog_chat_memory_query_uses_latest_message_and_recent_history():
    from y_web.routes.api import social

    session = SimpleNamespace(
        target_username="agent12",
        messages=[
            SimpleNamespace(id=1, role="user", content="we were talking about the education vote"),
            SimpleNamespace(id=2, role="assistant", content="yes, and your earlier post about schools"),
            SimpleNamespace(id=3, role="user", content="what about the mayor's statement?"),
        ],
    )

    query = social._social_chat_build_memory_query(
        session, "do you still support the mayor on this issue?"
    )

    assert "do you still support the mayor on this issue?" in query
    assert "what about the mayor's statement?" in query
    assert "education vote" in query


def test_microblog_chat_routes_are_exposed():
    from y_web.routes.api import social

    route_source = Path(social.__file__).read_text()

    assert '@api_social.get("/<int:exp_id>/chat/bootstrap")' in route_source
    assert '@api_social.post("/<int:exp_id>/chat/session")' in route_source
    assert '@api_social.get("/<int:exp_id>/chat/session/<int:session_id>")' in route_source
    assert '@api_social.post("/<int:exp_id>/chat/session/<int:session_id>/message")' in route_source
    assert "Microblogging chat is unavailable because memory is disabled." in route_source
    assert "You can chat only with followed agents." in route_source
    assert "_social_chat_followed_agent_ids" in route_source
    assert "_build_facts_snapshot" in route_source
    assert "_format_facts_pack" in route_source
    assert "FACTS CONTEXT" in route_source
    assert '"facts_snapshot_present"' in route_source
    assert "session.last_message_at =" in route_source
    assert "memory_query_text" in route_source


def test_microblog_chat_component_is_reusable_and_mounted():
    panel_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/chat_panel.html"
    ).read_text()
    feed_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/feed.html"
    ).read_text()
    thread_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/thread.html"
    ).read_text()
    profile_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text()
    friends_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/friends.html"
    ).read_text()
    hashtag_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/hashtag.html"
    ).read_text()
    interest_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/interest.html"
    ).read_text()
    emotions_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/emotions.html"
    ).read_text()

    assert 'id="microblog-chat-panel"' in panel_template
    assert 'id="microblog-chat-collapse-badge"' in panel_template
    assert 'id="microblog-chat-list"' in panel_template
    assert 'id="microblog-chat-compose"' in panel_template

    for template in (
        feed_template,
        thread_template,
        profile_template,
        friends_template,
        hashtag_template,
        interest_template,
        emotions_template,
    ):
        assert "{% if experiment_memory_enabled %}" in template
        assert '{% include "microblogging/components/chat_panel.html" %}' in template
        assert "assets/js/microblog-chat.js" in template


def test_microblog_chat_js_escapes_rendered_content():
    js_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/microblog-chat.js"
    ).read_text()

    assert "function escapeHtml" in js_source
    assert "function formatMessageHtml" in js_source
    assert "function renderCollapsedBadge" in js_source
    assert "function markSessionRead" in js_source
    assert "function isSessionUnread" in js_source
    assert "function getUnreadSessionCount" in js_source
    assert "microblog-chat-collapse-badge" in js_source
    assert "readStateKey" in js_source
    assert "replace(/^\\s+/, '')" in js_source
    assert "${escapeHtml(preview)}" in js_source
    assert "${formatMessageHtml(msg.content)}" in js_source
    assert "`/api/social/${expId}/chat/bootstrap`" in js_source
