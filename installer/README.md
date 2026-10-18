# YSocial installer (E5 prototype)

Tauri v2 app (Rust backend + static HTML UI, no Node build step).
It installs a uv-managed Python 3.12 environment under `<YSOCIAL_HOME>/runtime`,
installs the bundled `ysocial` wheel (optionally with the `toxicity` extra) and
launches `ysocial`, opening the browser once the port answers.

**Status: written but never compiled or run** (no Rust toolchain in the authoring
environment). Gate G-E5 requires a manual test on macOS, Windows and Linux.

Build (needs Rust + Tauri prerequisites):

```bash
python -m build --wheel --outdir installer/src-tauri/resources .
cp requirements.lock installer/src-tauri/resources/constraints.txt
cp "$(which uv)" installer/src-tauri/resources/uv      # uv.exe on Windows
cd installer/src-tauri && cargo install tauri-cli --version "^2" --locked
cargo tauri icon path/to/logo.png                         # generates icons/
cargo tauri build
```

Defaults for the data folder match `y_web/src/system/path_utils.py`.
No code signing or notarization (macOS ad-hoc only), as decided.
