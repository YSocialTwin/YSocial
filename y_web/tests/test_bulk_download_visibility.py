"""Tests for bulk experiment download visibility filtering."""

from types import SimpleNamespace

import pytest

from y_web.routes.admin.sub.experiments import _notifications

pytestmark = pytest.mark.unit


class _FakeQuery:
    def __init__(self, experiments):
        self._experiments = list(experiments)

    def all(self):
        return list(self._experiments)

    def filter_by(self, **kwargs):
        filtered = self._experiments
        for key, value in kwargs.items():
            filtered = [exp for exp in filtered if getattr(exp, key) == value]
        return _FakeQuery(filtered)

    def filter(self, _criterion):
        left = getattr(_criterion, "left", None)
        right = getattr(_criterion, "right", None)
        field_name = getattr(left, "key", None)
        field_value = getattr(right, "value", None)
        if field_name is None:
            return self
        return _FakeQuery(
            [
                exp
                for exp in self._experiments
                if getattr(exp, field_name, None) == field_value
            ]
        )


def test_bulk_download_all_uses_visible_completed_experiments(monkeypatch):
    visible = [
        SimpleNamespace(idexp=1, exp_status="completed", exp_group="g1"),
        SimpleNamespace(idexp=2, exp_status="active", exp_group="g1"),
        SimpleNamespace(idexp=3, exp_status="completed", exp_group="g2"),
    ]
    monkeypatch.setattr(
        _notifications,
        "get_visible_experiment_query",
        lambda _admin_user: _FakeQuery(visible),
    )

    resolved = _notifications._resolve_bulk_experiment_ids(
        "all", admin_user=SimpleNamespace(id=10)
    )

    assert resolved == [1, 3]


def test_bulk_download_explicit_ids_are_intersected_with_visibility(monkeypatch):
    visible = [
        SimpleNamespace(idexp=1, exp_status="completed", exp_group="g1"),
        SimpleNamespace(idexp=3, exp_status="completed", exp_group="g2"),
    ]
    monkeypatch.setattr(
        _notifications,
        "get_visible_experiment_query",
        lambda _admin_user: _FakeQuery(visible),
    )

    resolved = _notifications._resolve_bulk_experiment_ids(
        [1, 2, "3", 999, 1], admin_user=SimpleNamespace(id=10)
    )

    assert resolved == [1, 3]


def test_bulk_download_group_payload_is_scoped_by_visible_query(monkeypatch):
    visible = [
        SimpleNamespace(idexp=1, exp_status="completed", exp_group="shared"),
        SimpleNamespace(idexp=2, exp_status="completed", exp_group="shared"),
    ]

    monkeypatch.setattr(
        _notifications,
        "get_visible_experiment_query",
        lambda _admin_user: _FakeQuery(visible),
    )

    resolved = _notifications._resolve_bulk_experiment_ids(
        {"group": "shared", "status": "completed"},
        admin_user=SimpleNamespace(id=10),
    )

    assert resolved == [1, 2]
