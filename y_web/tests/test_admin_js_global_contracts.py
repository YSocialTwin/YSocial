from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

STATIC_JS_DIR = Path("/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js")
ADMIN_HEAD = Path(
    "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/head.html"
)


def _contains_any(path: Path, snippets):
    content = path.read_text(encoding="utf-8")
    return any(snippet in content for snippet in snippets)


def test_admin_dashboard_exports_template_handlers():
    path = STATIC_JS_DIR / "admin-dashboard.js"
    required = [
        "window.startExperimentServer = startExperimentServer;",
        "window.stopExperimentServer = stopExperimentServer;",
        "window.selectExperiment = selectExperiment;",
        "window.joinExperiment = joinExperiment;",
        "window.startJupyterSession = startJupyterSession;",
        "window.stopJupyterSession = stopJupyterSession;",
    ]
    content = path.read_text(encoding="utf-8")
    for item in required:
        assert item in content


def test_admin_settings_exports_template_handlers():
    path = STATIC_JS_DIR / "admin-settings.js"
    content = path.read_text(encoding="utf-8")
    for name in [
        "startExperimentServer",
        "stopExperimentServer",
        "downloadSelectedExperiments",
        "downloadAllExperiments",
        "toggleGroup",
        "autoCreateGroups",
        "addScheduleGroup",
        "clearLogs",
        "startSchedule",
        "stopSchedule",
        "deleteAllExperiments",
        "displayExperimentFileName",
        "fetchEmbeddingModels",
    ]:
        assert name in content and "Object.assign(window" in content


def test_admin_experiments_exports_template_handlers():
    path = STATIC_JS_DIR / "admin-experiments.js"
    content = path.read_text(encoding="utf-8")
    for name in [
        "startExperimentServer",
        "stopExperimentServer",
        "selectExperiment",
        "joinExperiment",
        "startJupyter",
        "stopJupyter",
        "submitExperimentLogs",
        "toggleRemoteServerEdit",
        "cancelRemoteServerEdit",
        "testRemoteServer",
        "saveRemoteServer",
    ]:
        assert name in content and "Object.assign(window" in content
    assert "experiment-topics-tags" in content
    assert "experiment-topics-hidden" in content
    assert "experiment-topics-input" in content


def test_forum_client_logs_support_legacy_shared_log_fallback():
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py"
    ).read_text(encoding="utf-8")

    assert 'platform_type", "") == "forum"' in route_source
    assert "agent_execution.log" in route_source


def test_forum_process_runner_passes_per_client_log_file_to_reddit_client():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/process_runner.py"
    ).read_text(encoding="utf-8")

    assert 'if exp.platform_type == "forum":' in source
    assert 'client_kwargs["log_file"] = log_file' in source


def test_admin_clients_exports_template_handlers():
    path = STATIC_JS_DIR / "admin-clients.js"
    content = path.read_text(encoding="utf-8")
    for name in [
        "toggleSimulationAdvancedParams",
        "toggleLLMFields",
        "toggleAdvancedSettings",
        "toggleImageTranscription",
        "fetchModelsForClient",
        "validateImageLLMModel",
        "displayNetworkFileNameCreate",
        "toggleStandardMemorySettings",
        "toggleStandardMemoryAdvancedParams",
        "syncStandardEmbeddingFieldsState",
        "toggleForumMemorySettings",
        "toggleForumMemoryAdvancedParams",
        "applyContextPreset",
    ]:
        assert name in content and "Object.assign(window" in content


def test_admin_populations_exports_template_handlers():
    path = STATIC_JS_DIR / "admin-populations.js"
    content = path.read_text(encoding="utf-8")
    for name in [
        "displayFileName",
        "removeMergePopulation",
        "toggleActivityProfiles",
        "toggleProfessionBackgrounds",
        "toggleProfessionTag",
        "updateFemalePercentage",
        "updateMalePercentage",
        "toggleDropdown",
        "toggleOption",
        "removeTag",
        "updatePercentageValue",
        "updateDistributionParams",
        "updatePercentage",
        "removeProfile",
    ]:
        assert name in content and "Object.assign(window" in content


def test_admin_miscellanea_and_feeds_export_template_handlers():
    miscellanea = (STATIC_JS_DIR / "admin-miscellanea.js").read_text(encoding="utf-8")
    feeds = (STATIC_JS_DIR / "admin-feeds.js").read_text(encoding="utf-8")
    opinion = (STATIC_JS_DIR / "admin-opinion.js").read_text(encoding="utf-8")

    assert "Object.assign(window" in miscellanea
    assert "switchMiscTab" in miscellanea
    assert "updateDistributionParams" in miscellanea

    assert "Object.assign(window" in feeds
    for name in [
        "parseSubreddit",
        "addParsedSubreddit",
        "removeFeed",
        "uploadImageFeeds",
        "exportImageFeeds",
        "parseRssFeed",
        "addParsedRssFeed",
        "removeRssFeed",
        "uploadRssFeeds",
    ]:
        assert name in feeds

    assert "window.selectUpdateRule = AdminOpinion.selectUpdateRule;" in opinion
    assert "createDistributionChart" in opinion
    assert "dist-chart-canvas" in opinion


def test_admin_notifications_page_uses_dedicated_actions_and_download_links():
    notifications_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/download_notifications.html"
    ).read_text(encoding="utf-8")
    notifications_js = (STATIC_JS_DIR / "admin-notifications.js").read_text(
        encoding="utf-8"
    )
    nav_js = (STATIC_JS_DIR / "admin-nav.js").read_text(encoding="utf-8")

    assert "assets/js/admin-notifications.js" in notifications_template
    assert 'id="notifications-table-body"' in notifications_template
    assert "n.download_url" in notifications_template
    assert "window.markRead = markRead;" in notifications_js
    assert "window.deleteNotification = deleteNotification;" in notifications_js
    assert ">Download</a>" in nav_js


def test_visibility_settings_uses_grid_table_for_current_researcher_visibility():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/visibility_settings.html"
    ).read_text(encoding="utf-8")
    script = (STATIC_JS_DIR / "admin-visibility.js").read_text(encoding="utf-8")

    assert "assets/vendor/js/gridjs.umd.js" in template
    assert 'id="researcher-visibility-table"' in template
    assert "YS_DATA_VISIBILITY" in template
    assert "assets/js/admin-visibility.js" in template
    assert "new gridjs.Grid({" in script
    assert "pagination: {" in script
    assert "window.revokeVisibilityAssignment = revokeVisibilityAssignment;" in script


def test_admin_head_loads_shared_admin_component_and_icon_css():
    content = ADMIN_HEAD.read_text(encoding="utf-8")
    assert "assets/css/admin-components.css" in content
    assert "assets/vendor/mdi/css/materialdesignicons.min.css" in content


def test_agents_grid_bootstrap_uses_data_attributes_instead_of_route_matching():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/agents.html"
    ).read_text(encoding="utf-8")
    script = (STATIC_JS_DIR / "admin-pages.js").read_text(encoding="utf-8")

    assert (
        "data-list-endpoint=\"{{ list_endpoint|default('/admin/agents_data') }}\""
        in template
    )
    assert "document.querySelector('#table[data-list-endpoint]')" in script


def test_admin_nav_unhides_notification_badge_with_bootstrap_class_toggle():
    path = STATIC_JS_DIR / "admin-nav.js"
    content = path.read_text(encoding="utf-8")

    assert "badge.classList.remove('d-none');" in content
    assert "badge.classList.add('d-none');" in content


def test_experiment_details_pages_expose_configuration_block_consistently():
    standard = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/experiment_details.html"
    ).read_text(encoding="utf-8")
    forum = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/experiment_details_forum.html"
    ).read_text(encoding="utf-8")
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py"
    ).read_text(encoding="utf-8")

    assert "<b>Experiment Configuration</b>" in standard
    assert "<b>Experiment Configuration</b>" in forum
    assert "Enable or disable runtime annotations and memory." in forum
    assert "{% if can_manage_experiment %}" in forum
    assert "<span>Opinion Dynamics</span>" in forum
    assert "<span>Memory</span>" in forum
    assert "<span>Toxicity</span>" in forum
    assert "<span>Emotion</span>" in forum
    assert "<span>Sentiment</span>" in forum
    assert "Update Configuration" in forum
    assert 'name="opinion_dynamics_enabled"' in standard
    assert 'name="opinion_dynamics_enabled"' in forum
    assert 'name="stress_reward_enabled"' in standard
    assert 'name="stress_reward_enabled"' in forum
    assert "Additional Configuration" in standard
    assert "/admin/stress_reward_settings/{{ experiment.idexp }}" in standard
    assert "/admin/stress_reward_settings/{{ experiment.idexp }}" in forum
    assert 'name="sr_churn_enabled"' not in standard
    assert 'name="memory_enabled"' in standard
    assert 'name="memory_enabled"' in forum
    assert 'name="toxicity_annotation"' in forum
    assert 'name="emotion_annotation"' in forum
    assert 'name="sentiment_annotation"' in forum
    assert "Detoxify is used automatically" in standard
    assert "Detoxify is used automatically" in forum
    assert "/admin/opinion_configuration_forum/" in forum
    assert "/admin/opinion_evolution/" in forum
    assert (
        "{% if memory_configuration_supported and memory_module_enabled %}" in standard
    )
    assert "{% if memory_configuration_supported and memory_module_enabled %}" in forum
    assert (
        "llm_agents_enabled_effective = _experiment_uses_llm_agents(experiment)"
        in route_source
    )


def test_stress_reward_settings_page_exists_as_dedicated_admin_view():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/stress_reward_settings.html"
    ).read_text(encoding="utf-8")
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_data.py"
    ).read_text(encoding="utf-8")

    assert "Stress / Reward Settings" in template
    assert (
        'action="/admin/update_stress_reward_settings/{{ experiment.idexp }}"'
        in template
    )
    assert 'name="sr_churn_enabled"' in template
    assert 'name="sr_coupling_reward_buffers_stress_alpha"' in template
    assert 'name="sr_event_{{ family }}_{{ subtype }}_stress"' in template
    assert '"/admin/stress_reward_settings/<int:uid>"' in route_source
    assert '"/admin/update_stress_reward_settings/<int:uid>"' in route_source


def test_forum_experiment_details_uses_supported_switch_markup_for_avatar_toggle():
    forum = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/experiment_details_forum.html"
    ).read_text(encoding="utf-8")

    assert '<label class="switch-small">' in forum
    assert '<span class="slider-small round"></span>' in forum
    assert '<span class="check"></span>' not in forum


def test_experiment_details_quick_guide_mentions_configuration_first_pipeline():
    standard = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/experiment_details.html"
    ).read_text(encoding="utf-8")
    forum = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/experiment_details_forum.html"
    ).read_text(encoding="utf-8")

    expected = (
        "First update <b>Experiment Configuration</b> to unlock execution controls"
    )
    assert expected in standard
    assert expected in forum


def test_client_creation_pages_use_experiment_memory_gate():
    standard = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients.html"
    ).read_text(encoding="utf-8")
    forum = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients_forum.html"
    ).read_text(encoding="utf-8")
    hpc = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients_hpc.html"
    ).read_text(encoding="utf-8")

    assert "experimentMemoryEnabled" in standard
    assert "memoryConfigurationSupported" in standard
    assert "standard_memory_enabled" in standard
    assert "{% if not experiment_memory_enabled %}" in standard

    assert "experimentMemoryEnabled" in forum
    assert "memoryConfigurationSupported" in forum
    assert "{% if memory_configuration_supported %}" in forum
    assert "{% if not experiment_memory_enabled %}" in forum

    assert "experimentMemoryEnabled" in hpc
    assert "memoryConfigurationSupported" in hpc
    assert "standard_memory_enabled" in hpc
    assert "{% if not experiment_memory_enabled %}" in hpc
    assert "Agent Memory (Run-Scoped)" in hpc


def test_client_forms_use_fetch_based_vision_model_selection():
    standard = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients.html"
    ).read_text(encoding="utf-8")
    forum = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients_forum.html"
    ).read_text(encoding="utf-8")
    hpc = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients_hpc.html"
    ).read_text(encoding="utf-8")
    admin_clients_js = (STATIC_JS_DIR / "admin-clients.js").read_text(encoding="utf-8")

    for template in (standard, forum, hpc):
        assert "Fetch Vision Models" in template
        assert 'name="llm_v_agent"' in template
        assert "validateImageLLMModel()" not in template

    assert "function fetchVisionModelsForClient()" in admin_clients_js


def test_create_experiment_enforces_external_repo_availability():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py"
    ).read_text(encoding="utf-8")

    assert "def _external_repo_availability():" in source
    assert 'get_runtime_status("microblogging_server").installed' in source
    assert '"microblogging_client"' in source
    assert 'get_runtime_status("hpc_simulator").installed' in source
    assert 'get_runtime_status("forum_server").installed' in source
    assert '"forum_client"' in source
    assert (
        "Forum experiments are unavailable because YServerReddit and YClientReddit are not both present."
        in source
    )
    assert (
        "Microblogging experiments are unavailable because neither YServer/YClient nor YSimulator is present."
        in source
    )


def test_external_runtime_panel_sidebar_link_and_templates_exist():
    head_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/head.html"
    ).read_text(encoding="utf-8")
    panel_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/external_runtimes.html"
    ).read_text(encoding="utf-8")
    logs_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/external_runtime_logs.html"
    ).read_text(encoding="utf-8")

    assert "sidebar-external-runtimes" in head_template
    assert "url_for('experiments.external_runtimes')" in head_template
    assert "External Runtime Plugins" in panel_template
    assert "GitHub session" in panel_template
    assert 'name="github_token"' in panel_template
    assert "Anonymous GitHub access" in panel_template
    assert "Installation source" in panel_template
    assert 'name="install_source"' in panel_template
    assert "GitHub Release" in panel_template
    assert "Git checkout" in panel_template
    assert "Install Plugin" in panel_template
    assert "Advanced maintenance" in panel_template
    assert "<details" in panel_template
    assert "Not installed" in panel_template
    assert "Private" in panel_template
    assert "Public" in panel_template
    assert "Install Dependencies" in panel_template
    assert (
        "Dependency installation uses the same Python interpreter currently running YSocial"
        in panel_template
    )
    assert "action='delete'" in panel_template
    assert "View Logs" in panel_template
    assert "Operation Output" in panel_template
    assert '{% include "admin/footer.html" %}' in panel_template
    assert "Operation Log" in logs_template
    assert '{% include "admin/footer.html" %}' in logs_template


def test_hpc_clients_template_disables_embedded_vllm_when_unavailable():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients_hpc.html"
    ).read_text(encoding="utf-8")
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/clients/_crud.py"
    ).read_text(encoding="utf-8")

    assert (
        'option value="vllm" {% if not embedded_vllm_available %}disabled{% endif %}'
        in template
    )
    assert (
        'context["embedded_vllm_available"] = bool(is_vllm_installed())' in route_source
    )


def test_embedding_settings_template_and_routes_support_hpc_memory_embeddings():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/embedding_settings.html"
    ).read_text(encoding="utf-8")
    helper_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_helpers.py"
    ).read_text(encoding="utf-8")
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_feeds.py"
    ).read_text(encoding="utf-8")

    assert "Experiments do not assume any embedding backend." in template
    assert "server_config.json" in helper_source
    assert 'if experiment.simulator_type == "HPC"' in route_source
