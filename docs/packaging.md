# Release and distribution

For maintainers. End users: see [Installation](installation.md) and [Desktop installer and launcher](launcher.md).

PyInstaller executables are **retired**: YSocial is distributed as a Python package (wheel) plus a graphical installer that manages a private Python environment with [uv](https://docs.astral.sh/uv/), and as a Docker image. Plugins are never bundled; they are installed later from the admin panel.

## What a release contains

A tag `v<version>` runs `.github/workflows/release-packaging.yml`, which builds everything and creates a **draft** GitHub release (nothing is published automatically):

| Artifact | Built by | Notes |
|---|---|---|
| `ysocial-<version>-py3-none-any.whl` | `wheel` job | `python -m build --wheel`; contents verified by `scripts/packaging/check_wheel.py` |
| `constraints.txt` | `wheel` job | copy of `requirements.lock`; the launcher uses it to update an installation |
| `YSocial-<version>-<platform>.<ext>` | `installers` job (matrix) | `macos-arm64` and `macos-x64` (`.dmg`), `windows-x64` (`.exe`), `linux-x64` and `linux-arm64` (`.AppImage`, `.deb`) |
| `SHA256SUMS.txt` | `release` job | checksum of every file attached |
| `ghcr.io/ysocialtwin/ysocial:<tag>` and `:latest` | `docker` job | image from `docker/Dockerfile` |

Installers are **not code-signed** (decision): macOS shows the Gatekeeper warning, Windows SmartScreen. Document this in the release notes.

## Making a release

1. Set the version in `VERSION`, `installer/src-tauri/tauri.conf.json` and `installer/src-tauri/Cargo.toml` (they must match; `test_installer_scaffold.py` checks it).
2. Regenerate the lock file if dependencies changed (`requirements.lock`) and make sure CI is green.
3. Tag and push: `git tag v<version> && git push origin v<version>`. To test the build without releasing, run the workflow by hand (*Actions > Release packaging > Run workflow*): it produces the artifacts but creates no release.
4. Open the draft release, check the files and the generated notes, then publish. The launcher's update check reads the *latest published* release.
5. First time only (or when avatars change): build `ysocial-avatars.tar.gz` with `python scripts/packaging/make_avatars_archive.py` and attach it to the release `avatars-v1`; YSocial downloads it at first run.

## Building locally

Wheel:

```bash
python -m build --wheel --outdir dist .
python scripts/packaging/check_wheel.py dist/ysocial-*.whl
```

Installer (needs Rust and the [Tauri prerequisites](https://tauri.app/start/prerequisites/)):

```bash
res=installer/src-tauri/resources
rm -f "$res"/ysocial-*.whl && cp dist/ysocial-*.whl "$res"/
cp requirements.lock "$res/constraints.txt"
cp "$(which uv)" "$res/uv"                  # uv.exe on Windows
cd installer/src-tauri && cargo install tauri-cli --version "^2" --locked
cargo tauri build --bundles dmg             # nsis (Windows), appimage,deb (Linux)
```

`installer/ui/assets/` mirrors the application's login-page assets; after changing them run `python scripts/packaging/sync_installer_assets.py` (a test fails when they drift).

Docker: `docker build -f docker/Dockerfile .` (build argument `WITH_TOXICITY=1` adds toxicity detection).

## Conventions

- One Python version everywhere: 3.12 (CI, release workflow, Docker, `requires-python`).
- The wheel excludes avatars (downloaded at first run) and ships `data_schema`, prompts, translations and migrations as package data.
- English prompt output must stay byte-identical: `python scripts/prompts/snapshot_hashes.py --check`.
- Tests that need Ray or local-only resources are skipped on GitHub Actions (`GITHUB_ACTIONS=true`).

## History

Until 3.x the application was distributed as PyInstaller executables built from `y_social.spec` (with macOS DMG scripts and code-signing notes). That pipeline, its spec and its docs were removed in 4.0.0. The Python code still contains defensive branches for frozen executables and `y_social_launcher.py` still offers an optional pywebview window when running from a checkout; they are inert in the packaged distribution and can be removed in a later clean-up.
