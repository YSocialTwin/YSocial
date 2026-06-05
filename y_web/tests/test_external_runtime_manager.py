from __future__ import annotations

import io
import json
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
        category="simulation_runtimes",
        category_label="Simulation Runtimes",
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


def test_runtime_status_lists_remote_branches_before_clone(
    runtime_repo_spec, monkeypatch
):
    monkeypatch.setattr(
        manager,
        "_list_remote_branches",
        lambda spec, github_token=None: (["main", "develop", "release"], None),
    )

    status = manager.get_runtime_status(runtime_repo_spec.key)

    assert status.installed is False
    assert status.available_branches == ["develop", "main", "release"]


def test_update_runtime_repo_switches_branch(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "develop", actor="tester")

    manager.update_runtime_repo(runtime_repo_spec.key, "main", actor="tester")
    status = manager.get_runtime_status(runtime_repo_spec.key)
    assert status.current_branch == "main"


def test_fetch_then_update_can_target_remote_only_branch(runtime_repo_spec):
    manager.clone_runtime_repo(runtime_repo_spec.key, "main", actor="tester")

    work = runtime_repo_spec.path.parent.parent / "work"
    subprocess.run(["git", "-C", str(work), "checkout", "-b", "feature-x"], check=True)
    (work / "testruntime" / "__init__.py").write_text("VALUE = 3\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-m", "feature branch"], check=True
    )
    subprocess.run(
        ["git", "-C", str(work), "push", "-u", "origin", "feature-x"], check=True
    )

    manager.fetch_runtime_repo(runtime_repo_spec.key, "feature-x", actor="tester")
    manager.update_runtime_repo(runtime_repo_spec.key, "feature-x", actor="tester")

    status = manager.get_runtime_status(runtime_repo_spec.key)
    assert status.current_branch == "feature-x"


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
        category="agent_extensions",
        category_label="Agent Extensions",
        label="PrivateRuntime",
        path=Path("/tmp/private-runtime"),
        github_repo="YSocialTwin/PrivateRuntime",
        repo_url="https://github.com/YSocialTwin/PrivateRuntime.git",
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


def test_grouped_runtime_specs_include_agent_plugins():
    grouped = registry.grouped_runtime_specs()
    group_keys = [group_key for group_key, _, _ in grouped]
    assert "agent_plugins" in group_keys

    plugin_spec = registry.runtime_spec("agent_plugins")
    assert plugin_spec.github_repo == "YSocialTwin/y_agents_plugins"
    assert plugin_spec.category == "agent_extensions"


def test_install_runtime_dependencies_detects_pyproject_layout(
    runtime_repo_spec, monkeypatch
):
    runtime_repo_spec.path.mkdir(parents=True)
    (runtime_repo_spec.path / "pyproject.toml").write_text(
        "[build-system]\nrequires = []\n", encoding="utf-8"
    )
    runtime_repo_spec = registry.ExternalRuntimeSpec(
        key=runtime_repo_spec.key,
        group=runtime_repo_spec.group,
        group_label=runtime_repo_spec.group_label,
        category=runtime_repo_spec.category,
        category_label=runtime_repo_spec.category_label,
        label=runtime_repo_spec.label,
        path=runtime_repo_spec.path,
        github_repo=runtime_repo_spec.github_repo,
        repo_url=runtime_repo_spec.repo_url,
        default_branch=runtime_repo_spec.default_branch,
        install_commands=(),
        validate_entrypoints=(),
        validate_import=None,
    )
    monkeypatch.setitem(
        registry.SUPPORTED_EXTERNAL_REPOS, runtime_repo_spec.key, runtime_repo_spec
    )
    monkeypatch.setattr(
        manager,
        "get_runtime_status",
        lambda repo_key, github_token=None: manager.RuntimeStatus(
            key=runtime_repo_spec.key,
            label=runtime_repo_spec.label,
            group=runtime_repo_spec.group,
            group_label=runtime_repo_spec.group_label,
            category=runtime_repo_spec.category,
            category_label=runtime_repo_spec.category_label,
            path=str(runtime_repo_spec.path),
            repo_url=runtime_repo_spec.repo_url,
            github_repo=runtime_repo_spec.github_repo,
            default_branch=runtime_repo_spec.default_branch,
            installed=True,
            exists=True,
            git_managed=False,
            is_symlink=False,
            current_branch=None,
            current_commit=None,
            tracking_branch=None,
            ahead=None,
            behind=None,
            dirty=False,
            dependency_files_ready=True,
            validation_ready=True,
            available_branches=[runtime_repo_spec.default_branch],
            available_releases=[],
            latest_release_tag=None,
            releases_enabled=False,
            release_error=None,
            path_kind="directory",
            python_executable=manager.sys.executable,
            is_private=False,
        ),
    )

    commands = []

    def fake_run(command, cwd, env=None, timeout=300):
        commands.append(command)
        return "ok"

    monkeypatch.setattr(manager, "_run_command", fake_run)
    manager.install_runtime_dependencies(runtime_repo_spec.key, actor="tester")

    assert commands == [[manager.sys.executable, "-m", "pip", "install", "-e", "."]]


def test_load_plugins_index_rebuilds_external_plugins_json(tmp_path, monkeypatch):
    external_dir = tmp_path / "external"
    meta_dir = external_dir / "sample_plugin" / "meta"
    meta_dir.mkdir(parents=True)
    info_payload = {
        "plugin_name": "Sample Plugin",
        "category": "Agent Extensions",
        "group": "Moderation",
        "description": "Example plugin metadata.",
        "authors": ["Example Org"],
        "repository_url": "https://github.com/example/sample_plugin",
    }
    (meta_dir / "info.json").write_text(json.dumps(info_payload), encoding="utf-8")

    monkeypatch.setattr(registry, "EXTERNAL_DIR", external_dir)
    monkeypatch.setattr(registry, "PLUGINS_INDEX_PATH", external_dir / "plugins.json")

    plugins = registry.load_plugins_index(refresh=True)

    assert plugins == [info_payload]
    saved_payload = json.loads(
        (external_dir / "plugins.json").read_text(encoding="utf-8")
    )
    assert saved_payload == {"plugins": [info_payload]}


def test_plugin_metadata_for_runtime_matches_repository_url(tmp_path, monkeypatch):
    external_dir = tmp_path / "external"
    monkeypatch.setattr(registry, "EXTERNAL_DIR", external_dir)
    monkeypatch.setattr(registry, "PLUGINS_INDEX_PATH", external_dir / "plugins.json")

    plugin_info = {
        "plugin_name": "Sample Plugin",
        "category": "Agent Extensions",
        "group": "Moderation",
        "description": "Example plugin metadata.",
        "authors": ["Example Org"],
        "repository_url": "https://github.com/example/sample_plugin",
    }
    spec = registry.ExternalRuntimeSpec(
        key="sample_plugin",
        group="agent_plugins",
        group_label="Agent Plugins",
        category="agent_extensions",
        category_label="Agent Extensions",
        label="sample_plugin",
        path=external_dir / "sample_plugin",
        github_repo="example/sample_plugin",
        repo_url="https://github.com/example/sample_plugin.git",
        default_branch="main",
        install_commands=(),
        validate_entrypoints=(),
    )

    assert registry.plugin_metadata_for_runtime(spec, [plugin_info]) == plugin_info


def test_load_plugins_index_detects_legacy_agent_plugin_layout(tmp_path, monkeypatch):
    external_dir = tmp_path / "external"
    legacy_dir = external_dir / "y_agents_plugins" / "plugins_exposed"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "agent_types.json").write_text(
        json.dumps(
            {
                "agent_types": [
                    {
                        "agent_type": "hello_world",
                        "display_name": "Hello World Agent",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(registry, "EXTERNAL_DIR", external_dir)
    monkeypatch.setattr(registry, "PLUGINS_INDEX_PATH", external_dir / "plugins.json")

    plugins = registry.load_plugins_index(refresh=True)

    assert any(plugin["plugin_name"] == "y_agents_plugins" for plugin in plugins)
