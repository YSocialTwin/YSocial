# YSocial installer / launcher

Tauri v2 app (Rust backend + static HTML UI, no Node build step).
It installs a uv-managed Python 3.12 environment under `<YSOCIAL_HOME>/runtime`,
installs the bundled `ysocial` wheel (optionally with the `toxicity` extra) and
launches `ysocial`, opening the browser once the port answers.

**Platforms.** macOS (Apple silicon and Intel, `.dmg`), Windows (`.exe`, NSIS) and
Linux x64 and arm64 (`.AppImage`, `.deb`). All four are built by the `installers` job of
`.github/workflows/release-packaging.yml` on every `v*` tag and attached to the draft
release together with the wheel, `constraints.txt` and `SHA256SUMS.txt`. The builds are
**unsigned** (decision): expect the Gatekeeper / SmartScreen warning on first launch.
Only macOS has been run by hand so far; Windows and Linux need a manual pass (gate G-E5):
install, start in app window and in browser mode, stop from the window close, uninstall.

Platform notes: Windows needs the WebView2 runtime (present on Windows 10/11); Linux needs
WebKitGTK 4.1 (`libwebkit2gtk-4.1`) and `xdg-open`; every platform uses `curl`
(update check / downloads), which ships with macOS, Windows 10+ and most Linux distributions.

Build (needs Rust + Tauri prerequisites):

```bash
python -m build --wheel --outdir installer/src-tauri/resources .
cp requirements.lock installer/src-tauri/resources/constraints.txt
cp "$(which uv)" installer/src-tauri/resources/uv      # uv.exe on Windows
# Linux only, once: sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev libayatana-appindicator3-dev patchelf
cd installer/src-tauri && cargo install tauri-cli --version "^2" --locked
cargo tauri icon path/to/logo.png                         # generates icons/
cargo tauri build
```

Defaults for the data folder match `y_web/src/system/path_utils.py`.
No code signing or notarization (macOS ad-hoc only), as decided.
