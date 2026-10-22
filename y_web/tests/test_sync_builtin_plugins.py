"""The packaged built-in plugin list is a generated copy of the plugin registry's."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "packaging" / "sync_builtin_plugins.py"
spec = importlib.util.spec_from_file_location("sync_builtin_plugins", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def _git(path, *args):
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def _registry(tmp_path, plugins=None):
    repo = tmp_path / "registry"
    repo.mkdir()
    plugins = plugins or [
        {
            "key": "demo_plugin",
            "label": "Demo",
            "group": "g",
            "group_label": "G",
            "category": "c",
            "category_label": "C",
            "directory": "Demo",
            "repo": "o/Demo",
        }
    ]
    (repo / "builtin.json").write_text(
        json.dumps({"schema_version": 1, "plugins": plugins}), encoding="utf-8"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", "builtin.json")
    _git(repo, "commit", "-q", "-m", "x")
    return repo


@pytest.fixture
def target(tmp_path, monkeypatch):
    path = tmp_path / "builtin_plugins.json"
    monkeypatch.setattr(sync, "TARGET", path)
    return path


def test_packaged_copy_matches_its_recorded_hash():
    assert sync.verify() == []


def test_packaged_copy_records_where_it_comes_from():
    generated = sync.current()["_generated"]
    assert generated["source"] == "YSocialTwin/plugin-registry/builtin.json"
    assert len(generated["commit"]) == 40 and len(generated["sha256"]) == 64
    assert "Do not edit" in generated["note"]


def test_sync_from_a_checkout_records_commit_and_hash(tmp_path, target):
    repo = _registry(tmp_path)
    assert sync.main(["--source", str(repo)]) == 0
    doc = json.loads(target.read_text(encoding="utf-8"))
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    assert doc["_generated"]["commit"] == head
    assert doc["_generated"]["sha256"] == sync.plugins_hash(doc["plugins"])
    assert [p["key"] for p in doc["plugins"]] == ["demo_plugin"]
    assert sync.verify() == []


def test_hand_edits_are_detected(tmp_path, target):
    sync.main(["--source", str(_registry(tmp_path))])
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["plugins"][0]["repo"] = "attacker/Demo"
    target.write_text(json.dumps(doc), encoding="utf-8")
    assert any("edited by hand" in p for p in sync.verify())
    assert sync.main(["--verify"]) == 1


def test_missing_generation_header_is_reported(target):
    target.write_text(json.dumps({"schema_version": 1, "plugins": []}), "utf-8")
    assert sync.verify()


def test_uncommitted_registry_changes_are_refused(tmp_path, target):
    repo = _registry(tmp_path)
    (repo / "builtin.json").write_text("{}", encoding="utf-8")
    assert sync.main(["--source", str(repo)]) == 1
    assert not target.exists()


def test_duplicate_keys_are_refused(tmp_path, target):
    plugin = {"key": "dup_plugin"}
    repo = _registry(tmp_path, [plugin, dict(plugin)])
    assert sync.main(["--source", str(repo)]) == 1


def test_check_reports_drift_and_accepts_a_match(tmp_path, target, monkeypatch):
    repo = _registry(tmp_path)
    sync.main(["--source", str(repo)])
    payload, commit = sync.from_checkout(repo)
    monkeypatch.setattr(sync, "from_github", lambda ref: (payload, commit))
    assert sync.main(["--check"]) == 0
    assert sync.main(["--check-latest"]) == 0
    payload["plugins"][0]["label"] = "Changed upstream"
    assert sync.main(["--check-latest"]) == 1


def test_check_latest_ignores_registry_commits_that_do_not_touch_the_list(
    tmp_path, target, monkeypatch
):
    repo = _registry(tmp_path)
    sync.main(["--source", str(repo)])
    payload, commit = sync.from_checkout(repo)
    # a later registry commit (README, banner...): new sha, same plugin list
    newer = "f" * 40
    monkeypatch.setattr(sync, "from_github", lambda ref: (payload, newer))
    assert sync.main(["--check-latest"]) == 0
    # --check still pins the recorded commit exactly
    assert commit != newer
    # a real change of the list, or a hand-edited copy, still fails the gate
    changed = json.loads(json.dumps(payload))
    changed["plugins"][0]["description"] = "Different"
    monkeypatch.setattr(sync, "from_github", lambda ref: (changed, newer))
    assert sync.main(["--check-latest"]) == 1


def test_release_workflow_gates_on_the_sync_check():
    workflow = (ROOT / ".github/workflows/release-packaging.yml").read_text("utf-8")
    assert "sync_builtin_plugins.py --verify" in workflow
    assert "sync_builtin_plugins.py --check-latest" in workflow
