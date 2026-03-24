import pytest

from y_web.routes.admin.sub.populations import _normalize_percentage_distribution


pytestmark = pytest.mark.unit


def test_normalize_percentage_distribution_falls_back_to_uniform_when_missing():
    distribution = _normalize_percentage_distribution({}, ["1", "2", "3"])

    assert set(distribution.keys()) == {"1", "2", "3"}
    assert pytest.approx(sum(distribution.values()), rel=1e-6) == 100.0


def test_normalize_percentage_distribution_preserves_valid_selected_values():
    distribution = _normalize_percentage_distribution(
        {"1": "35", "2": "42", "3": "23", "99": "100"},
        ["1", "2", "3"],
    )

    assert distribution == {"1": 35.0, "2": 42.0, "3": 23.0}
