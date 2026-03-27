"""
Phase T6 validation tests.

Verifies that:
  - Inline function scripts removed from admin templates
  - External JS files exist and contain the expected functions
  - Data bridges created for Jinja2 variables
  - Script src tags added to modified templates
"""

import os
import re

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES_DIR = os.path.join(REPO_ROOT, "y_web", "templates")
STATIC_JS_DIR = os.path.join(REPO_ROOT, "y_web", "static", "assets", "js")
ADMIN_DIR = os.path.join(TEMPLATES_DIR, "admin")


def _inline_function_scripts(path):
    content = open(path, encoding="utf-8").read()
    result = []
    for s in re.findall(r"<script>(.*?)</script>", content, re.DOTALL):
        if re.search(r"\bfunction\s", s) or "(function(" in s or "(function (" in s:
            result.append(s.strip()[:80])
    return result


def _has_script_src(path, js_filename):
    return js_filename in open(path, encoding="utf-8").read()


# ── admin-client-details.js ──────────────────────────────────────────────────


class TestAdminClientDetailsJs:
    JS = os.path.join(STATIC_JS_DIR, "admin-client-details.js")

    def test_file_exists(self):
        assert os.path.isfile(self.JS)

    def test_contains_fetch_models(self):
        assert "fetchModelsForClient" in open(self.JS).read()

    def test_contains_display_network_filename(self):
        assert "displayNetworkFileName" in open(self.JS).read()

    def test_contains_init_network_model_selector(self):
        assert "initNetworkModelSelector" in open(self.JS).read()

    def test_exposes_global_fetch_models(self):
        assert "window.fetchModelsForClient" in open(self.JS).read()

    def test_exposes_global_display_network_filename(self):
        assert "window.displayNetworkFileName" in open(self.JS).read()


class TestClientDetailsTemplates:
    TEMPLATES = [
        os.path.join(ADMIN_DIR, "client_details.html"),
        os.path.join(ADMIN_DIR, "client_details_forum.html"),
        os.path.join(ADMIN_DIR, "client_details_hpc.html"),
    ]

    def test_no_inline_function_scripts(self):
        for t in self.TEMPLATES:
            funcs = _inline_function_scripts(t)
            assert not funcs, f"{t} still has inline function scripts: {funcs}"

    def test_has_script_src(self):
        for t in self.TEMPLATES:
            assert _has_script_src(
                t, "admin-client-details.js"
            ), f"{t} missing <script src> for admin-client-details.js"

    def test_data_bridge_present(self):
        for t in self.TEMPLATES:
            content = open(t).read()
            assert "YS_DATA_CLIENT" in content, f"{t} missing YS_DATA_CLIENT bridge"


# ── admin-opinion.js ─────────────────────────────────────────────────────────


class TestAdminOpinionJs:
    JS = os.path.join(STATIC_JS_DIR, "admin-opinion.js")

    def test_file_exists(self):
        assert os.path.isfile(self.JS)

    def test_references_ys_data_opinion(self):
        assert "YS_DATA_OPINION" in open(self.JS).read()

    def test_references_ys_data_evolution(self):
        assert "YS_DATA_EVOLUTION" in open(self.JS).read()


class TestOpinionTemplates:
    OPINION_TEMPLATES = [
        os.path.join(ADMIN_DIR, "opinion_configuration.html"),
        os.path.join(ADMIN_DIR, "opinion_configuration_forum.html"),
        os.path.join(ADMIN_DIR, "opinion_configuration_hpc.html"),
    ]
    EVOLUTION_TEMPLATE = os.path.join(ADMIN_DIR, "opinion_evolution.html")

    def test_opinion_config_no_inline_function_scripts(self):
        for t in self.OPINION_TEMPLATES:
            funcs = _inline_function_scripts(t)
            assert not funcs, f"{t} still has inline function scripts"

    def test_opinion_config_has_script_src(self):
        for t in self.OPINION_TEMPLATES:
            assert _has_script_src(t, "admin-opinion.js")

    def test_opinion_config_data_bridge(self):
        for t in self.OPINION_TEMPLATES:
            content = open(t).read()
            assert "YS_DATA_OPINION" in content

    def test_evolution_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.EVOLUTION_TEMPLATE)

    def test_evolution_has_script_src(self):
        assert _has_script_src(self.EVOLUTION_TEMPLATE, "admin-opinion.js")

    def test_evolution_data_bridge(self):
        content = open(self.EVOLUTION_TEMPLATE).read()
        assert "YS_DATA_EVOLUTION" in content


# ── admin-feeds.js ───────────────────────────────────────────────────────────


class TestAdminFeedsJs:
    JS = os.path.join(STATIC_JS_DIR, "admin-feeds.js")

    def test_file_exists(self):
        assert os.path.isfile(self.JS)

    def test_references_ys_data_feeds(self):
        assert "YS_DATA_FEEDS" in open(self.JS).read()

    def test_references_ys_data_rss(self):
        assert "YS_DATA_RSS" in open(self.JS).read()


class TestFeedsTemplates:
    IMAGE_FEEDS = os.path.join(ADMIN_DIR, "image_feeds.html")
    RSS_FEEDS = os.path.join(ADMIN_DIR, "rss_feeds.html")

    def test_image_feeds_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.IMAGE_FEEDS)

    def test_image_feeds_has_script_src(self):
        assert _has_script_src(self.IMAGE_FEEDS, "admin-feeds.js")

    def test_image_feeds_data_bridge(self):
        assert "YS_DATA_FEEDS" in open(self.IMAGE_FEEDS).read()

    def test_rss_feeds_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.RSS_FEEDS)

    def test_rss_feeds_has_script_src(self):
        assert _has_script_src(self.RSS_FEEDS, "admin-feeds.js")

    def test_rss_feeds_data_bridge(self):
        assert "YS_DATA_RSS" in open(self.RSS_FEEDS).read()


# ── admin-users.js ───────────────────────────────────────────────────────────


class TestAdminUsersJs:
    JS = os.path.join(STATIC_JS_DIR, "admin-users.js")

    def test_file_exists(self):
        assert os.path.isfile(self.JS)

    def test_contains_fetch_models_add_user(self):
        assert "fetchModelsForAddUser" in open(self.JS).read()

    def test_contains_fetch_models_user(self):
        assert "fetchModelsForUser" in open(self.JS).read()

    def test_exposes_global_fetch_models_add_user(self):
        assert "window.fetchModelsForAddUser" in open(self.JS).read()

    def test_exposes_global_fetch_models_user(self):
        assert "window.fetchModelsForUser" in open(self.JS).read()


class TestUsersTemplates:
    USERS = os.path.join(ADMIN_DIR, "users.html")
    USER_DETAILS = os.path.join(ADMIN_DIR, "user_details.html")

    def test_users_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.USERS)

    def test_users_has_script_src(self):
        assert _has_script_src(self.USERS, "admin-users.js")

    def test_users_data_bridge(self):
        assert "YS_DATA_USERS" in open(self.USERS).read()

    def test_user_details_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.USER_DETAILS)

    def test_user_details_has_script_src(self):
        assert _has_script_src(self.USER_DETAILS, "admin-users.js")


# ── admin-pages.js ───────────────────────────────────────────────────────────


class TestAdminPagesJs:
    JS = os.path.join(STATIC_JS_DIR, "admin-pages.js")

    def test_file_exists(self):
        assert os.path.isfile(self.JS)

    def test_contains_init_agents_grid(self):
        assert "initAgentsGrid" in open(self.JS).read()

    def test_contains_display_page_collection_filename(self):
        assert "displayPageCollectionFileName" in open(self.JS).read()

    def test_exposes_global_display_page_collection(self):
        assert "window.displayPageCollectionFileName" in open(self.JS).read()


class TestPagesTemplates:
    AGENTS = os.path.join(ADMIN_DIR, "agents.html")
    PAGES = os.path.join(ADMIN_DIR, "pages.html")

    def test_agents_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.AGENTS)

    def test_agents_has_script_src(self):
        assert _has_script_src(self.AGENTS, "admin-pages.js")

    def test_pages_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.PAGES)

    def test_pages_has_script_src(self):
        assert _has_script_src(self.PAGES, "admin-pages.js")


# ── admin-settings.js ────────────────────────────────────────────────────────


class TestAdminSettingsJs:
    JS = os.path.join(STATIC_JS_DIR, "admin-settings.js")

    def test_file_exists(self):
        assert os.path.isfile(self.JS)

    def test_contains_sync_embedding_settings_controls(self):
        assert "syncEmbeddingSettingsControls" in open(self.JS).read()

    def test_contains_fetch_embedding_models(self):
        assert "fetchEmbeddingModels" in open(self.JS).read()


class TestEmbeddingSettingsTemplate:
    TEMPLATE = os.path.join(ADMIN_DIR, "embedding_settings.html")

    def test_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.TEMPLATE)

    def test_has_script_src(self):
        assert _has_script_src(self.TEMPLATE, "admin-settings.js")


# ── admin-dashboard.js ───────────────────────────────────────────────────────


class TestAdminDashboardJs:
    JS = os.path.join(STATIC_JS_DIR, "admin-dashboard.js")

    def test_file_exists(self):
        assert os.path.isfile(self.JS)

    def test_contains_mark_read(self):
        assert "markRead" in open(self.JS).read()

    def test_contains_delete_notification(self):
        assert "deleteNotification" in open(self.JS).read()

    def test_contains_jupyter_frame(self):
        assert "jupyter-frame" in open(self.JS).read()

    def test_exposes_global_mark_read(self):
        assert "window.markRead" in open(self.JS).read()

    def test_exposes_global_delete_notification(self):
        assert "window.deleteNotification" in open(self.JS).read()

    def test_references_ys_data_jupyter(self):
        assert "YS_DATA_JUPYTER" in open(self.JS).read()


class TestDashboardTemplates:
    NOTIFICATIONS = os.path.join(ADMIN_DIR, "download_notifications.html")
    JUPYTER = os.path.join(ADMIN_DIR, "jupyter.html")

    def test_notifications_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.NOTIFICATIONS)

    def test_notifications_has_script_src(self):
        assert _has_script_src(self.NOTIFICATIONS, "admin-notifications.js")

    def test_jupyter_no_inline_function_scripts(self):
        assert not _inline_function_scripts(self.JUPYTER)

    def test_jupyter_has_script_src(self):
        assert _has_script_src(self.JUPYTER, "admin-dashboard.js")

    def test_jupyter_data_bridge(self):
        assert "YS_DATA_JUPYTER" in open(self.JUPYTER).read()


# ── Global inline script count ───────────────────────────────────────────────


class TestGlobalInlineScriptReductionT6:
    T5_BASELINE = 78  # count before T6 (after T5 phase)

    def _count_inline_scripts(self):
        pattern = re.compile(r"<script(?![^>]*src)>", re.IGNORECASE)
        total = 0
        for root, _dirs, files in os.walk(
            os.path.join(REPO_ROOT, "y_web", "templates")
        ):
            for fname in files:
                if fname.endswith(".html"):
                    text = open(os.path.join(root, fname), encoding="utf-8").read()
                    total += len(pattern.findall(text))
        return total

    def test_inline_script_count_decreased_from_t5(self):
        current = self._count_inline_scripts()
        decrease = self.T5_BASELINE - current
        assert decrease >= 20, (
            f"Expected >=20 fewer inline scripts vs T5 baseline of {self.T5_BASELINE}, "
            f"but decrease was only {decrease} (current: {current})"
        )
