import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/packaging/set_version.py"


def _copy_repo_bits(tmp_path):
    for rel in (
        "VERSION",
        "installer/src-tauri/tauri.conf.json",
        "installer/src-tauri/Cargo.toml",
        "installer/src-tauri/Cargo.lock",
    ):
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dest)


def test_tag_is_stamped_everywhere(tmp_path):
    _copy_repo_bits(tmp_path)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "v9.8.7", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and r.stdout.strip() == "9.8.7"
    assert (tmp_path / "VERSION").read_text().strip() == "9.8.7"
    conf = json.loads((tmp_path / "installer/src-tauri/tauri.conf.json").read_text())
    assert conf["version"] == "9.8.7"
    assert (
        'version = "9.8.7"' in (tmp_path / "installer/src-tauri/Cargo.toml").read_text()
    )
    lock = (tmp_path / "installer/src-tauri/Cargo.lock").read_text()
    assert 'name = "ysocial-installer"\nversion = "9.8.7"' in lock


def test_prerelease_and_bad_versions(tmp_path):
    _copy_repo_bits(tmp_path)
    ok = subprocess.run(
        [sys.executable, str(SCRIPT), "v4.1.0-rc1", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0 and ok.stdout.strip() == "4.1.0-rc1"
    for bad in ("latest", "v4.1", "4.1.0.1", "v4.1.0; rm -rf /"):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), bad, "--root", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 1, bad


def test_other_cargo_versions_untouched(tmp_path):
    _copy_repo_bits(tmp_path)
    before = (
        (tmp_path / "installer/src-tauri/Cargo.lock").read_text().count('version = "')
    )
    subprocess.run(
        [sys.executable, str(SCRIPT), "5.0.0", "--root", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    after = (tmp_path / "installer/src-tauri/Cargo.lock").read_text()
    assert after.count('version = "') == before
    assert after.count('version = "5.0.0"') == 1
