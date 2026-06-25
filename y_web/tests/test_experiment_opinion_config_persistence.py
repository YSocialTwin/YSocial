import pytest

pytestmark = pytest.mark.unit


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
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py",
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


def test_hpc_server_config_generation_and_embedding_routes_support_memory():
    crud_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()
    helpers_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_helpers.py",
        "r",
    ).read()
    feeds_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_feeds.py",
        "r",
    ).read()

    assert '"memory": {"enabled": False}' in crud_source
    assert "This page is only available for Standard and Forum experiments." not in (
        helpers_source
    )
    assert '"server_config.json"' in feeds_source


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


def test_stopped_experiments_allow_client_configuration_updates():
    template_paths = [
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/experiment_details.html",
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/experiment_details_forum.html",
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/experiment_details_photo.html",
    ]

    for template_path in template_paths:
        content = open(template_path, "r").read()
        if template_path.endswith("experiment_details_photo.html"):
            assert "experiment_details_variant = 'photo'" in content
            assert 'include "admin/experiment_details.html"' in content
        else:
            assert "experiment.running == 0" in content
            assert "configuration_update_required or experiment.running == 0" in content


def test_new_experiment_form_supports_photo_sharing_platform():
    settings_template = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/settings.html",
        "r",
    ).read()
    settings_js = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/admin-settings.js",
        "r",
    ).read()
    crud_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py",
        "r",
    ).read()
    data_source = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py",
        "r",
    ).read()

    assert 'value="photo_sharing"' in settings_template
    assert "Photo Sharing (e.g., Instagram)" in settings_template
    assert "photoSharingAvailable" in settings_js
    assert 'platform_type == "photo_sharing"' in crud_source
    assert 'simulator_type = "HPC"' in crud_source
    assert "generate_photo_sharing_config(" in crud_source
    assert '"server_name": "orchestrator_server"' in crud_source
    assert '"namespace": "yphotosharing"' in crud_source
    assert '"min_to_start": 1' in crud_source
    assert '"prompts_ygram.json"' in crud_source
    assert "experiment_details_photo.html" in data_source


def test_client_details_pages_expose_editable_simulation_and_action_fields():
    standard_template = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/client_details.html",
        "r",
    ).read()
    forum_template = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/client_details_forum.html",
        "r",
    ).read()

    expected_standard_field_names = [
        'name="days"',
        'name="percentage_new_agents_iteration"',
        'name="percentage_removed_agents_iteration"',
        'name="max_length_thread_reading"',
        'name="reading_from_follower_ratio"',
        'name="probability_of_daily_follow"',
        'name="attention_window"',
        'name="visibility_rounds"',
        'name="post"',
        'name="image"',
        'name="news"',
        'name="comment"',
        'name="read"',
        'name="share"',
        'name="search"',
        'name="vote"',
    ]

    expected_forum_field_names = [
        'name="days"',
        'name="percentage_new_agents_iteration"',
        'name="percentage_removed_agents_iteration"',
        'name="max_length_thread_reading"',
        'name="reading_from_follower_ratio"',
        'name="probability_of_daily_follow"',
        'name="attention_window"',
        'name="visibility_rounds"',
        'name="post"',
        'name="image"',
        'name="comment"',
        'name="read"',
        'name="share"',
        'name="search"',
    ]

    for field_name in expected_standard_field_names:
        assert field_name in standard_template

    for field_name in expected_forum_field_names:
        assert field_name in forum_template


def test_hpc_client_details_align_model_selection_with_active_vllm_model():
    content = open(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/client_details_hpc.html",
        "r",
    ).read()

    assert "config.llm.model == model" in content
    assert 'action="/admin/update_hpc_client_settings/{{ client.id }}"' in content


def test_client_details_pages_expose_memory_and_archetype_editors():
    for template_path in [
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/client_details.html",
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/client_details_forum.html",
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/client_details_hpc.html",
    ]:
        content = open(template_path, "r").read()
        assert "box-memory-config" in content
        assert "memory_enabled" in content
        assert "memory_embedding_model" in content
        assert "box-archetype-config" in content
        assert "archetype_validator" in content
