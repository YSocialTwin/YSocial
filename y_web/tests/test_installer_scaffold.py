import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

I = Path(__file__).resolve().parents[2] / "installer"


def test_tauri_config_is_valid_json_and_points_to_ui():
    cfg = json.loads((I / "src-tauri/tauri.conf.json").read_text())
    assert cfg["build"]["frontendDist"] == "../ui"
    assert (I / "ui/index.html").exists()
    json.loads((I / "src-tauri/capabilities/default.json").read_text())


def test_installer_python_version_matches_package():
    rs = (I / "src-tauri/src/main.rs").read_text()
    assert 'PYTHON_VERSION: &str = "3.12"' in rs
    boot = Path(I.parent / "scripts/packaging/bootstrap_env.py").read_text()
    assert 'PYTHON_VERSION = "3.12"' in boot


def test_default_home_matches_path_utils():
    rs = (I / "src-tauri/src/main.rs").read_text()
    pu = (I.parent / "y_web/src/system/path_utils.py").read_text()
    assert "Library/Application Support/YSocial" in rs
    assert '"Library" / "Application Support" / "YSocial"' in pu
    assert "AppData/Local/YSocial" in rs
    assert '"AppData" / "Local" / "YSocial"' in pu
    assert '".ysocial"' in rs and '".ysocial"' in pu


def test_ui_exposes_toxicity_choice_with_clear_text():
    html = (I / "ui/index.html").read_text()
    assert 'id="toxicity"' in html
    assert re.search(r"large download", html)
    js = (I / "ui/main.js").read_text()
    for cmd in ("default_home", "is_installed", "install", "launch"):
        assert f'"{cmd}"' in js
        assert f"fn {cmd}" in (I / "src-tauri/src/main.rs").read_text()
