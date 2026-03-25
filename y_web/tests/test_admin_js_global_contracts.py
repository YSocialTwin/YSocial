from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

STATIC_JS_DIR = Path("/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js")
ADMIN_HEAD = Path("/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/head.html")


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


def test_admin_head_loads_shared_admin_component_and_icon_css():
    content = ADMIN_HEAD.read_text(encoding="utf-8")
    assert "assets/css/admin-components.css" in content
    assert "assets/vendor/mdi/css/materialdesignicons.min.css" in content


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
    assert "Generated content annotations are unavailable for forum experiments." in forum
    assert "{% if can_manage_experiment and experiment.llm_agents_enabled %}" in forum
    assert "<span>Opinion Dynamics</span>" not in forum
    assert "Update Configuration" in forum
    assert 'name="opinion_dynamics_enabled"' in standard
    assert 'name="opinion_dynamics_enabled"' not in forum
    assert 'name="memory_enabled"' in standard
    assert 'name="memory_enabled"' in forum
    assert "{% if memory_configuration_supported and memory_module_enabled %}" in standard
    assert "{% if memory_configuration_supported and memory_module_enabled %}" in forum
    assert 'if getattr(exp, "platform_type", "") == "forum":' in route_source


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

    expected = "First update <b>Experiment Configuration</b> to unlock execution controls"
    assert expected in standard
    assert expected in forum


def test_client_creation_pages_use_experiment_memory_gate():
    standard = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients.html"
    ).read_text(encoding="utf-8")
    forum = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/clients_forum.html"
    ).read_text(encoding="utf-8")

    assert "experimentMemoryEnabled" in standard
    assert "memoryConfigurationSupported" in standard
    assert 'standard_memory_enabled' in standard
    assert "{% if not experiment_memory_enabled %}" in standard

    assert "experimentMemoryEnabled" in forum
    assert "memoryConfigurationSupported" in forum
    assert "{% if memory_configuration_supported %}" in forum
    assert "{% if not experiment_memory_enabled %}" in forum
