import pytest

pytestmark = pytest.mark.unit


def test_standard_and_hpc_experiment_configs_persist_opinion_toggle():
    source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()
    assert '"opinion_dynamics_enabled": opinion_dynamics_enabled' in source
    assert '"memory": {"enabled": False}' in source
    assert '"opinions_enabled": opinions_enabled' not in source
    assert "generate_hpc_config(" in source
    assert "opinion_dynamics_enabled=opinion_dynamics_enabled" in source


def test_experiment_configuration_confirmation_flag_is_persisted():
    crud_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()
    data_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()

    assert '"experiment_configuration_confirmed": False' in crud_source
    assert 'config["experiment_configuration_confirmed"] = True' in data_source


def test_experiment_configuration_helpers_are_explicitly_imported():
    data_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()
    crud_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()

    assert "_experiment_configuration_update_required" in data_source
    assert "_experiment_configuration_box_present" in data_source
    assert "from ._helpers import (" in data_source
    assert "_experiment_configuration_update_required" in crud_source
    assert "from ._helpers import (" in crud_source


def test_experiment_topics_update_route_reuses_exp_topic_and_config_storage():
    data_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()

    assert '"/admin/update_experiment_topics/<int:uid>"' in data_source
    assert "db.session.query(Exp_Topic).filter_by(exp_id=uid).delete()" in data_source
    assert 'config["topics"] = topics' in data_source


def test_memory_support_is_resolved_and_enforced_across_experiment_and_client_routes():
    data_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()
    clients_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/clients/_crud.py",
        "r",
    ).read()

    assert "memory_configuration_supported = bool(" in data_source
    assert (
        "llm_agents_enabled_effective = _experiment_uses_llm_agents(experiment)"
        in data_source
    )
    assert (
        'experiment.simulator_type != "HPC" and llm_agents_enabled_effective'
        in data_source
    )
    assert "if memory_configuration_supported:" in data_source
    assert 'memory_enabled = _is_checked("memory_enabled")' in data_source
    assert 'memory_config["enabled"] = bool(memory_enabled)' in data_source
    assert "def _memory_enabled_for_client_creation(experiment):" in clients_source
    assert (
        "experiment_memory_enabled = _memory_enabled_for_client_creation(exp)"
        in clients_source
    )
    assert 'and bool(getattr(experiment, "llm_agents_enabled", 0))' in clients_source


def test_forum_opinion_dynamics_is_not_forced_off_for_rule_based_runs():
    data_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py",
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
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_helpers.py",
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
