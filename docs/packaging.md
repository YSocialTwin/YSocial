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
| `<file>.asc`, `SHA256SUMS.txt.asc`, `release-signing-key.asc` | `release` job | detached GPG signatures of every file and of the checksums, and the public key (only when the `GPG_PRIVATE_KEY` and `GPG_PASSPHRASE` secrets exist; without them the release is published unsigned) |
| `ghcr.io/ysocialtwin/ysocial:<tag>` and `:latest` | `docker` job | image from `docker/Dockerfile` |

Installers are **not code-signed** (decision): macOS shows the Gatekeeper warning, Windows SmartScreen. Document this in the release notes.

## Making a release

The version of every package comes from the **tag**: `scripts/packaging/set_version.py` stamps `v4.1.0` as `4.1.0` into `VERSION` (the wheel), `tauri.conf.json`, `Cargo.toml` and `Cargo.lock` inside each build job, so the wheel, the installers (`YSocial-4.1.0-<platform>.<ext>`) and the Docker image (`:v4.1.0`, plus `:latest` unless the version has a suffix such as `-rc1`) always match the release. Suffixed tags (`v4.1.0-rc1`) are attached to a pre-release.

1. Bump `VERSION` (and, to keep the repository consistent, the two installer files) in the commit you tag; the workflow warns if the tag and `VERSION` disagree, because the source archive GitHub adds to the release ("Source code (tar.gz / zip)") contains the files as committed. Regenerate `requirements.lock` if dependencies changed and make sure CI is green.
   If the list of built-in plugins changed in the plugin registry (`builtin.json`), run `python scripts/packaging/sync_builtin_plugins.py --source <checkout of YSocialTwin/plugin-registry>` first and commit the result: the workflow starts with `--verify` and `--check-latest` and stops if the packaged copy is not the registry's latest.
2. Create the release in either way:
   - push the tag: `git tag v4.1.0 && git push origin v4.1.0`. The workflow builds everything and creates a **draft** release with all the files; or
   - create the release from the GitHub page (new tag `v4.1.0`): the tag push starts the workflow, which **adds the files to that release** (replacing files with the same name).
3. When the workflow ends, open the release, check the files and notes, and publish. The launcher's update check reads the *latest published* release.
4. First time only (or when avatars change): build `ysocial-avatars.tar.gz` with `python scripts/packaging/make_avatars_archive.py` and attach it to the release `avatars-v1`; YSocial downloads it at first run.

**On demand.** *Actions > Release packaging > Run workflow* with the tag field empty builds all the packages from the chosen branch with the version in the repository and keeps them as workflow artifacts: nothing is released or pushed. Filling the tag field (e.g. `v4.1.0`) does the same as pushing that tag (stamping, release and image push) for a tag you want to re-package.

To build only some installers, fill **platforms** with a comma-separated list of `macos-arm64`, `macos-x64`, `windows-x64`, `linux-x64`, `linux-arm64` (default `all`), for example `linux-x64` to retry the Linux build. Untick **docker** to skip the image. The wheel is always built. With a tag, the new files are added to the existing release: files with the same name are replaced, the others stay, and `SHA256SUMS.txt` keeps the lines of the files that were not rebuilt (it is re-signed, so the `.asc` files of the rebuilt ones are replaced too).

## Building locally

### Wheel and Docker image

```bash
python -m build --wheel --outdir dist .
python scripts/packaging/check_wheel.py dist/ysocial-*.whl
docker build -f docker/Dockerfile .         # build argument WITH_TOXICITY=1 adds toxicity detection
```

### Desktop installer, from a clean machine

The installer is a [Tauri v2](https://tauri.app/) app: a Rust backend with a static HTML UI (no Node.js, no npm). A normal build needs four things: a C/C++ toolchain, the system web view libraries, Rust with the Tauri command-line tool, and the files the installer carries inside (the wheel, `constraints.txt` and the `uv` binary). Build on the platform you are targeting: there is no cross-compilation between macOS, Windows and Linux.

#### Step 1: system prerequisites

**macOS** (Apple silicon or Intel)

```bash
xcode-select --install          # Command Line Tools (compiler, linker); skip if already installed
```

Nothing else: the web view (WKWebView) is part of the system.

**Windows 10/11**

1. Install the *Microsoft C++ Build Tools* ([download](https://visualstudio.microsoft.com/visual-cpp-build-tools/)) and tick the workload **Desktop development with C++** (it brings the MSVC compiler and a Windows SDK).
2. The *WebView2* runtime is already part of Windows 10 (recent) and 11; if it is missing, install the "Evergreen" runtime from Microsoft.
3. Use the MSVC Rust toolchain (step 2 shows how). Run the commands below in PowerShell, or in Git Bash if you prefer the Unix syntax.

**Linux**

Debian / Ubuntu (24.04 or newer):

```bash
sudo apt update
sudo apt install build-essential curl wget file patchelf xdg-utils \
  libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev libayatana-appindicator3-dev libssl-dev
```

Fedora:

```bash
sudo dnf install webkit2gtk4.1-devel openssl-devel curl wget file patchelf libxdo-devel \
  libappindicator-gtk3-devel librsvg2-devel
sudo dnf group install "c-development"
```

Arch / Manjaro:

```bash
sudo pacman -S --needed base-devel webkit2gtk-4.1 curl wget file openssl patchelf \
  appmenu-gtk-module libappindicator-gtk3 librsvg xdotool
```

Other distributions: see the [Tauri prerequisites](https://tauri.app/start/prerequisites/#linux) and install the equivalents of the packages above. arm64 machines use the same packages and produce an arm64 build.

#### Step 2: Rust

Install the toolchain with `rustup` (it needs a few minutes and about 1.5 GB).

- macOS and Linux:

  ```bash
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  ```

- Windows: download and run `rustup-init.exe` from [rustup.rs](https://rustup.rs) and accept the defaults (host `x86_64-pc-windows-msvc`). If you already have Rust with another host, run `rustup default stable-msvc`.

**Close and reopen the terminal** (so `cargo` is on the `PATH`) and check:

```bash
rustc --version      # a recent stable release (rustup installs it)
cargo --version
```

#### Step 3: Python and the Tauri tool

You need Python 3.12 (the same version YSocial targets) to build the wheel, and the Tauri command-line tool to build the app:

```bash
python3.12 -m venv .venv-build && source .venv-build/bin/activate   # Windows: .venv-build\Scripts\activate
python -m pip install --upgrade pip build uv
cargo install tauri-cli --version "^2" --locked                     # about 5 minutes, once
cargo tauri --version                                               # tauri-cli 2.x
```

#### Step 4: the files the installer carries

The installer bundles everything in `installer/src-tauri/resources/`; the folder is git-ignored, so on a fresh checkout you fill it yourself. Run these from the repository root:

```bash
mkdir -p installer/src-tauri/resources
cp requirements.lock installer/src-tauri/resources/constraints.txt
cp "$(which uv)" installer/src-tauri/resources/uv        # Windows: copy the uv.exe found by `where uv` to resources\uv.exe
```

(`uv` is the tool the installer uses to create the private Python 3.12 environment on the user's machine. It must be the binary of the platform you are building for.) The wheel is added in the last step.

#### Step 5: build

From the repository root, with the build environment active:

```bash
rm -f dist/ysocial-*.whl installer/src-tauri/resources/*.whl
python -m build --wheel --outdir dist .
cp dist/ysocial-*.whl installer/src-tauri/resources/
cd installer/src-tauri
cargo tauri build
```

PowerShell equivalent:

```powershell
Remove-Item dist\ysocial-*.whl, installer\src-tauri\resources\*.whl -ErrorAction SilentlyContinue
python -m build --wheel --outdir dist .
Copy-Item dist\ysocial-*.whl installer\src-tauri\resources\
cd installer\src-tauri
cargo tauri build
```

The first build compiles all Rust dependencies and takes 5-15 minutes; later builds take about a minute. Without options `cargo tauri build` produces every bundle the platform supports; to build one (as the release workflow does) add `--bundles`:

| System | Command | Output (under `installer/src-tauri/target/release/bundle/`) |
|---|---|---|
| macOS | `cargo tauri build --bundles dmg` | `dmg/YSocial_<version>_<arch>.dmg` and `macos/YSocial.app` |
| Windows | `cargo tauri build --bundles nsis` | `nsis/YSocial_<version>_x64-setup.exe` |
| Linux | `cargo tauri build --bundles appimage,deb` | `appimage/*.AppImage`, `deb/*.deb` |

The version of the files is the one in `installer/src-tauri/tauri.conf.json` (and `Cargo.toml`), which must equal `VERSION`; to stamp another version before building run `python scripts/packaging/set_version.py 4.1.0`.

#### Step 6: check the result

Install the file you built on a clean user account (or a virtual machine), press **Install YSocial**, **Start**, create an experiment, close the window and confirm that the services stop. A quick pre-check without installing: `cargo tauri dev` (from `installer/src-tauri`) runs the launcher straight from the sources.

#### Troubleshooting the build

| Message | Cause and fix |
|---|---|
| `linker 'cc' not found` / `link.exe not found` | The C toolchain is missing: step 1 (Command Line Tools, Build Tools, `build-essential`). |
| `The system library 'webkit2gtk-4.1' ... was not found` (Linux) | Install `libwebkit2gtk-4.1-dev` (Debian/Ubuntu); older distributions that only ship 4.0 cannot build Tauri v2. |
| `cargo: command not found` after installing Rust | Open a new terminal, or `source "$HOME/.cargo/env"`. |
| `no such command: tauri` | Step 3: `cargo install tauri-cli --version "^2" --locked`. |
| `resource path 'resources/...' doesn't exist` | Step 4 was skipped. The folder must contain the wheel, `constraints.txt` and `uv`. |
| A `.deb`/`.AppImage` is built but the app has an old version | `installer/src-tauri/tauri.conf.json` still has the old version; stamp it with `set_version.py`. |
| macOS: "cannot be opened because the developer cannot be verified" on your own build | Builds are not signed: right-click > *Open*, or `xattr -dr com.apple.quarantine YSocial.app`. |
| Building for Intel on an Apple silicon Mac | `rustup target add x86_64-apple-darwin`, use an Intel `uv` binary and `cargo tauri build --target x86_64-apple-darwin`. The release workflow builds Intel natively instead. |

`installer/ui/assets/` mirrors the application's login-page assets; after changing them run `python scripts/packaging/sync_installer_assets.py` (a test fails when they drift).

## Conventions

- One Python version everywhere: 3.12 (CI, release workflow, Docker, `requires-python`).
- The wheel excludes avatars (downloaded at first run) and ships `data_schema`, prompts, translations and migrations as package data.
- English prompt output must stay byte-identical: `python scripts/prompts/snapshot_hashes.py --check`.
- Tests that need Ray or local-only resources are skipped on GitHub Actions (`GITHUB_ACTIONS=true`).

## History

Until 3.x the application was distributed as PyInstaller executables built from `y_social.spec` (with macOS DMG scripts and code-signing notes). That pipeline, its spec and its docs were removed in 4.0.0. The Python code still contains defensive branches for frozen executables and `y_social_launcher.py` still offers an optional pywebview window when running from a checkout; they are inert in the packaged distribution and can be removed in a later clean-up.

### Verifying a download

```bash
curl -LO https://github.com/YSocialTwin/YSocial/raw/main/docs/release-signing-key.asc
gpg --import release-signing-key.asc
gpg --verify YSocial-<version>-linux-x64.AppImage.asc YSocial-<version>-linux-x64.AppImage
sha256sum -c SHA256SUMS.txt --ignore-missing
```
