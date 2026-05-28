from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_assistant_agent_transcript_shape(monkeypatch):
    from y_web.src.llm import autogen_compat

    monkeypatch.setattr(
        autogen_compat,
        "_invoke_text_model",
        lambda **kwargs: "generated reply",
    )

    peer = autogen_compat.AssistantAgent(
        name="peer",
        llm_config={},
        system_message="peer system",
        max_consecutive_auto_reply=1,
    )
    user = autogen_compat.AssistantAgent(name="user", max_consecutive_auto_reply=0)

    user.initiate_chat(peer, message="hello", silent=True)

    assert user.chat_messages[peer][0]["content"] == "generated reply"
    assert peer.chat_messages[user][0]["content"] == "generated reply"


def test_multimodal_agent_returns_text_chunks(monkeypatch):
    from y_web.src.llm import autogen_compat

    monkeypatch.setattr(
        autogen_compat,
        "_invoke_vision_model",
        lambda **kwargs: "vision reply",
    )

    agent = autogen_compat.MultimodalConversableAgent(
        name="vision",
        llm_config={},
        system_message="vision system",
    )

    result = agent._generate_reply("Describe <img http://example.test/image.png>")

    assert result == [{"text": "vision reply"}]
