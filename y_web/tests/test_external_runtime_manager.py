from __future__ import annotations

import subprocess
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
    subprocess.run(["git", "-C", str(work), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "Test User"], check=True)

    pkg = work / "testruntime"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (work / "requirements.txt").write_text("\n", encoding="utf-8")
    (work / "run_server.py").write_text("print('server')\n", encoding="utf-8")
    (work / "run_client.py").write_text("print('client')\n", encoding="utf-8")

    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-m", "initial"], check=True)
    subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(work), "push", "-u", "origin", "main"], check=True)

    subprocess.run(["git", "-C", str(work), "checkout", "-b", "develop"], check=True)
    (pkg / "__init__.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-m", "develop"], check=True)
    subprocess.run(["git", "-C", str(work), "push", "-u", "origin", "develop"], check=True)

    spec = registry.ExternalRuntimeSpec(
        key="test_runtime",
        group="hpc",
        group_label="HPC",
        label="TestRuntime",
        path=clone_target,
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
    assert status.current_branch == "develop"
    assert "develop" in status.available_branches
    assert "main" in status.available_branches


def test_update_runtime_repo_switches_branch(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "develop", actor="tester")

    manager.update_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    status = manager.get_runtime_status(runtime_repo_spec.key)
    assert status.current_branch == "main"


def test_update_runtime_repo_rejects_dirty_worktree(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    (runtime_repo_spec.path / "testruntime" / "__init__.py").write_text("VALUE = 99\n", encoding="utf-8")

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
