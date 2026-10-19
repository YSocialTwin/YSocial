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

The version of every package comes from the **tag**: `scripts/packaging/set_version.py` stamps `v4.1.0` as `4.1.0` into `VERSION` (the wheel), `tauri.conf.json`, `Cargo.toml` and `Cargo.lock` inside each build job, so the wheel, the installers (`YSocial-4.1.0-<platform>.<ext>`) and the Docker image (`:v4.1.0`, plus `:latest` unless the version has a suffix such as `-rc1`) always match the release. Suffixed tags (`v4.1.0-rc1`) are attached to a pre-release.

1. Bump `VERSION` (and, to keep the repository consistent, the two installer files) in the commit you tag; the workflow warns if the tag and `VERSION` disagree, because the source archive GitHub adds to the release ("Source code (tar.gz / zip)") contains the files as committed. Regenerate `requirements.lock` if dependencies changed and make sure CI is green.
2. Create the release in either way:
   - push the tag: `git tag v4.1.0 && git push origin v4.1.0`. The workflow builds everything and creates a **draft** release with all the files; or
   - create the release from the GitHub page (new tag `v4.1.0`): the tag push starts the workflow, which **adds the files to that release** (replacing files with the same name).
3. When the workflow ends, open the release, check the files and notes, and publish. The launcher's update check reads the *latest published* release.
4. First time only (or when avatars change): build `ysocial-avatars.tar.gz` with `python scripts/packaging/make_avatars_archive.py` and attach it to the release `avatars-v1`; YSocial downloads it at first run.

**On demand.** *Actions > Release packaging > Run workflow* with the tag field empty builds all the packages from the chosen branch with the version in the repository and keeps them as workflow artifacts: nothing is released or pushed. Filling the tag field (e.g. `v4.1.0`) does the same as pushing that tag (stamping, release and image push) for a tag you want to re-package.

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
