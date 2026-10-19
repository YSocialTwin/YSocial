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
