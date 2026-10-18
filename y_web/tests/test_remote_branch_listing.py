from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.src.external_runtime import manager

pytestmark = pytest.mark.unit


def _spec(tmp_path):
    return SimpleNamespace(
        github_repo="o/r",
        repo_url="https://github.com/o/r.git",
        path=tmp_path / "external" / "r",
        default_branch="main",
    )


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._p = payload

    def json(self):
        return self._p


def test_api_pagination_collects_all_branches(tmp_path, monkeypatch):
    pages = {
        1: [{"name": f"b{i}"} for i in range(100)],
        2: [{"name": "last"}],
    }
    monkeypatch.setattr(
        manager,
        "_github_api_request",
        lambda url, github_token=None: _Resp(200, pages[int(url.rsplit("&page=", 1)[1])]),
    )
    names, err = manager._list_remote_branches(_spec(tmp_path))
    assert err is None and len(names) == 101 and "last" in names


def test_falls_back_to_git_ls_remote_when_api_is_denied(tmp_path, monkeypatch):
    monkeypatch.setattr(
        manager, "_github_api_request", lambda url, github_token=None: _Resp(403)
    )
    monkeypatch.setattr(manager, "host_git_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_git_remote",
        lambda cmd, cwd, github_token=None: (
            "aaa\trefs/heads/main\nbbb\trefs/heads/feature/x\nccc\trefs/heads/dev"
        ),
    )
    names, err = manager._branch_list_for_repo(_spec(tmp_path), git_managed=False)
    assert names == ["dev", "feature/x", "main"] and err is None


def test_reports_error_when_both_sources_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(
        manager, "_github_api_request", lambda url, github_token=None: _Resp(404)
    )
    monkeypatch.setattr(manager, "host_git_available", lambda: False)
    names, err = manager._branch_list_for_repo(_spec(tmp_path), git_managed=False)
    assert names == ["main"] and "private" in err
