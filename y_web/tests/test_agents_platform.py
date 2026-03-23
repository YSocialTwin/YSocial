"""
Phase I — agents/platform.py tests.

Covers the pure helper functions that require no running DB:
  - normalize_population_username_type
  - population_matches_platform  (with infer_population_username_type mocked)

Functions that execute real DB queries (ensure_population_username_type_column,
infer_population_username_type) are tested via lightweight mocking so no
database fixture is required.
"""

from unittest.mock import MagicMock, patch

import pytest
pytestmark = pytest.mark.integration



# ---------------------------------------------------------------------------
# normalize_population_username_type
# ---------------------------------------------------------------------------


def test_normalize_returns_microblogging():
    from y_web.src.agents.platform import normalize_population_username_type

    assert normalize_population_username_type("microblogging") == "microblogging"


def test_normalize_returns_forum():
    from y_web.src.agents.platform import normalize_population_username_type

    assert normalize_population_username_type("forum") == "forum"


def test_normalize_unknown_returns_default():
    from y_web.src.agents.platform import normalize_population_username_type

    assert normalize_population_username_type("unknown_value") == "microblogging"


def test_normalize_none_returns_default():
    from y_web.src.agents.platform import normalize_population_username_type

    assert normalize_population_username_type(None) == "microblogging"


def test_normalize_empty_string_returns_default():
    from y_web.src.agents.platform import normalize_population_username_type

    assert normalize_population_username_type("") == "microblogging"


def test_normalize_strips_whitespace():
    from y_web.src.agents.platform import normalize_population_username_type

    assert normalize_population_username_type("  forum  ") == "forum"


def test_normalize_case_insensitive():
    from y_web.src.agents.platform import normalize_population_username_type

    assert normalize_population_username_type("MICROBLOGGING") == "microblogging"
    assert normalize_population_username_type("Forum") == "forum"


def test_normalize_custom_default():
    from y_web.src.agents.platform import normalize_population_username_type

    assert normalize_population_username_type("junk", default="forum") == "forum"


# ---------------------------------------------------------------------------
# population_matches_platform (infer_population_username_type mocked)
# ---------------------------------------------------------------------------


def _mock_pop(username_type=None):
    pop = MagicMock()
    pop.id = 1
    pop.username_type = username_type
    return pop


def test_matches_platform_true_when_inferred_matches():
    """population_matches_platform returns True when inferred type equals requested."""
    from y_web.src.agents.platform import population_matches_platform

    pop = _mock_pop("microblogging")
    with patch(
        "y_web.src.agents.platform.infer_population_username_type",
        return_value="microblogging",
    ):
        assert population_matches_platform(pop, "microblogging") is True


def test_matches_platform_false_when_mismatch():
    """population_matches_platform returns False on explicit type mismatch."""
    from y_web.src.agents.platform import population_matches_platform

    pop = _mock_pop("forum")
    with patch(
        "y_web.src.agents.platform.infer_population_username_type",
        return_value="forum",
    ):
        assert population_matches_platform(pop, "microblogging") is False


def test_matches_platform_true_when_inferred_is_none():
    """When inferred type is None the population is considered universal → True."""
    from y_web.src.agents.platform import population_matches_platform

    pop = _mock_pop(None)
    with patch(
        "y_web.src.agents.platform.infer_population_username_type",
        return_value=None,
    ):
        assert population_matches_platform(pop, "microblogging") is True
        assert population_matches_platform(pop, "forum") is True


def test_matches_platform_forum_explicit():
    from y_web.src.agents.platform import population_matches_platform

    pop = _mock_pop("forum")
    with patch(
        "y_web.src.agents.platform.infer_population_username_type",
        return_value="forum",
    ):
        assert population_matches_platform(pop, "forum") is True


# ---------------------------------------------------------------------------
# infer_population_username_type — explicit attribute short-circuit
# (no DB needed when username_type is already set correctly)
# ---------------------------------------------------------------------------


def test_infer_returns_explicit_type_when_valid(app):
    """When population.username_type is a valid type, infer returns it directly."""
    from y_web.src.agents.platform import infer_population_username_type

    pop = _mock_pop("forum")

    with app.app_context():
        # No DB queries fired because explicit attribute is valid
        with patch(
            "y_web.src.agents.platform.Population_Experiment"
        ) as mock_pe:
            mock_pe.query.filter_by.return_value.all.return_value = []
            result = infer_population_username_type(pop)

    assert result == "forum"


def test_infer_returns_none_when_no_associations(app):
    """When explicit type is blank and no Population_Experiment rows exist, returns None."""
    from y_web.src.agents.platform import infer_population_username_type

    pop = _mock_pop(None)

    with app.app_context():
        with patch(
            "y_web.src.agents.platform.Population_Experiment"
        ) as mock_pe:
            mock_pe.query.filter_by.return_value.all.return_value = []
            result = infer_population_username_type(pop)

    assert result is None
