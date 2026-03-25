import pytest

pytestmark = pytest.mark.unit


def test_rule_based_select_action_fallback_present():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClient/y_client/classes/base_agent.py",
        "r",
    ).read()

    assert "def _has_usable_llm_config(self):" in source
    assert 'if not getattr(self, "llm_agents_enabled", True):' in source
    assert "return self.select_action_lite(" in source
    assert "def select_action_lite(self, tid, actions, max_length_thread_reading=5):" in source
