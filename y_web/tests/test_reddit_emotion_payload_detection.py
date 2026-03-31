import importlib.util
import sys
from pathlib import Path

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
