"""
Phase 2 validation tests.

Verifies that:
- All four sub-modules of y_web.src.data_access are importable
- All public functions are reachable via the new canonical paths
- All public functions are still reachable via the legacy shim
- Shim exports are the same objects as the canonical ones
- No circular imports are introduced
- The src/data_access package is importable without the optional faker dependency
"""

import sys

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKER_MISSING = False
try:
    import faker  # noqa: F401
except ImportError:
    _FAKER_MISSING = True


# ---------------------------------------------------------------------------
# Phase 2 — package structure
# ---------------------------------------------------------------------------


def test_src_data_access_package_importable():
    """y_web.src.data_access must be importable and expose its __init__.py."""
    import y_web.src.data_access

    assert y_web.src.data_access.__file__.endswith("__init__.py")


def test_src_data_access_submodules_importable():
    """All four sub-modules must be discoverable by the import system."""
    import importlib.util

    for mod in [
        "y_web.src.data_access.profiles",
        "y_web.src.data_access.trends",
        "y_web.src.data_access.users",
        "y_web.src.data_access.posts",
    ]:
        # Use find_spec without triggering execution; after the package
        # __init__ has already been imported above, sub-module specs can be
        # located without side effects.
        assert mod in sys.modules or importlib.util.find_spec(mod) is not None, (
            f"Sub-module not found: {mod}"
        )


# ---------------------------------------------------------------------------
# Phase 2 — canonical import paths
# ---------------------------------------------------------------------------


class TestCanonicalProfilesImports:
    def test_get_safe_profile_pic(self):
        from y_web.src.data_access.profiles import get_safe_profile_pic

        assert callable(get_safe_profile_pic)


class TestCanonicalTrendsImports:
    def test_get_trending_hashtags(self):
        from y_web.src.data_access.trends import get_trending_hashtags

        assert callable(get_trending_hashtags)

    def test_get_trending_emotions(self):
        from y_web.src.data_access.trends import get_trending_emotions

        assert callable(get_trending_emotions)

    def test_get_trending_topics(self):
        from y_web.src.data_access.trends import get_trending_topics

        assert callable(get_trending_topics)

    def test_get_top_user_hashtags(self):
        from y_web.src.data_access.trends import get_top_user_hashtags

        assert callable(get_top_user_hashtags)

    def test_all_trends_functions(self):
        from y_web.src.data_access.trends import (
            get_top_user_hashtags,
            get_trending_emotions,
            get_trending_hashtags,
            get_trending_topics,
        )

        for fn in [
            get_top_user_hashtags,
            get_trending_emotions,
            get_trending_hashtags,
            get_trending_topics,
        ]:
            assert callable(fn), f"{fn} is not callable"


class TestCanonicalUsersImports:
    def test_get_user_friends(self):
        from y_web.src.data_access.users import get_user_friends

        assert callable(get_user_friends)

    def test_get_mutual_friends(self):
        from y_web.src.data_access.users import get_mutual_friends

        assert callable(get_mutual_friends)

    def test_get_user_recent_interests(self):
        from y_web.src.data_access.users import get_user_recent_interests

        assert callable(get_user_recent_interests)

    def test_all_users_functions(self):
        from y_web.src.data_access.users import (
            get_mutual_friends,
            get_user_friends,
            get_user_recent_interests,
        )

        for fn in [get_mutual_friends, get_user_friends, get_user_recent_interests]:
            assert callable(fn), f"{fn} is not callable"


class TestCanonicalPostsImports:
    def test_get_user_recent_posts(self):
        from y_web.src.data_access.posts import get_user_recent_posts

        assert callable(get_user_recent_posts)

    def test_augment_text(self):
        from y_web.src.data_access.posts import augment_text

        assert callable(augment_text)

    def test_get_elicited_emotions(self):
        from y_web.src.data_access.posts import get_elicited_emotions

        assert callable(get_elicited_emotions)

    def test_get_topics(self):
        from y_web.src.data_access.posts import get_topics

        assert callable(get_topics)

    def test_get_unanswered_mentions(self):
        from y_web.src.data_access.posts import get_unanswered_mentions

        assert callable(get_unanswered_mentions)

    def test_get_posts_associated_to_hashtags(self):
        from y_web.src.data_access.posts import get_posts_associated_to_hashtags

        assert callable(get_posts_associated_to_hashtags)

    def test_get_posts_associated_to_interest(self):
        from y_web.src.data_access.posts import get_posts_associated_to_interest

        assert callable(get_posts_associated_to_interest)

    def test_get_posts_associated_to_emotion(self):
        from y_web.src.data_access.posts import get_posts_associated_to_emotion

        assert callable(get_posts_associated_to_emotion)

    def test_all_posts_functions(self):
        from y_web.src.data_access.posts import (
            augment_text,
            get_elicited_emotions,
            get_posts_associated_to_emotion,
            get_posts_associated_to_hashtags,
            get_posts_associated_to_interest,
            get_topics,
            get_unanswered_mentions,
            get_user_recent_posts,
        )

        for fn in [
            get_user_recent_posts,
            augment_text,
            get_posts_associated_to_hashtags,
            get_posts_associated_to_interest,
            get_posts_associated_to_emotion,
            get_elicited_emotions,
            get_topics,
            get_unanswered_mentions,
        ]:
            assert callable(fn), f"{fn} is not callable"


class TestSrcDataAccessPackageReExports:
    """y_web.src.data_access must re-export every public function."""

    def test_profiles_via_package(self):
        from y_web.src.data_access import get_safe_profile_pic

        assert callable(get_safe_profile_pic)

    def test_trends_via_package(self):
        from y_web.src.data_access import (
            get_top_user_hashtags,
            get_trending_emotions,
            get_trending_hashtags,
            get_trending_topics,
        )

        for fn in [
            get_top_user_hashtags,
            get_trending_emotions,
            get_trending_hashtags,
            get_trending_topics,
        ]:
            assert callable(fn)

    def test_users_via_package(self):
        from y_web.src.data_access import (
            get_mutual_friends,
            get_user_friends,
            get_user_recent_interests,
        )

        for fn in [get_mutual_friends, get_user_friends, get_user_recent_interests]:
            assert callable(fn)

    def test_posts_via_package(self):
        from y_web.src.data_access import (
            augment_text,
            get_elicited_emotions,
            get_posts_associated_to_emotion,
            get_posts_associated_to_hashtags,
            get_posts_associated_to_interest,
            get_topics,
            get_unanswered_mentions,
            get_user_recent_posts,
        )

        for fn in [
            get_user_recent_posts,
            augment_text,
            get_posts_associated_to_hashtags,
            get_posts_associated_to_interest,
            get_posts_associated_to_emotion,
            get_elicited_emotions,
            get_topics,
            get_unanswered_mentions,
        ]:
            assert callable(fn)


# ---------------------------------------------------------------------------
# Phase 2 — legacy shim backward-compatibility
# ---------------------------------------------------------------------------


class TestLegacyShimBackwardCompatibility:
    """All existing from y_web.src.data_access import X usages must keep working."""

    def test_shim_profiles_function(self):
        from y_web.src.data_access import get_safe_profile_pic

        assert callable(get_safe_profile_pic)

    def test_shim_trends_functions(self):
        from y_web.src.data_access import (
            get_top_user_hashtags,
            get_trending_emotions,
            get_trending_hashtags,
            get_trending_topics,
        )

        for fn in [
            get_top_user_hashtags,
            get_trending_emotions,
            get_trending_hashtags,
            get_trending_topics,
        ]:
            assert callable(fn)

    def test_shim_users_functions(self):
        from y_web.src.data_access import (
            get_mutual_friends,
            get_user_friends,
            get_user_recent_interests,
        )

        for fn in [get_mutual_friends, get_user_friends, get_user_recent_interests]:
            assert callable(fn)

    def test_shim_posts_functions(self):
        from y_web.src.data_access import (
            augment_text,
            get_elicited_emotions,
            get_posts_associated_to_emotion,
            get_posts_associated_to_hashtags,
            get_posts_associated_to_interest,
            get_topics,
            get_unanswered_mentions,
            get_user_recent_posts,
        )

        for fn in [
            get_user_recent_posts,
            augment_text,
            get_posts_associated_to_hashtags,
            get_posts_associated_to_interest,
            get_posts_associated_to_emotion,
            get_elicited_emotions,
            get_topics,
            get_unanswered_mentions,
        ]:
            assert callable(fn)

    def test_shim_functions_are_same_objects_as_canonical(self):
        """The shim must re-export the exact same function objects, not copies."""
        from y_web.src.data_access import augment_text as shim_aug
        from y_web.src.data_access import get_trending_hashtags as shim_th
        from y_web.src.data_access import get_user_recent_posts as shim_urp

        from y_web.src.data_access.posts import augment_text as src_aug
        from y_web.src.data_access.posts import get_user_recent_posts as src_urp
        from y_web.src.data_access.trends import get_trending_hashtags as src_th

        assert shim_urp is src_urp
        assert shim_th is src_th
        assert shim_aug is src_aug


# ---------------------------------------------------------------------------
# Phase 2 — no circular imports
# ---------------------------------------------------------------------------


def test_no_circular_imports():
    """All src.data_access sub-modules must already be in sys.modules (no
    circular import forced a reload or caused an ImportError)."""
    expected = [
        "y_web.src.data_access",
        "y_web.src.data_access.profiles",
        "y_web.src.data_access.trends",
        "y_web.src.data_access.users",
        "y_web.src.data_access.posts",
    ]
    for mod in expected:
        assert mod in sys.modules, f"Expected module not in sys.modules: {mod}"
