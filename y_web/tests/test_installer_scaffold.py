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
    for cmd in ("default_home", "is_installed", "install", "launch", "is_running", "stop", "load_settings", "save_settings"):
        assert f'"{cmd}"' in js
        assert f"fn {cmd}" in (I / "src-tauri/src/main.rs").read_text()


def test_stop_button_and_pid_file_wiring():
    html = (I / "ui/index.html").read_text()
    assert 'id="stop"' in html
    rs = (I / "src-tauri/src/main.rs").read_text()
    assert "ysocial.pid" in rs and "            stop,\n" in rs


def test_ysocial_exits_cleanly_on_sigterm():
    main = (I.parent / "y_social.py").read_text()
    assert "signal.SIGTERM" in main


def test_advanced_options_cover_cli_flags():
    import re

    main = (I.parent / "y_social.py").read_text()
    cli = set(re.findall(r'"--([a-z_-]+)"', main))
    rs = (I / "src-tauri/src/main.rs").read_text()
    # every flag of the command line (except help) is reachable from the launcher
    for flag in cli - {"help"}:
        assert f'"--{flag}"' in rs, flag
    html = (I / "ui/index.html").read_text()
    for field in ("host", "port", "db", "llm", "extra", "debug", "nonotebook", "development", "appwindow"):
        assert f'id="{field}"' in html


def test_app_window_blocks_external_navigation():
    rs = (I / "src-tauri/src/main.rs").read_text()
    assert "WebviewWindowBuilder" in rs and "on_new_window" in rs
    # no on_navigation: it also fires for iframes (e.g. js.stripe.com) and broke pages
    assert ".on_navigation(" not in rs
    # the remote page gets no IPC: capabilities stay limited to the installer window
    cap = json.loads((I / "src-tauri/capabilities/default.json").read_text())
    assert cap["windows"] == ["main"]


def test_launcher_reuses_login_look_and_assets_are_in_sync():
    import sys

    root = I.parent
    sys.path.insert(0, str(root / "scripts/packaging"))
    try:
        import sync_installer_assets as sia
    finally:
        sys.path.pop(0)
    for src, name in sia.FILES.items():
        assert (root / src).read_bytes() == (I / "ui/assets" / name).read_bytes(), f"run sync_installer_assets.py ({name})"
    html = (I / "ui/index.html").read_text()
    for needle in ("login-scene.css", "yl-card", "yl-aurora", "yl-net", 'id="v-setup"', 'id="v-installing"', 'id="v-ready"'):
        assert needle in html
    # every local resource referenced by the page exists
    for ref in re.findall(r'(?:src|href)="([^":]+)"', html):
        assert (I / "ui" / ref).exists(), ref
