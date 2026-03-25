from pathlib import Path


def test_base_agent_restores_opinion_runtime_path():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClient/y_client/classes/base_agent.py"
    ).read_text()
    assert "def _seed_initial_opinions_if_needed(self):" in source
    assert 'def new_opinions(self, post_id, tid, text=""):' in source
    assert "def _record_self_post_opinions(self, *, topic_ids, tid):" in source
    assert "def _record_current_opinions_for_topic_ids(" in source
    assert "if self.opinions_enabled:" in source
    assert "self.new_opinions(post_id, tid, post_text)" in source
    assert (
        "self._record_self_post_opinions(topic_ids=interests_id, tid=int(tid))"
        in source
    )
    assert '"opinions": getattr(self, "opinions", None)' in source


def test_client_web_passes_experiment_db_path_and_opinions():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClient/y_client/clients/client_web.py"
    ).read_text()
    assert 'opinions=ag.get("opinions")' in source
    assert (
        'experiment_db_path=os.path.join(self.base_path, "database_server.db")'
        in source
    )
    assert "def _rule_based_agents_enabled(self):" in source
    assert (
        "AgentClass = FakeAgent if self._rule_based_agents_enabled() else Agent"
        in source
    )
    assert (
        "PageClass = FakePageAgent if self._rule_based_agents_enabled() else PageAgent"
        in source
    )


def test_fake_agent_keeps_opinion_write_hooks():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClient/y_client/classes/fake_base_agent.py"
    ).read_text()
    assert (
        "self._record_self_post_opinions(topic_ids=interests_id, tid=int(tid))"
        in source
    )
    assert source.count("self.new_opinions(post_id, tid, post_text)") >= 2


def test_generate_user_uses_fake_agent_for_non_llm_configs():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClient/y_client/utils.py"
    ).read_text()
    assert "def _rule_based_agents_enabled(config):" in source
    assert (
        "AgentClass = FakeAgent if _rule_based_agents_enabled(config) else Agent"
        in source
    )
    assert (
        "PageClass = FakePageAgent if _rule_based_agents_enabled(config) else PageAgent"
        in source
    )


def test_web_init_restores_fake_agent_follow_probabilities():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClient/y_client/classes/base_agent.py"
    ).read_text()
    assert "self.probability_of_daily_follow = float(" in source
    assert 'config["agents"].get("probability_of_daily_follow", 0)' in source
    assert "self.probability_of_secondary_follow = float(" in source
    assert 'config["agents"].get("probability_of_secondary_follow", 0)' in source
