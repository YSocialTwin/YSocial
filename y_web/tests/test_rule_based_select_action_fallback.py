import pytest

pytestmark = pytest.mark.unit


def test_rule_based_select_action_fallback_present():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClient/y_client/classes/base_agent.py",
        "r",
    ).read()

    assert "def _llm_agents_enabled_from_config(config):" in source
    assert "len(llm_agents) == 1" in source
    assert "llm_agents[0] is None" in source
    assert "def _has_usable_llm_config(self):" in source
    assert 'if not getattr(self, "llm_agents_enabled", True):' in source
    assert "return self.select_action_lite(" in source
    assert (
        "def select_action_lite(self, tid, actions, max_length_thread_reading=5):"
        in source
    )


def test_forum_rule_based_runtime_uses_fake_agents():
    client_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/clients/client_web.py",
        "r",
    ).read()
    utils_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/utils.py",
        "r",
    ).read()
    package_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/__init__.py",
        "r",
    ).read()
    classes_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/classes/__init__.py",
        "r",
    ).read()

    assert "def _rule_based_agents_enabled(self):" in client_source
    assert "def _agent_class_for_payload(self, payload):" in client_source
    assert "def _coerce_legacy_rule_based_config(self, payloads):" in client_source
    assert "from y_client.classes.base_agent import Agent, Agents" in client_source
    assert "from y_client.classes.fake_base_agent import FakeAgent" in client_source
    assert 'if not str((payload or {}).get("type") or "").strip():' in client_source
    assert (
        'self.config.setdefault("agents", {})["llm_agents"] = [None]' in client_source
    )
    assert (
        'self._coerce_legacy_rule_based_config(data.get("agents", []))' in client_source
    )
    assert (
        'self._coerce_legacy_rule_based_config(agents.get("agents", []))'
        in client_source
    )
    assert "AgentClass = self._agent_class_for_payload(ag)" in client_source
    assert "AgentClass = self._agent_class_for_payload(a)" in client_source
    assert "agent = AgentClass(" in client_source
    assert "ag = AgentClass(" in client_source
    assert "def _rule_based_agents_enabled(config):" in utils_source
    assert (
        "AgentClass = FakeAgent if _rule_based_agents_enabled(config) else Agent"
        in utils_source
    )
    assert "from y_client.classes.base_agent import Agent" in utils_source
    assert "from y_client.classes.fake_base_agent import FakeAgent" in utils_source
    assert "from y_client.classes.fake_base_agent import *" in package_source
    assert "from .fake_base_agent import *" in classes_source


def test_forum_rule_based_fake_agent_supports_forum_share_aliases():
    fake_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/classes/fake_base_agent.py",
        "r",
    ).read()
    crud_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/clients/_crud.py",
        "r",
    ).read()

    assert 'if action == "NEWS":' in fake_source
    assert 'action = "SHARE_LINK"' in fake_source
    assert 'elif action == "SHARE_LINK":' in fake_source
    assert "self.share_link(tid=tid, article=article, website=website)" in fake_source
    assert 'elif action == "SHARE_IMAGE":' in fake_source
    assert "self.share_image(tid=tid, image_post=image_post)" in fake_source
    assert '"llm_agents": [] if llm_agents_enabled else [None],' in crud_source


def test_forum_rule_based_fake_agent_records_opinion_updates():
    fake_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/classes/fake_base_agent.py",
        "r",
    ).read()
    server_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YServerReddit/y_server/routes/user_managment.py",
        "r",
    ).read()

    assert (
        "self._record_self_post_opinions(topic_ids=interests_id, tid=int(tid))"
        in fake_source
    )
    assert "self.new_opinions(post_id, tid, post_text)" in fake_source
    assert "def share_link(self, tid, article, website):" in fake_source
    assert 'api_url = f"{self.base_url}/news"' in fake_source
    assert "def share_image(self, tid: int, image_post):" in fake_source
    assert 'api_url = f"{self.base_url}/image_post"' in fake_source
    assert (
        "def comment_image(self, image: object, tid: int, article_id: int = None):"
        in fake_source
    )
    assert '@app.route("/set_user_opinions", methods=["POST"])' in server_source


def test_forum_web_init_restores_fake_agent_follow_probabilities():
    reddit_base_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/classes/base_agent.py",
        "r",
    ).read()

    assert "self.probability_of_daily_follow = float(" in reddit_base_source
    assert (
        'config["agents"].get("probability_of_daily_follow", 0)' in reddit_base_source
    )
    assert "self.probability_of_secondary_follow = float(" in reddit_base_source
    assert (
        'config["agents"].get("probability_of_secondary_follow", 0)'
        in reddit_base_source
    )


def test_forum_fake_agent_uses_runtime_db_session_for_news_and_images():
    fake_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/classes/fake_base_agent.py",
        "r",
    ).read()

    assert "def _current_db_session(self):" in fake_source
    assert (
        "from y_client.clients.client_web import session as global_session"
        in fake_source
    )
    assert "current_session = self._current_db_session()" in fake_source
    assert "current_session.query(Websites)" in fake_source
    assert "current_session.query(Images)" in fake_source
    assert "current_session.commit()" in fake_source
    assert "current_session.delete(image)" in fake_source


def test_forum_new_opinions_resolves_numeric_author_id():
    reddit_base_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit/y_client/classes/base_agent.py",
        "r",
    ).read()
    server_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/external/YServerReddit/y_server/routes/user_managment.py",
        "r",
    ).read()

    assert (
        "author_id, _author_username = self.get_username_from_post(post_id)"
        in reddit_base_source
    )
    assert "legacy_author = self.get_user_from_post(post_id)" in reddit_base_source
    assert "author_id = int(legacy_author)" in reddit_base_source
    assert "return json.dumps(user.username)" in server_source


def test_process_runner_forum_rule_based_daily_follow_uses_fake_agent():
    runner_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/process_runner.py",
        "r",
    ).read()
    sampler_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/agent_sampler.py",
        "r",
    ).read()

    assert 'elif exp.platform_type == "forum":' in runner_source
    assert "from y_client.classes.fake_base_agent import FakeAgent" in runner_source
    assert "agent.__class__ = FakeAgent" in runner_source
    assert "def _rule_based_agents_enabled(config):" in sampler_source
    assert "g.__class__ = FakeAgent" in sampler_source
