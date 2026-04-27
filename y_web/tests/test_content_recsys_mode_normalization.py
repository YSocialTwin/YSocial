from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def test_normalize_content_recsys_mode_reverse_chrono_alias():
    from y_web.src.recsys.content_recsys import _normalize_content_recsys_mode

    assert _normalize_content_recsys_mode("Reverse Chrono") == "ReverseChrono"
    assert _normalize_content_recsys_mode("reverse_chrono") == "ReverseChrono"
    assert _normalize_content_recsys_mode("RC") == "ReverseChrono"


def test_get_suggested_posts_reverse_chrono_alias_does_not_fallback_to_random(
    monkeypatch,
):
    from y_web.src.recsys import content_recsys

    # ReverseChrono path uses db.session.query(...).filter(...).outerjoin(...).order_by(...).paginate(...)
    paginate_result = MagicMock()
    query_chain = MagicMock()
    query_chain.filter.return_value.outerjoin.return_value.order_by.return_value.paginate.return_value = paginate_result
    db_mock = MagicMock()
    db_mock.session.query.return_value = query_chain
    monkeypatch.setattr(content_recsys, "db", db_mock)

    # Random fallback path calls func.random(); ensure it is not used.
    random_fn = MagicMock(return_value="RANDOM_ORDER")
    monkeypatch.setattr(content_recsys.func, "random", random_fn)

    posts, additional = content_recsys.get_suggested_posts(
        uid=1, mode="Reverse Chrono", page=1, per_page=10
    )

    assert posts is paginate_result
    assert additional is None
    db_mock.session.query.assert_called_once()
    query_chain.filter.return_value.outerjoin.assert_called_once()
    random_fn.assert_not_called()


def test_get_suggested_posts_all_orders_by_round_day_hour(monkeypatch):
    from y_web.src.recsys import content_recsys

    paginate_result = MagicMock()
    query_chain = MagicMock()
    query_chain.filter_by.return_value.outerjoin.return_value.order_by.return_value.paginate.return_value = paginate_result
    db_mock = MagicMock()
    db_mock.session.query.return_value = query_chain
    monkeypatch.setattr(content_recsys, "db", db_mock)

    posts, additional = content_recsys.get_suggested_posts(
        uid="all", mode="Reverse Chrono", page=1, per_page=10
    )

    assert posts is paginate_result
    assert additional is None
    query_chain.filter_by.return_value.outerjoin.assert_called_once()
