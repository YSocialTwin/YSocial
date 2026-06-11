import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.external_repo]

MODULE_PATH = Path(
    "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/classes/base_agent.py"
)
PACKAGE_ROOT = Path("/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit")


def _load_module():
    module_name = "reddit_base_agent_under_test_emotion_payload"
    if module_name in sys.modules:
        return sys.modules[module_name]

    sys.path.insert(0, str(PACKAGE_ROOT))
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _make_agent(module):
    agent = module.Agent.__new__(module.Agent)
    agent.emotions = ["joy", "sadness", "anger", "fear", "surprise", "disgust"]
    agent.emotion_annotation_enabled = True
    return agent


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        if isinstance(payload, (bytes, bytearray)):
            self._content = bytes(payload)
        elif isinstance(payload, str):
            self._content = payload.encode("utf-8")
        else:
            self._content = json.dumps(payload).encode("utf-8")


def test_reddit_emotion_payload_detection_accepts_labeled_payloads():
    module = _load_module()
    agent = _make_agent(module)

    assert agent._looks_like_emotion_payload("Emotion: joy")
    assert agent._looks_like_emotion_payload("Emotions: joy, sadness")
    assert agent._looks_like_emotion_payload("Detected emotions [joy, anger]")
    assert agent._looks_like_emotion_payload(
        "Here are the emotions identified in the text using the GoEmotions taxonomy:\n"
        "- joy\n- sadness\n- anger"
    )


def test_reddit_generated_content_extractor_skips_labeled_emotion_payload():
    module = _load_module()
    agent = _make_agent(module)

    class ChatOwner:
        def __init__(self):
            self.chat_messages = {}

        def last_message(self, _peer_agent):
            return {"content": "Emotion: joy"}

    peer = object()
    owner = ChatOwner()
    owner.chat_messages[peer] = [
        {"content": "actual generated post"},
        {"content": "Emotion: joy"},
    ]

    extracted = agent._extract_generated_chat_content(
        owner,
        peer,
        prompt_hint="ignored",
        skip_emotion_like=True,
    )
    assert extracted == "actual generated post"


def test_reddit_generated_content_extractor_skips_verbose_emotion_analysis():
    module = _load_module()
    agent = _make_agent(module)

    class ChatOwner:
        def __init__(self):
            self.chat_messages = {}

        def last_message(self, _peer_agent):
            return {
                "content": (
                    "Here are the emotions identified in the text using the GoEmotions taxonomy:\n"
                    "- joy\n- sadness\n- anger"
                )
            }

    peer = object()
    owner = ChatOwner()
    owner.chat_messages[peer] = [
        {"content": "this post actually reacts to the thread"},
        {
            "content": (
                "Here are the emotions identified in the text using the GoEmotions taxonomy:\n"
                "- joy\n- sadness\n- anger"
            )
        },
    ]

    extracted = agent._extract_generated_chat_content(
        owner,
        peer,
        prompt_hint="ignored",
        skip_emotion_like=True,
    )
    assert extracted == "this post actually reacts to the thread"


def test_reddit_emotion_payload_detection_accepts_rationale_lists():
    module = _load_module()
    agent = _make_agent(module)
    agent.emotions = [
        "admiration",
        "disapproval",
        "curiosity",
        "disappointment",
        "remorse",
        "caring",
        "fear",
    ]

    assert agent._looks_like_emotion_payload(
        "admiration for the individual's passionate advocacy of library values\n"
        "disapproval for the potential motives behind censorship\n"
        "curiosity about the decision-making process used by Lithuanian libraries\n"
        "disappointment with the lack of consultation"
    )


def test_reddit_emotion_handler_turns_follow_toggle():
    module = _load_module()
    agent = _make_agent(module)

    agent.emotion_annotation_enabled = False
    assert agent._handler_auto_reply_turns() == 0

    agent.emotion_annotation_enabled = True
    assert agent._handler_auto_reply_turns() == 1


def test_reddit_clean_text_strips_trailing_emotion_fragment():
    module = _load_module()
    agent = _make_agent(module)
    agent.name = "tommy96"

    cleaned = agent._Agent__clean_text(
        "found this gem at a congressional hearing yesterday, (fear, anger"
    )

    assert cleaned == "found this gem at a congressional hearing yesterday"


def test_reddit_comment_payload_keeps_text_and_emotions_separate(monkeypatch):
    module = _load_module()
    agent = _make_agent(module)

    agent.name = "forumuser"
    agent.user_id = 17
    agent.base_url = "http://example.test"
    agent.llm_config = {"config_list": [{"model": "llama3.2"}]}
    agent.prompts = {
        "agent_roleplay_comments_share": "persona",
        "handler_instructions": "handler",
        "handler_comment": "{conv}",
    }
    agent._Agent__effify = lambda template, **kwargs: template.format(**kwargs) if kwargs else template
    agent._get_llm_config_for_write_action = lambda: agent.llm_config
    agent._append_system_messages_to_prompt = lambda base_prompt, tid: base_prompt
    agent._append_stress_level_to_prompt = lambda base_prompt, tid: base_prompt
    agent._is_generated_text_usable = lambda text: True
    agent._extract_generated_chat_content = lambda *args, **kwargs: "I think this policy is wrong."
    agent._extract_optional_emotion_eval = lambda *args, **kwargs: ["anger"]
    agent._memory_use_subtle_prompt_mode = lambda: True
    agent._memory_get_author_id_and_username = lambda post_id: (None, None)
    agent._memory_get_thread_root_id = lambda post_id: None
    agent._memory_build_query_text = lambda *args, **kwargs: ""
    agent._memory_build_reply_context = lambda *args, **kwargs: ("", {})
    agent._memory_build_tiered_context = lambda *args, **kwargs: ("", {})
    agent._memory_build_conversation_cues = lambda *args, **kwargs: {}
    agent._memory_format_conversation_cues = lambda *args, **kwargs: ""
    agent._detect_high_affect_signal = lambda **kwargs: {
        "is_high_affect": False,
        "confidence": 0.0,
        "source": "rules",
        "triggers": {},
    }
    agent._memory_format_high_affect_flags = lambda *args, **kwargs: ""
    agent._memory_collect_high_affect_recall = lambda *args, **kwargs: {
        "items": [],
        "counts_by_bucket": {},
        "has_usable_memories": False,
        "prompt_block": "",
    }
    agent._build_comment_style_options = lambda **kwargs: {
        "style_names": ["default"],
        "quick_styles_allowed": True,
    }
    agent._forum_forced_skip_reason = lambda target_quality: None
    agent._select_comment_style = lambda *args, **kwargs: {"selected_style": "default"}
    agent._log_comment_style_selection = lambda *args, **kwargs: None
    agent._record_generated_comment = lambda *args, **kwargs: None
    agent._has_recent_identical_comment = lambda *args, **kwargs: False
    agent._is_thread_duplicate = lambda *args, **kwargs: False
    agent._apply_stress_reward_comment = lambda *args, **kwargs: None
    agent._record_recent_comment = lambda *args, **kwargs: None
    agent._record_writing_action = lambda *args, **kwargs: None
    agent._decision_log = lambda *args, **kwargs: None
    agent._memory_after_comment = lambda *args, **kwargs: None
    agent._memory_reply_references_recalled_item = lambda *args, **kwargs: (True, "")
    agent._memory_rewrite_reply_with_callback = lambda *args, **kwargs: ""
    agent._enforce_text_limits = lambda text, **kwargs: (text, {})
    agent._memory_after_vote = lambda *args, **kwargs: None
    agent._Agent__evaluate_follow = lambda *args, **kwargs: None
    agent._Agent__update_user_interests = lambda *args, **kwargs: None
    agent.get_user_from_post = lambda post_id: "alice"
    agent._Agent__get_thread = lambda post_id, max_tweets=None: ["Root post\n"]

    class _FakeAssistantAgent:
        def __init__(self, *args, **kwargs):
            self.chat_messages = {}

        def initiate_chat(self, other, message=None, silent=True, max_turns=1):
            other.chat_messages[self] = [{"content": "No emotions were found in this annotated sentence."}]

        def reset(self):
            return None

    posted = []

    monkeypatch.setattr(module, "AssistantAgent", _FakeAssistantAgent)
    monkeypatch.setattr(
        module,
        "post",
        lambda url, headers=None, data=None: posted.append((url, json.loads(data)))
        or _FakeResponse({"deduped": False}),
    )
    monkeypatch.setattr(
        module,
        "get",
        lambda *args, **kwargs: _FakeResponse([]),
    )
    monkeypatch.setattr(module, "Admin_users", SimpleNamespace(query=SimpleNamespace(filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None))), raising=False)
    monkeypatch.setattr(module, "Post_topics", SimpleNamespace(query=SimpleNamespace(filter_by=lambda **kwargs: SimpleNamespace(all=lambda: []))), raising=False)
    monkeypatch.setattr(module, "Post_Sentiment", SimpleNamespace(query=SimpleNamespace(filter_by=lambda **kwargs: SimpleNamespace(first=lambda: None))), raising=False)

    result = agent.comment(post_id=99, tid=7)

    assert result is not False
    comment_payload = next(payload for url, payload in posted if url == "http://example.test/comment")
    assert comment_payload["text"] == "I think this policy is wrong."
    assert comment_payload["emotions"] == ["anger"]
    assert "No emotions were found in this annotated sentence." not in comment_payload["text"]
