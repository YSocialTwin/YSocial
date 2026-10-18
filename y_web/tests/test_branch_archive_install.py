import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.src.external_runtime import manager

pytestmark = pytest.mark.unit


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr("owner-repo-abc123/" + name, content)
    return buf.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    spec = SimpleNamespace(
        key="demo",
        label="Demo",
        github_repo="o/r",
        repo_url="https://github.com/o/r.git",
        path=tmp_path / "external" / "Demo",
        default_branch="main",
        group="g",
        group_label="G",
        category="c",
        category_label="C",
        is_private=False,
        validate_entrypoints=(),
        validate_import=None,
        install_commands=(),
    )
    state = {"sha": "a" * 40, "zip": _zip({"app.py": "v1"}), "downloads": 0}
    monkeypatch.setattr(manager, "runtime_spec", lambda key: spec)
    monkeypatch.setattr(manager, "log_external_runtime_action", lambda *a, **k: None)
    monkeypatch.setattr(
        manager,
        "_remote_branch_head",
        lambda spec_, branch, token=None: (state["sha"], None),
    )

    def fake_download(spec_, branch, token=None):
        state["downloads"] += 1
        return state["zip"]

    monkeypatch.setattr(manager, "_download_branch_archive", fake_download)
    return spec, state


def test_install_writes_marker_and_files(env):
    spec, state = env
    manager.install_runtime_branch_archive("demo", "dev", "me")
    assert (spec.path / "app.py").read_text() == "v1"
    marker = manager._read_archive_marker(spec.path)
    assert marker["branch"] == "dev" and marker["commit"] == "a" * 40
    assert manager.is_archive_install("demo")


def test_update_is_noop_when_head_unchanged(env):
    spec, state = env
    manager.install_runtime_branch_archive("demo", "main", "me")
    assert manager.update_runtime_branch_archive("demo", None, "me") is False
    assert state["downloads"] == 1


def test_update_replaces_directory_when_head_moves(env):
    spec, state = env
    manager.install_runtime_branch_archive("demo", "main", "me")
    (spec.path / "local_edit.txt").write_text("discarded")
    state["sha"] = "b" * 40
    state["zip"] = _zip({"app.py": "v2"})
    assert manager.update_runtime_branch_archive("demo", None, "me") is True
    assert (spec.path / "app.py").read_text() == "v2"
    assert not (spec.path / "local_edit.txt").exists()
    assert manager._read_archive_marker(spec.path)["commit"] == "b" * 40
    assert not spec.path.with_name("Demo.old").exists()
    assert not spec.path.with_name("Demo.new").exists()


def test_update_keeps_old_copy_if_download_fails(env, monkeypatch):
    spec, state = env
    manager.install_runtime_branch_archive("demo", "main", "me")
    state["sha"] = "c" * 40

    def boom(*a, **k):
        raise manager.ExternalRuntimeError("network down")

    monkeypatch.setattr(manager, "_download_branch_archive", boom)
    with pytest.raises(manager.ExternalRuntimeError):
        manager.update_runtime_branch_archive("demo", None, "me")
    assert (spec.path / "app.py").read_text() == "v1"


def test_update_runtime_repo_uses_archive_path_without_git(env, monkeypatch):
    spec, state = env
    manager.install_runtime_branch_archive("demo", "main", "me")
    monkeypatch.setattr(manager, "host_git_available", lambda: False)
    state["sha"] = "d" * 40
    state["zip"] = _zip({"app.py": "v3"})
    manager.update_runtime_repo("demo", None, "me")
    assert (spec.path / "app.py").read_text() == "v3"


def test_status_reports_archive_install_and_update_available(env, monkeypatch):
    spec, state = env
    manager.install_runtime_branch_archive("demo", "main", "me")
    state["sha"] = "e" * 40
    monkeypatch.setattr(manager, "_list_releases", lambda *a, **k: ([], None))
    monkeypatch.setattr(
        manager, "_branch_list_for_repo", lambda *a, **k: (["main", "dev"], None)
    )
    monkeypatch.setattr(manager, "_dependency_files_ready", lambda s: True)
    monkeypatch.setattr(manager, "_validate_prereqs", lambda s: True)
    status = manager.get_runtime_status("demo")
    assert status.archive_managed and not status.git_managed
    assert status.current_branch == "main" and status.current_commit == "a" * 7
    assert status.update_available is True


def test_macos_git_shim_is_not_git(monkeypatch):
    monkeypatch.setattr(manager.shutil, "which", lambda name: "/usr/bin/git")
    monkeypatch.setattr(manager.sys, "platform", "darwin")

    class R:
        returncode = 2

    monkeypatch.setattr(manager.subprocess, "run", lambda *a, **k: R())
    assert manager.host_git_available() is False
