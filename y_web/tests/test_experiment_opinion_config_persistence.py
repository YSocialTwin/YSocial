import pytest

pytestmark = pytest.mark.skip


def test_stress_reward_client_sync_preserves_structured_system_config():
    from y_web.routes.admin.sub.experiments._helpers import (
        sync_stress_reward_client_config,
    )

    client_config = {"simulation": {"name": "demo"}}
    stress_reward_config = {
        "enabled": True,
        "backward_rounds": 18,
        "system": {
            "coupling": {"reward_buffers_stress_alpha": 0.12},
            "churn": {"enabled": True, "bias": -1.3},
            "events": {"reaction": {"like": {"stress": -0.01, "reward": 0.05}}},
        },
    }

    updated = sync_stress_reward_client_config(client_config, stress_reward_config)

    assert updated["stress_reward"]["enabled"] is True
    assert updated["stress_reward"]["backward_rounds"] == 18
    assert (
        updated["stress_reward"]["system"]["coupling"]["reward_buffers_stress_alpha"]
        == 0.12
    )
    assert updated["stress_reward"]["system"]["churn"]["enabled"] is True
    assert updated["stress_reward"]["system"]["churn"]["bias"] == -1.3
    assert (
        updated["stress_reward"]["system"]["events"]["reaction"]["like"]["reward"]
        == 0.05
    )
    assert (
        updated["stress_reward"]["system"]["events"]["report"]["mass_report"]["stress"]
        == 0.12
    )


def test_standard_and_hpc_experiment_configs_persist_opinion_toggle():
    source = open(
        "y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()
    assert '"opinion_dynamics_enabled": opinion_dynamics_enabled' in source
    assert '"memory": {"enabled": False}' in source
    assert '"stress_reward": default_stress_reward_config()' in source
    assert '"opinions_enabled": opinions_enabled' not in source
    assert "generate_hpc_config(" in source
    assert "opinion_dynamics_enabled=opinion_dynamics_enabled" in source


def test_experiment_configuration_confirmation_flag_is_persisted():
    crud_source = open(
        "y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()
    data_source = open(
        "y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()

    assert '"experiment_configuration_confirmed": False' in crud_source
    assert 'config["experiment_configuration_confirmed"] = True' in data_source


def test_experiment_configuration_helpers_are_explicitly_imported():
    data_source = open(
        "y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()
    crud_source = open(
        "y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()

    assert "_experiment_configuration_update_required" in data_source
    assert "_experiment_configuration_box_present" in data_source
    assert "from ._helpers import (" in data_source
    assert "_experiment_configuration_update_required" in crud_source
    assert "from ._helpers import (" in crud_source


def test_experiment_topics_update_route_reuses_exp_topic_and_config_storage():
    data_source = open(
        "y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()

    assert '"/admin/update_experiment_topics/<int:uid>"' in data_source
    assert "db.session.query(Exp_Topic).filter_by(exp_id=uid).delete()" in data_source
    assert 'config["topics"] = topics' in data_source


def test_memory_support_is_resolved_and_enforced_across_experiment_and_client_routes():
    data_source = open(
        "y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()
    clients_source = open(
        "y_web/routes/admin/sub/clients/_crud.py",
        "r",
    ).read()

    assert "memory_configuration_supported = bool(" in data_source
    assert (
        "llm_agents_enabled_effective = _experiment_uses_llm_agents(experiment)"
        in data_source
    )
    assert "bool(llm_agents_enabled_effective)" in data_source
    assert "if memory_configuration_supported:" in data_source
    assert 'memory_enabled = _is_checked("memory_enabled")' in data_source
    assert 'memory_config["enabled"] = bool(memory_enabled)' in data_source
    assert 'stress_reward_enabled = _is_checked("stress_reward_enabled")' in data_source
    assert 'config["stress_reward"] = stress_reward_config' in data_source
    assert (
        'if getattr(exp, "platform_type", "") in {"microblogging", "forum", "hpc"}:'
        in data_source
    )
    assert 'if exp.simulator_type == "HPC":' in data_source
    assert "client_config = sync_stress_reward_client_config(" in data_source
    assert "def stress_reward_settings(uid):" in data_source
    assert "def update_stress_reward_settings(uid):" in data_source
    assert (
        'stress_reward_config["system"]["churn"]["enabled"] = _is_checked("sr_churn_enabled")'
        in data_source
    )
    assert 'field_name = f"sr_event_{family}_{subtype}_{variable}"' in data_source
    assert "def _memory_enabled_for_client_creation(experiment):" in clients_source
    assert (
        "experiment_memory_enabled = _memory_enabled_for_client_creation(exp)"
        in clients_source
    )
    assert "bool(_experiment_uses_llm_agents(experiment))" in clients_source


def test_hpc_server_config_generation_and_embedding_routes_support_memory():
    crud_source = open(
        "y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()
    helpers_source = open(
        "y_web/routes/admin/sub/experiments/_helpers.py",
        "r",
    ).read()
    feeds_source = open(
        "y_web/routes/admin/sub/experiments/_feeds.py",
        "r",
    ).read()

    assert '"memory": {"enabled": False}' in crud_source
    assert "This page is only available for Standard and Forum experiments." not in (
        helpers_source
    )
    assert '"server_config.json"' in feeds_source


def test_forum_opinion_dynamics_is_not_forced_off_for_rule_based_runs():
    data_source = open(
        "y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()

    assert "opinion_dynamics_enabled = False" not in data_source
    assert 'if getattr(exp, "platform_type", "") == "forum":' not in (
        data_source.split("def update_experiment_config(uid):", 1)[1].split(
            "memory_configuration_supported =", 1
        )[0]
    )


def test_forum_experiments_always_require_configuration_box_for_lock_workflow():
    helpers_source = open(
        "y_web/routes/admin/sub/experiments/_helpers.py",
        "r",
    ).read()

    assert 'if getattr(experiment, "platform_type", "") == "forum":' not in (
        helpers_source.split(
            "def _experiment_configuration_box_present(experiment):", 1
        )[1].split("def _experiment_uses_llm_agents", 1)[0]
    )
    assert "return True" in (
        helpers_source.split(
            "def _experiment_configuration_box_present(experiment):", 1
        )[1].split("def _experiment_uses_llm_agents", 1)[0]
    )
