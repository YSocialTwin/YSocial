"""The chats with agents, the interview and the URL summary follow the experiment's prompt language."""

import pytest

from y_web import prompt_store
from y_web.routes.api.interview._llm import _sanitize_interview_reply
from y_web.src.system import prompt_packs

pytestmark = pytest.mark.unit

FACTS = {"query_hits": [], "top_posts": []}


def test_english_chat_prompts_are_unchanged():
    assert (
        prompt_store.get("social__social_chat_generate_reply__5")
        == "I do not have much to add right now."
    )
    system = prompt_store.prompt(
        "reddit__forum_chat_generate_reply__1", username="bob", persona="Name: Bob"
    )
    assert system.startswith(
        "You are @bob, a participant in a forum simulation. You are having a private"
    )
    assert system.endswith("\n\nPERSONA\nName: Bob")


@pytest.mark.parametrize("language", ["en", "it"])
def test_sanitizer_follows_the_language(language):
    reply, meta = _sanitize_interview_reply(
        "post_id=999",
        facts_snapshot=FACTS,
        memory_snapshot={},
        strict_no_inference=False,
        language=language,
    )
    assert meta["reason"] == "unknown_ids"
    assert reply == prompt_store.get(
        "_llm__sanitize_interview_reply__1", language=language
    )


def test_italian_claim_phrases_trigger_the_strict_guard():
    reply, meta = _sanitize_interview_reply(
        "Ho commentato quel post ieri.",
        facts_snapshot=FACTS,
        memory_snapshot={},
        strict_no_inference=True,
        language="it",
    )
    assert meta["reason"] == "strict_no_inference_without_ids"
    assert reply.startswith("Non riesco a confermarlo")


def test_experiment_language_defaults_to_english_when_unknown():
    assert prompt_packs.experiment_language(None) == "en"
    assert prompt_packs.experiment_language("not-a-number") == "en"
