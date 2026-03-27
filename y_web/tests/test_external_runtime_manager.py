from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from y_web.src.external_runtime import manager, registry


@pytest.fixture()
def runtime_repo_spec(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    clone_target = tmp_path / "external" / "TestRuntime"
    log_file = tmp_path / "runtime.log"

    subprocess.run(["git", "init", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True)
    subprocess.run(
        ["git", "-C", str(work), "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(
        ["git", "-C", str(work), "config", "user.name", "Test User"], check=True
    )

    pkg = work / "testruntime"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (work / "requirements.txt").write_text("\n", encoding="utf-8")
    (work / "run_server.py").write_text("print('server')\n", encoding="utf-8")
    (work / "run_client.py").write_text("print('client')\n", encoding="utf-8")

    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-m", "initial"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "remote", "add", "origin", str(remote)], check=True
    )
    subprocess.run(["git", "-C", str(work), "push", "-u", "origin", "main"], check=True)

    subprocess.run(["git", "-C", str(work), "checkout", "-b", "develop"], check=True)
    (pkg / "__init__.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-m", "develop"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "push", "-u", "origin", "develop"], check=True
    )

    spec = registry.ExternalRuntimeSpec(
        key="test_runtime",
        group="hpc",
        group_label="HPC",
        label="TestRuntime",
        path=clone_target,
        github_repo="YSocialTwin/TestRuntime",
        repo_url=str(remote),
        default_branch="main",
        install_commands=(("python", "-c", "print('install ok')"),),
        validate_entrypoints=("testruntime", "requirements.txt"),
        validate_import="testruntime",
    )

    monkeypatch.setitem(registry.SUPPORTED_EXTERNAL_REPOS, spec.key, spec)
    monkeypatch.setattr(manager, "LOG_FILE", log_file)
    monkeypatch.setattr(manager, "LOG_DIR", log_file.parent)
    yield spec
    registry.SUPPORTED_EXTERNAL_REPOS.pop(spec.key, None)


def test_clone_runtime_repo_uses_selected_branch(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "develop", actor="tester")

    status = manager.get_runtime_status(runtime_repo_spec.key)
    assert status.installed is True
    assert status.git_managed is True
    assert status.current_branch == "develop"
    assert "develop" in status.available_branches
    assert "main" in status.available_branches


def test_update_runtime_repo_switches_branch(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "develop", actor="tester")

    manager.update_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    status = manager.get_runtime_status(runtime_repo_spec.key)
    assert status.current_branch == "main"


def test_fetch_runtime_repo_normalizes_origin_remote(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    subprocess.run(
        [
            "git",
            "-C",
            str(runtime_repo_spec.path),
            "remote",
            "set-url",
            "origin",
            "https://github.com/example/legacy.git",
        ],
        check=True,
    )

    manager.fetch_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    current_origin = subprocess.check_output(
        ["git", "-C", str(runtime_repo_spec.path), "remote", "get-url", "origin"],
        text=True,
    ).strip()
    assert current_origin == runtime_repo_spec.repo_url


def test_update_runtime_repo_rejects_dirty_worktree(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    (runtime_repo_spec.path / "testruntime" / "__init__.py").write_text(
        "VALUE = 99\n", encoding="utf-8"
    )

    with pytest.raises(manager.ExternalRuntimeError, match="local modifications"):
        manager.update_runtime_repo(runtime_repo_spec.key, "main", actor="tester")


def test_validate_runtime_repo_imports_package(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    output = manager.validate_runtime_repo(runtime_repo_spec.key, actor="tester")

    assert "Required files present" in output
    assert "Imported testruntime" in output


def test_delete_runtime_repo_removes_clone(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    assert runtime_repo_spec.path.exists()

    manager.delete_runtime_repo(runtime_repo_spec.key, actor="tester")
    assert not runtime_repo_spec.path.exists()


def test_download_runtime_release_installs_non_git_runtime(
    runtime_repo_spec, monkeypatch
):
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("repo-release/testruntime/__init__.py", "VALUE = 3\n")
        archive.writestr("repo-release/requirements.txt", "\n")
        archive.writestr("repo-release/run_server.py", "print('server')\n")
        archive.writestr("repo-release/run_client.py", "print('client')\n")

    monkeypatch.setattr(
        manager,
        "_list_releases",
        lambda spec, github_token=None: (
            [
                {
                    "tag": "v1.0.0",
                    "name": "v1.0.0",
                    "zipball_url": "https://example.test/archive.zip",
                }
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        manager,
        "_download_release_archive",
        lambda spec, release, github_token=None: archive_buffer.getvalue(),
    )

    manager.download_runtime_release(runtime_repo_spec.key, "v1.0.0", actor="tester")
    status = manager.get_runtime_status(runtime_repo_spec.key)

    assert status.installed is True
    assert status.git_managed is False
    assert status.validation_ready is True
    assert (runtime_repo_spec.path / "testruntime" / "__init__.py").exists()


def test_update_runtime_repo_rejects_release_archive_install(
    runtime_repo_spec, monkeypatch
):
    runtime_repo_spec.path.mkdir(parents=True)
    (runtime_repo_spec.path / "testruntime").mkdir()
    (runtime_repo_spec.path / "testruntime" / "__init__.py").write_text(
        "VALUE = 4\n", encoding="utf-8"
    )
    (runtime_repo_spec.path / "requirements.txt").write_text("\n", encoding="utf-8")

    with pytest.raises(manager.ExternalRuntimeError, match="release archive"):
        manager.update_runtime_repo(runtime_repo_spec.key, "main", actor="tester")


def test_runtime_visibility_respects_private_allowlist(monkeypatch):
    spec = registry.ExternalRuntimeSpec(
        key="private_runtime",
        group="hpc",
        group_label="HPC",
        label="PrivateRuntime",
        path=Path("/tmp/private-runtime"),
        github_repo="YSocialTwin/PrivateRuntime",
        repo_url="git@github.com:YSocialTwin/PrivateRuntime.git",
        default_branch="main",
        install_commands=(),
        validate_entrypoints=(),
        is_private=True,
        visible_to_usernames=("alice",),
    )

    class User:
        def __init__(self, username, role):
            self.username = username
            self.role = role

    assert registry.runtime_visible_to_user(spec, User("alice", "admin")) is True
    assert registry.runtime_visible_to_user(spec, User("bob", "admin")) is False
