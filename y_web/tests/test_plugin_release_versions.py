import json

from y_web.src.external_runtime import manager, registry


def _fake_release_install(tmp_path, monkeypatch, tag_marker=None, logged=None):
    import dataclasses

    spec = registry.SUPPORTED_EXTERNAL_REPOS["microblogging_server"]
    new = dataclasses.replace(spec, path=tmp_path / "plugin")
    (tmp_path / "plugin").mkdir()
    monkeypatch.setitem(registry.SUPPORTED_EXTERNAL_REPOS, spec.key, new)
    if tag_marker:
        (tmp_path / "plugin" / manager.RELEASE_MARKER).write_text(
            json.dumps({"source": "release", "tag": tag_marker})
        )
    monkeypatch.setattr(
        manager,
        "read_external_runtime_logs",
        lambda limit=200, repo_key=None: (
            [{"success": True, "action": "download_release", "branch": logged}]
            if logged
            else []
        ),
    )
    return new


def test_release_install_shows_version_and_update(tmp_path, monkeypatch):
    spec = _fake_release_install(tmp_path, monkeypatch, tag_marker="v1.0.0")
    monkeypatch.setattr(
        manager,
        "_list_releases",
        lambda s, github_token=None: ([{"tag": "v1.1.0"}, {"tag": "v1.0.0"}], None),
    )
    st = manager.get_runtime_status(
        spec.key, include_remote_metadata=False, check_release_update=True
    )
    assert st.release_managed and st.installed_release_tag == "v1.0.0"
    assert st.latest_release_tag == "v1.1.0" and st.release_update_available is True


def test_up_to_date_and_log_fallback(tmp_path, monkeypatch):
    spec = _fake_release_install(tmp_path, monkeypatch, logged="v2.0.0")
    monkeypatch.setattr(
        manager,
        "_list_releases",
        lambda s, github_token=None: ([{"tag": "v2.0.0"}], None),
    )
    st = manager.get_runtime_status(
        spec.key, include_remote_metadata=False, check_release_update=True
    )
    assert st.installed_release_tag == "v2.0.0"
    assert st.release_update_available is False


def test_git_or_archive_installs_have_no_release_version(tmp_path, monkeypatch):
    spec = _fake_release_install(tmp_path, monkeypatch, tag_marker="v1.0.0")
    (tmp_path / "plugin" / ".git").mkdir()
    monkeypatch.setattr(manager, "_is_git_worktree", lambda p: True)
    st = manager.get_runtime_status(
        spec.key, include_remote_metadata=False, check_release_update=True
    )
    assert not st.release_managed and st.release_update_available is None


def test_list_view_skips_lookup_without_flag(tmp_path, monkeypatch):
    spec = _fake_release_install(tmp_path, monkeypatch, tag_marker="v1.0.0")

    def boom(*a, **k):
        raise AssertionError("no network in plain list view")

    monkeypatch.setattr(manager, "_list_releases", boom)
    st = manager.get_runtime_status(spec.key, include_remote_metadata=False)
    assert st.installed_release_tag == "v1.0.0" and st.release_update_available is None


def test_release_is_newer_compares_numbers_not_text():
    from y_web.src.external_runtime.manager import release_is_newer

    assert release_is_newer("v2.1.1", "v2.1.0")
    assert release_is_newer("v2.10.0", "v2.9.0")
    assert release_is_newer("v1.1", "v1.0.9")
    assert not release_is_newer("v2.1.0", "v2.1.0")
    assert not release_is_newer("2.1.0", "v2.1.0")
    assert not release_is_newer("v2.0.0", "v2.1.0")
    assert not release_is_newer(None, "v1.0.0") and not release_is_newer("v1.0.0", None)
    assert release_is_newer("nightly-2", "nightly-1")


def test_list_entry_ignores_a_stale_update_flag_for_equal_versions():
    from y_web.routes.admin.sub.experiments._external_runtimes import _make_entry

    repo = {
        "key": "ysimulator_test",
        "label": "X",
        "installed": True,
        "release_managed": True,
        "installed_release_tag": "v2.1.0",
        "latest_release_tag": "v2.1.0",
        "release_update_available": True,  # what an older build would have reported
    }
    versions = _make_entry("ysimulator_test", [repo])["versions"]
    assert versions and versions[0]["update"] is False
    repo.update(latest_release_tag="v2.2.0")
    assert _make_entry("ysimulator_test", [repo])["versions"][0]["update"] is True
