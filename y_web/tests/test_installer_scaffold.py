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
    # toxicity is offered only after the base install (never in the setup view), with a clear warning
    setup = html[html.index('id="v-setup"'):html.index('id="v-installing"')]
    assert "toxicity" not in setup.lower().replace("toxicity detection can be added afterwards", "")
    assert 'id="tox-add"' in html and re.search(r"large download", html)
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
    # the launcher exposes only the everyday options; Jupyter is opt-in (off by default)
    for field in ("host", "port", "jupyter", "appwindow", "checkupdates", "lang"):  # options live in #advanced (ready view only)
        assert f'id="{field}"' in html
    for gone in ("db", "llm", "extra", "debug", "development", "nonotebook", "log"):
        assert f'id="{gone}"' not in html, gone
    assert 'id="jupyter" type="checkbox">' in html and 'id="jupyter" type="checkbox" checked' not in html
    js = (I / "ui/main.js").read_text()
    assert "no_notebook: !$(\"jupyter\").checked" in js


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
    for ref in re.findall(r'(?:src|href)="([^":#]+)"', html):
        assert (I / "ui" / ref).exists(), ref


def test_uninstall_and_stop_on_window_close_wiring():
    rs = (I / "src-tauri/src/main.rs").read_text()
    html = (I / "ui/index.html").read_text()
    js = (I / "ui/main.js").read_text()
    assert "fn uninstall" in rs and "            uninstall,\n" in rs and '"uninstall"' in js
    assert 'id="uninstall"' in html and 'id="deletedata"' in html
    # the program is removed, data only on explicit request, and only for a real YSocial home
    assert "delete_data" in rs and 'runtime.join("venv").exists()' in rs
    # closing the application window stops YSocial (and its process group)
    assert "CloseRequested" in rs and "process_group(0)" in rs


def test_installer_version_matches_ysocial_version():
    version = (I.parent / "VERSION").read_text().strip()
    assert version == "4.0.0"
    cfg = json.loads((I / "src-tauri/tauri.conf.json").read_text())
    assert cfg["version"] == version
    cargo = (I / "src-tauri/Cargo.toml").read_text()
    assert re.search(r'^version = "%s"' % re.escape(version), cargo, re.M)


def test_launcher_closes_itself_after_app_window_and_keeps_process_alive():
    rs = (I / "src-tauri/src/main.rs").read_text()
    assert 'get_webview_window("main")' in rs
    # the close handler must hold the process until YSocial is stopped
    assert "api.prevent_close()" in rs and "app.exit(0)" in rs


def test_launcher_is_translated_and_every_key_is_used():
    js = (I / "ui/i18n.js").read_text()
    html = (I / "ui/index.html").read_text()
    main = (I / "ui/main.js").read_text()
    it_block = js[js.index("it: {"):]
    keys = set(re.findall(r'^\s+"([a-z.]+)":', it_block, re.M))
    used = set(re.findall(r'data-i18n="([a-z.]+)"', html)) | set(re.findall(r'I\("([a-z.]+)"', main))
    assert used and used <= keys, used - keys
    assert keys <= used, keys - used
    assert 'id="lang"' in html and "i18n.js" in html


def test_update_flow_wiring():
    rs = (I / "src-tauri/src/main.rs").read_text()
    js = (I / "ui/main.js").read_text()
    html = (I / "ui/index.html").read_text()
    for fn in ("app_version", "installed_info", "fetch_latest_release", "update"):
        assert f"fn {fn}" in rs and f"            {fn},\n" in rs
    for cmd in ("app_version", "installed_info", "fetch_latest_release", "update"):
        assert f'"{cmd}"' in js
    # only assets of the project's own releases are downloaded; only drafts/pre-releases are skipped
    assert "releases/download/" in rs and "RELEASE_DOWNLOAD_PREFIX" in rs
    assert "rel.draft || rel.prerelease" in js
    # the installed version is displayed and re-read after an update
    assert 'id="ver"' in html and 'id="launcher-ver"' in html and 'id="doupdate"' in html
    assert js.count("await readInstalled()") >= 3
    assert 'id="checkupdates"' in html and 'checkupdates: "check_updates"' in js


def test_release_workflow_ships_constraints_for_updates():
    wf = (I.parent / ".github/workflows/release-packaging.yml").read_text()
    assert "cp requirements.lock dist/constraints.txt" in wf


def test_launcher_toxicity_box_models_and_links():
    html = (I / "ui/index.html").read_text()
    js = (I / "ui/main.js").read_text()
    rs = (I / "src-tauri/src/main.rs").read_text()
    # toxicity offers appear only while the library is missing (setup box + "Add" card)
    assert "tox-opt" not in html and "tox-opt" not in js
    assert "$(\"tox-add\").hidden = info.toxicity || running" in js
    for fn in ("toxicity_models", "install_toxicity", "open_url"):
        assert f"fn {fn}" in rs and f"            {fn},\n" in rs and f'"{fn}"' in js
    # uninstall can also remove the models; only the folders created by the model download
    assert 'id="deletemodels"' in html and "delete_models" in rs and "deleteModels" in js
    assert '["torch", "huggingface"]' in rs
    # footer: release number and project site (opened in the system browser, allow-listed)
    assert "Release" in html and "https://y-not.social" in html and "https://y-not.social" in rs


def test_start_options_are_shown_only_after_install():
    js = (I / "ui/main.js").read_text()
    html = (I / "ui/index.html").read_text()
    assert '$("advanced").hidden = name !== "ready"' in js
    setup = html[html.index('id="v-setup"'):html.index('id="v-installing"')]
    assert 'id="advanced"' in html and 'id="advanced"' not in setup


def test_app_window_takes_focus_after_launcher_closes():
    rs = (I / "src-tauri/src/main.rs").read_text()
    assert ".focused(true)" in rs and rs.count("set_focus()") >= 3


def test_app_window_nudges_page_on_resize():
    rs = (I / "src-tauri/src/main.rs").read_text()
    assert "tauri::WindowEvent::Resized" in rs and "RESIZE_NUDGE" in rs and "CloseRequested" in rs


def test_close_shows_feedback_and_ignores_repeated_clicks():
    rs = (I / "src-tauri/src/main.rs").read_text()
    assert "CLOSING_OVERLAY" in rs and "ys-closing" in rs
    assert "CLOSING.swap(true" in rs
    # the overlay goes up before the services are stopped
    assert rs.index("w.eval(CLOSING_OVERLAY)") < rs.index("stop_service(&app, &home, &host, port, false)")
