import time

from y_web.src.external_runtime import manager


class _Spec:
    github_repo = "owner/repo"


def test_remote_lookups_are_cached_and_clearable():
    manager.clear_remote_cache()
    calls = []

    def fn():
        calls.append(1)
        return ["main"], None

    for _ in range(3):
        assert manager._remote_cached("t", _Spec, "", None, fn) == (["main"], None)
    assert len(calls) == 1
    manager.clear_remote_cache()
    manager._remote_cached("t", _Spec, "", None, fn)
    assert len(calls) == 2


def test_failed_lookup_cached_briefly(monkeypatch):
    manager.clear_remote_cache()
    calls = []

    def fn():
        calls.append(1)
        return [], "boom"

    manager._remote_cached("e", _Spec, "", None, fn)
    manager._remote_cached("e", _Spec, "", None, fn)
    assert len(calls) == 1
    # an expired entry is fetched again
    monkeypatch.setattr(manager, "_REMOTE_TTL_ERR", -1.0)
    manager.clear_remote_cache()
    manager._remote_cached("e", _Spec, "", None, fn)
    manager._remote_cached("e", _Spec, "", None, fn)
    assert len(calls) == 3


def test_releases_and_branches_queried_once_per_status(monkeypatch):
    manager.clear_remote_cache()
    hits = {"rel": 0, "br": 0}
    monkeypatch.setattr(
        manager,
        "_list_releases_uncached",
        lambda spec, github_token=None: (
            hits.__setitem__("rel", hits["rel"] + 1) or [],
            None,
        ),
    )
    monkeypatch.setattr(
        manager,
        "_list_remote_branches_uncached",
        lambda spec, github_token=None: (
            hits.__setitem__("br", hits["br"] + 1) or ["main"],
            None,
        ),
    )
    key = manager.grouped_runtime_specs()[0][2][0].key
    manager.get_runtime_status(key)
    manager.get_runtime_status(key)
    assert hits == {"rel": 1, "br": 1}
