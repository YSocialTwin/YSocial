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
        "toggleActivityProfiles",
        "toggleProfessionBackgrounds",
        "toggleProfessionTag",
        "updateFemalePercentage",
        "updateMalePercentage",
        "toggleDropdown",
        "toggleOption",
        "updateDistributionParams",
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


def test_admin_head_loads_shared_admin_component_and_icon_css():
    content = ADMIN_HEAD.read_text(encoding="utf-8")
    assert "assets/css/admin-components.css" in content
    assert "assets/vendor/mdi/css/materialdesignicons.min.css" in content
