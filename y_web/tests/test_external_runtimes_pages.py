"""Plugin list + detail pages: one entry for microblogging and for forum, install/update from the detail page."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from y_web.routes.admin.sub.experiments import _external_runtimes as route_mod
from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import _client_as

_STATIC = Path(__file__).resolve().parents[1] / "static" / "assets" / "js"


def _repo(key, group, installed=False, label=None):
    return {
        "key": key,
        "label": label or key,
        "group": group,
        "group_label": group,
        "category_label": "Runtimes",
        "installed": installed,
        "exists": installed,
        "plugin_description": f"{key} description",
        "git_managed": False,
        "is_symlink": False,
        "dirty": False,
    }


def test_microblogging_and_forum_are_one_entry_each():
    status = [
        {"group": "hpc", "label": "HPC", "repos": [_repo("hpc_client", "hpc", True)]},
        {
            "group": "microblogging",
            "label": "M",
            "repos": [
                _repo("microblogging_client", "microblogging", True),
                _repo("microblogging_server", "microblogging", False),
            ],
        },
        {
            "group": "forum",
            "label": "F",
            "repos": [_repo("forum_client", "forum"), _repo("forum_server", "forum")],
        },
    ]
    entries = route_mod._plugin_entries(status)
    assert [e["key"] for e in entries] == ["hpc_client", "microblogging", "forum"]
    micro = entries[1]
    assert micro["paired"] and micro["label"] == "Microblogging"
    assert [m["key"] for m in micro["members"]] == [
        "microblogging_server",
        "microblogging_client",
    ]  # server first
    assert (
        micro["state"] == "partial"
        and entries[2]["state"] == "missing"
        and entries[0]["state"] == "installed"
    )


def test_the_list_and_detail_pages_render(core_app, monkeypatch):  # noqa: F811
    client = _client_as(core_app, "admin")
    resp = client.get("/admin/external_runtimes")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for key in ("microblogging", "forum"):
        assert f'data-entry-key="{key}"' in html
    for key in (
        "microblogging_client",
        "microblogging_server",
        "forum_client",
        "forum_server",
    ):
        assert f'data-entry-key="{key}"' not in html
    assert "Install" in html or "Update" in html

    def fake_status(key, github_token=None, include_remote_metadata=True):
        repo = _repo(key, "forum", installed=False)
        repo.update(
            github_repo="Org/" + key,
            repo_url="u",
            default_branch="main",
            current_branch=None,
            current_commit=None,
            ahead=None,
            behind=None,
            dependency_files_ready=False,
            validation_ready=False,
            available_branches=["main"],
            available_releases=[],
            latest_release_tag=None,
            releases_enabled=False,
            release_error=None,
        )
        return SimpleNamespace(to_dict=lambda: repo)

    monkeypatch.setattr(route_mod, "get_runtime_status", fake_status)
    monkeypatch.setattr(route_mod, "_runtime_group_active_experiments", lambda g: [])
    detail = client.get("/admin/external_runtimes/forum")
    assert detail.status_code == 200
    html = detail.get_data(as_text=True)
    assert (
        "forum_server" in html
        and "forum_client" in html
        and "/admin/external_runtimes/forum_server/sync" in html
        and "/admin/external_runtimes/forum_client/sync" in html
    )
    assert "Operation output" in html
    assert client.get("/admin/external_runtimes/no_such_plugin").status_code in (
        302,
        404,
    )


def _pair_calls(monkeypatch):
    calls = []

    def single(repo_key, action):
        calls.append((repo_key, action))
        return "ok"

    monkeypatch.setattr(route_mod, "_external_runtime_action_single", single)
    return calls


def test_install_update_and_remove_of_a_pair_run_server_then_client_and_remove_in_reverse(
    app, monkeypatch
):
    calls = _pair_calls(monkeypatch)
    with app.test_request_context("/x", method="POST"):
        route_mod.external_runtime_action.__wrapped__("forum", "sync")
        route_mod.external_runtime_action.__wrapped__("microblogging", "delete")
    assert calls == [
        ("forum_server", "sync"),
        ("forum_client", "sync"),
        ("microblogging_client", "delete"),
        ("microblogging_server", "delete"),
    ]


def test_a_failed_server_stops_the_pair(app, monkeypatch):
    from flask import flash

    calls = []

    def single(repo_key, action):
        calls.append(repo_key)
        flash("boom", "error")
        return "err"

    monkeypatch.setattr(route_mod, "_external_runtime_action_single", single)
    with app.test_request_context("/x", method="POST"):
        route_mod.external_runtime_action.__wrapped__("forum", "sync")
    assert calls == ["forum_server"]


def _single_env(monkeypatch, exists, git):
    class _Path:
        def exists(self):
            return exists

        def is_symlink(self):
            return False

        def __truediv__(self, other):
            return SimpleNamespace(exists=lambda: git)

    path = _Path()
    spec = SimpleNamespace(
        key="t", group="g", group_label="G", label="T", default_branch="main", path=path
    )
    done = []
    monkeypatch.setattr(
        route_mod, "_require_admin_user", lambda: SimpleNamespace(username="admin")
    )
    monkeypatch.setattr(route_mod, "runtime_spec", lambda k: spec)
    monkeypatch.setattr(route_mod, "runtime_visible_to_user", lambda s, u: True)
    monkeypatch.setattr(route_mod, "_runtime_group_active_experiments", lambda g: [])
    monkeypatch.setattr(route_mod, "host_git_available", lambda: True)
    monkeypatch.setattr(route_mod, "_run_suite_schema_migration", lambda k: None)
    monkeypatch.setattr(route_mod, "log_external_runtime_action", lambda *a, **k: None)
    for name in (
        "download_runtime_release",
        "clone_runtime_repo",
        "update_runtime_repo",
        "delete_runtime_repo",
    ):
        monkeypatch.setattr(route_mod, name, lambda *a, _n=name, **k: done.append(_n))
    monkeypatch.setattr(
        route_mod, "install_runtime_dependencies", lambda *a: done.append("deps")
    )
    monkeypatch.setattr(
        route_mod, "validate_runtime_repo", lambda *a: done.append("validate")
    )
    return done


def _sync(app, source):
    with app.test_request_context(
        "/x",
        method="POST",
        data={"install_source": source, "branch": "main"},
        headers={"Accept": "application/json"},
    ):
        return route_mod._external_runtime_action_single("t", "sync")


def test_sync_installs_when_missing_updates_a_git_checkout_and_replaces_otherwise(
    app, monkeypatch
):
    done = _single_env(monkeypatch, exists=False, git=False)
    _sync(app, "release")
    assert done == ["download_runtime_release", "deps", "validate"]

    done = _single_env(monkeypatch, exists=True, git=True)
    _sync(app, "git")
    assert done == ["update_runtime_repo", "deps", "validate"]

    done = _single_env(
        monkeypatch, exists=True, git=False
    )  # installed from a release, release chosen again
    _sync(app, "release")
    assert done == [
        "delete_runtime_repo",
        "download_runtime_release",
        "deps",
        "validate",
    ]


def test_the_plugin_pages_load_their_guided_tours(core_app, monkeypatch):  # noqa: F811
    client = _client_as(core_app, "admin")
    assert "external-runtimes-tutorial.js" in client.get(
        "/admin/external_runtimes"
    ).get_data(as_text=True)
    monkeypatch.setattr(
        route_mod,
        "get_runtime_status",
        lambda key, **kw: SimpleNamespace(
            to_dict=lambda: {
                **_repo(key, "forum"),
                "github_repo": "o/" + key,
                "repo_url": "u",
                "default_branch": "main",
                "current_branch": None,
                "current_commit": None,
                "ahead": None,
                "behind": None,
                "dependency_files_ready": False,
                "validation_ready": False,
                "available_branches": ["main"],
                "available_releases": [],
                "latest_release_tag": None,
                "releases_enabled": False,
                "release_error": None,
            }
        ),
    )
    monkeypatch.setattr(route_mod, "_runtime_group_active_experiments", lambda g: [])
    html = client.get("/admin/external_runtimes/forum").get_data(as_text=True)
    assert "external-runtime-detail-tutorial.js" in html
    js = (_STATIC / "external-runtime-detail-tutorial.js").open().read()
    for selector in (
        "#external-runtime-detail",
        ".ext-members",
        ".ext-options",
        "#external-runtime-output",
    ):
        assert selector.lstrip("#.") in html, selector
        assert selector in js
    nav = (_STATIC / "admin-nav.js").open().read()
    assert "startPluginTutorial" in nav and "startExternalRuntimeDetailTutorial" in nav
