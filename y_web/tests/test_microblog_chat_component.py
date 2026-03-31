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


def test_microblog_chat_reply_strips_hashtags():
    from y_web.routes.api import social

    cleaned = social._strip_social_chat_hashtags(
        "i still think #policy matters, but #schools are where it hits"
    )

    assert "#" not in cleaned
    assert "policy" in cleaned
    assert "schools" in cleaned


def test_microblog_chat_refresh_runtime_context_uses_semantic_memory(monkeypatch):
    from y_web.routes.api import social

    calls = {}

    monkeypatch.setattr(
        social,
        "_get_top_interests_for_user",
        lambda user_id: ["policy", "education"],
    )
    monkeypatch.setattr(
        social,
        "_build_persona_snapshot",
        lambda target_user, interests, exp: f"persona:{target_user.username}:{','.join(interests)}",
    )
    monkeypatch.setattr(
        social,
        "_detect_run_id_from_server_log",
        lambda exp, agent_user_id, probe_memory_coverage=True: {"run_id": "run-42"},
    )
    monkeypatch.setattr(
        social,
        "_ensure_experiment_server_db_binding",
        lambda exp: {"ok": True},
    )
    monkeypatch.setattr(social, "_memory_server_unavailable", lambda binding: False)

    def fake_build_memory_snapshot(exp, *, run_id, agent_user_id, memory_mode=None, query_text=None):
        calls["run_id"] = run_id
        calls["agent_user_id"] = agent_user_id
        calls["memory_mode"] = memory_mode
        calls["query_text"] = query_text
        return {"semantic_items": [{"text": "posted about schools"}]}

    monkeypatch.setattr(social, "_build_memory_snapshot", fake_build_memory_snapshot)

    session = SimpleNamespace(
        run_id="",
        persona_snapshot="",
        memory_snapshot_json="",
    )
    exp = SimpleNamespace(idexp=9)
    target_user = SimpleNamespace(id=12, username="agent12")

    snapshot = social._social_chat_refresh_runtime_context(
        exp=exp,
        target_user=target_user,
        session=session,
        query_text="schools and education",
    )

    assert session.run_id == "run-42"
    assert session.persona_snapshot == "persona:agent12:policy,education"
    assert calls["run_id"] == "run-42"
    assert calls["agent_user_id"] == 12
    assert calls["memory_mode"] == "semantic"
    assert calls["query_text"] == "schools and education"
    assert snapshot["semantic_items"][0]["text"] == "posted about schools"


def test_microblog_chat_generate_reply_injects_memory_facts_and_transcript(monkeypatch):
    from y_web.routes.api import social

    exp = SimpleNamespace(idexp=9)
    owner_user = SimpleNamespace(id=1, username="alice")
    target_user = SimpleNamespace(id=12, username="agent12")
    session = SimpleNamespace(
        run_id="run-42",
        persona_snapshot="Agent persona",
        llm_model="",
        llm_base_url="",
        target_username="agent12",
        messages=[
            SimpleNamespace(id=1, role="user", content="we talked about education"),
            SimpleNamespace(id=2, role="assistant", content="I posted about it before"),
        ],
    )

    monkeypatch.setattr(social, "_social_chat_admin_user", lambda exp: SimpleNamespace())
    monkeypatch.setattr(
        social,
        "_social_chat_refresh_runtime_context",
        lambda **kwargs: {"semantic_items": [{"text": "posted about education funding"}]},
    )
    monkeypatch.setattr(
        social,
        "_format_memory_pack",
        lambda snapshot, max_chars=2200: "MEMORY: posted about education funding",
    )
    monkeypatch.setattr(
        social,
        "_build_facts_snapshot",
        lambda **kwargs: {"top_posts": [{"post_id": 7, "text": "education funding matters"}]},
    )
    monkeypatch.setattr(
        social,
        "_format_facts_pack",
        lambda snapshot, max_chars=2200: "FACTS: post_id=7 education funding matters",
    )
    monkeypatch.setattr(
        social,
        "_resolve_llm_backend",
        lambda **kwargs: ("admin", "llama3.2", "http://127.0.0.1:11434/v1", "NULL", 0.7, 450),
    )

    llm_calls = {}

    def fake_generate_reply(**kwargs):
        llm_calls.update(kwargs)
        return "I remember posting about education funding."

    monkeypatch.setattr(social, "_generate_reply", fake_generate_reply)

    sanitize_calls = {}

    def fake_sanitize(reply, **kwargs):
        sanitize_calls["reply"] = reply
        sanitize_calls.update(kwargs)
        return reply, {"sanitized": False}

    monkeypatch.setattr(social, "_sanitize_interview_reply", fake_sanitize)

    reply, meta = social._social_chat_generate_reply(
        exp=exp,
        target_user=target_user,
        owner_user=owner_user,
        session=session,
        user_message="what have you posted about education?",
    )

    assert reply == "I remember posting about education funding."
    assert "MEMORY CONTEXT" in llm_calls["system_message"]
    assert "FACTS CONTEXT" in llm_calls["system_message"]
    assert "Do not use hashtags in your replies." in llm_calls["system_message"]
    assert "RECENT CHAT" in llm_calls["user_message"]
    assert "alice: what have you posted about education?" in llm_calls["user_message"]
    assert sanitize_calls["strict_no_inference"] is False
    assert meta["memory_snapshot_present"] is True
    assert meta["facts_snapshot_present"] is True


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
