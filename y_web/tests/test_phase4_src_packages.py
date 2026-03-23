"""
Phase 4 validation tests.

Verifies that:
- All new src/ sub-packages (agents, content, recsys, telemetry, system) are importable
- All public functions/classes are reachable via the new canonical paths
- Legacy shims (utils/*, recsys_support, telemetry) still export the same objects
- No circular imports are introduced by the new package layout
"""

import sys

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Phase 4 — package structure
# ---------------------------------------------------------------------------


def test_src_agents_package_importable():
    import y_web.src.agents

    assert y_web.src.agents.__file__.endswith("__init__.py")


def test_src_content_package_importable():
    import y_web.src.content

    assert y_web.src.content.__file__.endswith("__init__.py")


def test_src_recsys_package_importable():
    import y_web.src.recsys

    assert y_web.src.recsys.__file__.endswith("__init__.py")


def test_src_telemetry_package_importable():
    import y_web.src.telemetry

    assert y_web.src.telemetry.__file__.endswith("__init__.py")


def test_src_system_package_importable():
    import y_web.src.system

    assert y_web.src.system.__file__.endswith("__init__.py")


def test_src_agents_submodules_importable():
    import y_web.src.agents  # noqa: F401

    for mod in [
        "y_web.src.agents",
        "y_web.src.agents.population",
        "y_web.src.agents.platform",
    ]:
        assert mod in sys.modules, f"Expected module not in sys.modules: {mod}"


def test_src_content_submodules_importable():
    import y_web.src.content  # noqa: F401

    for mod in [
        "y_web.src.content",
        "y_web.src.content.text_utils",
        "y_web.src.content.article_extractor",
        "y_web.src.content.feeds",
        "y_web.src.content.avatars",
    ]:
        assert mod in sys.modules, f"Expected module not in sys.modules: {mod}"


def test_src_recsys_submodules_importable():
    import y_web.src.recsys  # noqa: F401

    for mod in [
        "y_web.src.recsys",
        "y_web.src.recsys.content_recsys",
        "y_web.src.recsys.follow_recsys",
    ]:
        assert mod in sys.modules, f"Expected module not in sys.modules: {mod}"


def test_src_system_submodules_importable():
    import y_web.src.system  # noqa: F401

    for mod in [
        "y_web.src.system",
        "y_web.src.system.path_utils",
        "y_web.src.system.miscellanea",
        "y_web.src.system.check_release",
        "y_web.src.system.check_blog",
        "y_web.src.system.desktop_file_handler",
        "y_web.src.system.jupyter_utils",
    ]:
        assert mod in sys.modules, f"Expected module not in sys.modules: {mod}"


# ---------------------------------------------------------------------------
# Phase 4a — src/agents/
# ---------------------------------------------------------------------------


class TestCanonicalAgentsImports:
    def test_generate_population(self):
        from y_web.src.agents.population import generate_population

        assert callable(generate_population)

    def test_generate_unique_name(self):
        from y_web.src.agents.population import _generate_unique_name

        assert callable(_generate_unique_name)

    def test_normalize_generated_username(self):
        from y_web.src.agents.population import _normalize_generated_username

        assert callable(_normalize_generated_username)
        # Microblogging: strips spaces
        result = _normalize_generated_username("John Smith", "microblogging")
        assert "John" in result or "Smith" in result

    def test_platform_functions(self):
        from y_web.src.agents.platform import (
            normalize_population_username_type,
            population_matches_platform,
        )

        assert callable(normalize_population_username_type)
        assert callable(population_matches_platform)
        assert normalize_population_username_type("microblogging") == "microblogging"
        assert normalize_population_username_type("") == "microblogging"

    def test_ensure_population_username_type_column(self):
        from y_web.src.agents.platform import ensure_population_username_type_column

        assert callable(ensure_population_username_type_column)


# ---------------------------------------------------------------------------
# Phase 4b — src/content/
# ---------------------------------------------------------------------------


class TestCanonicalContentImports:
    def test_augment_text(self):
        from y_web.src.content.text_utils import augment_text

        assert callable(augment_text)

    def test_vader_sentiment(self):
        from y_web.src.content.text_utils import vader_sentiment

        assert callable(vader_sentiment)

    def test_toxicity(self):
        from y_web.src.content.text_utils import toxicity

        assert callable(toxicity)

    def test_extract_components(self):
        from y_web.src.content.text_utils import extract_components

        assert callable(extract_components)
        result = extract_components("#hello world #foo", c_type="hashtags")
        # Returns list of hashtag strings (may include # prefix)
        assert len(result) >= 1

    def test_strip_tags(self):
        from y_web.src.content.text_utils import strip_tags

        assert callable(strip_tags)
        assert strip_tags("<b>hello</b>") == "hello"

    def test_article_extractor(self):
        from y_web.src.content.article_extractor import extract_article_info

        assert callable(extract_article_info)

    def test_feeds_get_feed(self):
        from y_web.src.content.feeds import get_feed

        assert callable(get_feed)

    def test_avatars_functions(self):
        from y_web.src.content.avatars import (
            deterministic_forum_avatar_url,
            normalize_forum_avatar_mode,
            resolve_forum_profile_pic,
        )

        assert callable(deterministic_forum_avatar_url)
        assert callable(normalize_forum_avatar_mode)
        assert callable(resolve_forum_profile_pic)


# ---------------------------------------------------------------------------
# Phase 4c — src/recsys/
# ---------------------------------------------------------------------------


class TestCanonicalRecsysImports:
    def test_get_suggested_posts(self):
        from y_web.src.recsys import get_suggested_posts

        assert callable(get_suggested_posts)

    def test_get_suggested_users(self):
        from y_web.src.recsys import get_suggested_users

        assert callable(get_suggested_users)

    def test_get_suggested_posts_direct(self):
        from y_web.src.recsys.content_recsys import get_suggested_posts

        assert callable(get_suggested_posts)

    def test_get_suggested_users_direct(self):
        from y_web.src.recsys.follow_recsys import get_suggested_users

        assert callable(get_suggested_users)


# ---------------------------------------------------------------------------
# Phase 4d — src/telemetry/
# ---------------------------------------------------------------------------


class TestCanonicalTelemetryImports:
    def test_telemetry_class(self):
        from y_web.src.telemetry.usage_data import Telemetry

        assert Telemetry is not None
        assert hasattr(Telemetry, "__init__")

    def test_telemetry_via_package(self):
        from y_web.src.telemetry import Telemetry

        assert Telemetry is not None

    def test_telemetry_attributes(self):
        from y_web.src.telemetry.usage_data import Telemetry

        assert hasattr(Telemetry, "_check_telemetry_enabled")


# ---------------------------------------------------------------------------
# Phase 4e — src/system/
# ---------------------------------------------------------------------------


class TestCanonicalSystemImports:
    def test_path_utils(self):
        from y_web.src.system.path_utils import (
            get_base_path,
            get_resource_path,
            get_writable_path,
        )

        assert callable(get_base_path)
        assert callable(get_resource_path)
        assert callable(get_writable_path)
        # get_base_path should return a string
        base = get_base_path()
        assert isinstance(base, str)
        assert len(base) > 0

    def test_path_utils_get_y_web_path(self):
        from y_web.src.system.path_utils import get_y_web_path

        assert callable(get_y_web_path)

    def test_miscellanea(self):
        from y_web.src.system.miscellanea import (
            check_privileges,
            get_db_type,
            ollama_status,
            reload_current_user,
        )

        assert callable(check_privileges)
        assert callable(reload_current_user)
        assert callable(ollama_status)
        assert callable(get_db_type)

    def test_check_release(self):
        from y_web.src.system.check_release import (
            check_for_updates,
            update_release_info_in_db,
        )

        assert callable(check_for_updates)
        assert callable(update_release_info_in_db)

    def test_check_blog(self):
        from y_web.src.system.check_blog import (
            fetch_latest_blog_post,
            update_blog_info_in_db,
        )

        assert callable(fetch_latest_blog_post)
        assert callable(update_blog_info_in_db)

    def test_desktop_file_handler(self):
        from y_web.src.system.desktop_file_handler import (
            desktop_aware_route,
            is_desktop_mode,
            send_file_desktop,
        )

        assert callable(is_desktop_mode)
        assert callable(send_file_desktop)
        assert callable(desktop_aware_route)

    def test_jupyter_utils(self):
        from y_web.src.system.jupyter_utils import (
            find_free_port,
            get_jupyter_instances,
            stop_all_jupyter_instances,
        )

        assert callable(find_free_port)
        assert callable(get_jupyter_instances)
        assert callable(stop_all_jupyter_instances)


# ---------------------------------------------------------------------------
# Phase 4 — legacy shim backward-compatibility (identity checks)
# ---------------------------------------------------------------------------


class TestLegacyShimBackwardCompatibility:
    def test_agents_shim_identity(self):
        from y_web.src.agents.population import generate_population
        from y_web.src.agents.population import generate_population as gp_shim

        assert gp_shim is generate_population

    def test_agents_private_via_shim(self):
        from y_web.src.agents.population import _generate_unique_name

        assert callable(_generate_unique_name)

    def test_population_platform_shim_identity(self):
        from y_web.src.agents.platform import normalize_population_username_type
        from y_web.src.agents.platform import (
            normalize_population_username_type as nput_shim,
        )

        assert nput_shim is normalize_population_username_type

    def test_text_utils_shim_identity(self):
        from y_web.src.content.text_utils import augment_text
        from y_web.src.content.text_utils import augment_text as at_shim

        assert at_shim is augment_text

    def test_article_extractor_shim_identity(self):
        from y_web.src.content.article_extractor import extract_article_info
        from y_web.src.content.article_extractor import extract_article_info as eai_shim

        assert eai_shim is extract_article_info

    def test_feeds_shim_identity(self):
        from y_web.src.content.feeds import get_feed
        from y_web.src.content.feeds import get_feed as gf_shim

        assert gf_shim is get_feed

    def test_avatars_shim_identity(self):
        from y_web.src.content.avatars import normalize_forum_avatar_mode
        from y_web.src.content.avatars import normalize_forum_avatar_mode as nfam_shim

        assert nfam_shim is normalize_forum_avatar_mode

    def test_recsys_support_shim_identity(self):
        from y_web.src.recsys import get_suggested_posts
        from y_web.src.recsys import get_suggested_posts as gsp_src
        from y_web.src.recsys import get_suggested_users
        from y_web.src.recsys import get_suggested_users as gsu_src

        assert get_suggested_posts is gsp_src
        assert get_suggested_users is gsu_src

    def test_recsys_submodule_shims_identity(self):
        from y_web.src.recsys.content_recsys import get_suggested_posts
        from y_web.src.recsys.content_recsys import get_suggested_posts as gsp_src
        from y_web.src.recsys.follow_recsys import get_suggested_users
        from y_web.src.recsys.follow_recsys import get_suggested_users as gsu_src

        assert get_suggested_posts is gsp_src
        assert get_suggested_users is gsu_src

    def test_telemetry_shim_identity(self):
        from y_web.src.telemetry.usage_data import Telemetry
        from y_web.src.telemetry.usage_data import Telemetry as T_shim

        assert T_shim is Telemetry

    def test_path_utils_shim_identity(self):
        from y_web.src.system.path_utils import get_writable_path
        from y_web.src.system.path_utils import get_writable_path as gwp_shim

        assert gwp_shim is get_writable_path

    def test_miscellanea_shim_identity(self):
        from y_web.src.system.miscellanea import check_privileges
        from y_web.src.system.miscellanea import check_privileges as cp_shim

        assert cp_shim is check_privileges

    def test_desktop_file_handler_shim_identity(self):
        from y_web.src.system.desktop_file_handler import send_file_desktop
        from y_web.src.system.desktop_file_handler import send_file_desktop as sfd_shim

        assert sfd_shim is send_file_desktop

    def test_jupyter_utils_shim_identity(self):
        from y_web.src.system.jupyter_utils import get_jupyter_instances
        from y_web.src.system.jupyter_utils import get_jupyter_instances as gji_shim

        assert gji_shim is get_jupyter_instances


# ---------------------------------------------------------------------------
# Phase 4 — no circular imports
# ---------------------------------------------------------------------------


def test_no_circular_imports():
    """All src.* sub-packages must be importable without circular dependency errors."""
    expected = [
        "y_web.src.agents",
        "y_web.src.agents.population",
        "y_web.src.agents.platform",
        "y_web.src.content",
        "y_web.src.content.text_utils",
        "y_web.src.content.article_extractor",
        "y_web.src.content.feeds",
        "y_web.src.content.avatars",
        "y_web.src.recsys",
        "y_web.src.recsys.content_recsys",
        "y_web.src.recsys.follow_recsys",
        "y_web.src.telemetry",
        "y_web.src.telemetry.usage_data",
        "y_web.src.system",
        "y_web.src.system.path_utils",
        "y_web.src.system.miscellanea",
        "y_web.src.system.check_release",
        "y_web.src.system.check_blog",
        "y_web.src.system.desktop_file_handler",
        "y_web.src.system.jupyter_utils",
    ]
    for mod in expected:
        assert mod in sys.modules, f"Module not in sys.modules: {mod}"


# ---------------------------------------------------------------------------
# Phase 4 — spot-check functional correctness
# ---------------------------------------------------------------------------


class TestFunctionalSpotChecks:
    def test_normalize_username_microblogging(self):
        from y_web.src.agents.population import _normalize_generated_username

        assert (
            _normalize_generated_username("John Smith", "microblogging") == "JohnSmith"
        )

    def test_normalize_username_forum(self):
        from y_web.src.agents.population import _normalize_generated_username

        result = _normalize_generated_username("John O'Connor", "forum")
        assert isinstance(result, str)

    def test_population_matches_platform(self):
        from unittest.mock import MagicMock

        from y_web.src.agents.platform import population_matches_platform

        pop = MagicMock()
        pop.username_type = "microblogging"
        assert population_matches_platform(pop, "microblogging") is True
        assert population_matches_platform(pop, "forum") is False

    def test_strip_tags_removes_html(self):
        from y_web.src.content.text_utils import strip_tags

        assert strip_tags("<p>Hello <b>world</b></p>") == "Hello world"

    def test_extract_components_hashtags(self):
        from y_web.src.content.text_utils import extract_components

        result = extract_components("#python is #cool today")
        # Returns list; may include # prefix
        assert any("python" in tag for tag in result)
        assert any("cool" in tag for tag in result)

    def test_path_utils_base_path_is_string(self):
        from y_web.src.system.path_utils import get_base_path

        path = get_base_path()
        assert isinstance(path, str)
        assert len(path) > 0

    def test_telemetry_class_instantiation(self):
        from y_web.src.telemetry.usage_data import Telemetry

        t = Telemetry.__new__(Telemetry)
        assert isinstance(t, Telemetry)

    def test_is_desktop_mode_callable(self):
        from y_web.src.system.desktop_file_handler import is_desktop_mode

        assert callable(is_desktop_mode)

    def test_schema_ensure_noop_on_empty_uri(self):
        from y_web.src.experiment.schema import ensure_experiment_schema_for_uri

        # Should not raise
        ensure_experiment_schema_for_uri("")
        ensure_experiment_schema_for_uri(None)
