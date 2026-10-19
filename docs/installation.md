# Installation

## Installation modalities

YSocial can be installed in four ways. Pick the first one unless you have a reason not to.

1. **Desktop installer** (macOS, Windows, Linux): a small graphical app that sets everything up for you and starts YSocial in its own window. No terminal, no Python knowledge. See [Desktop installer and launcher](launcher.md).
2. **Python package** (`pip`/`uv`): the same `ysocial` command the installer uses, for people who manage their own environments or servers.
3. **From source**: for development and local customization.
4. **Docker**: for controlled, server-style deployments.

In every case YSocial keeps its data in one folder (`YSOCIAL_HOME`, see [Where the data lives](#where-the-data-lives)) and plugins are installed later from the admin panel, not bundled.

## Option 1: Desktop installer

Download the installer for your system from the [latest release](https://github.com/YSocialTwin/YSocial/releases/latest) (or from [y-not.social/download](https://y-not.social/download)):

| System | File |
|---|---|
| macOS, Apple silicon | `YSocial-<version>-macos-arm64.dmg` |
| macOS, Intel | `YSocial-<version>-macos-x64.dmg` |
| Windows 10/11 | `YSocial-<version>-windows-x64.exe` |
| Linux x86-64 | `YSocial-<version>-linux-x64.AppImage` or `.deb` |
| Linux arm64 | `YSocial-<version>-linux-arm64.AppImage` or `.deb` |

Open it, press **Install YSocial** and wait a few minutes (the first time it downloads and prepares a private Python 3.12 environment). Then press **Start**. The installers are **not code-signed**, so the first launch shows a security warning: on macOS right-click the app and choose *Open* (or run `xattr -dr com.apple.quarantine /Applications/YSocial.app`), on Windows choose *More info* and then *Run anyway*. Windows needs the WebView2 runtime (already present on Windows 10/11); Linux needs WebKitGTK 4.1.

Everything about using, updating and removing it is in [Desktop installer and launcher](launcher.md).

## Option 2: Python package

Requires Python 3.12 or newer. Download `ysocial-<version>-py3-none-any.whl` and `constraints.txt` from the same [release](https://github.com/YSocialTwin/YSocial/releases/latest), then:

```bash
python3.12 -m venv ysocial-env && source ysocial-env/bin/activate     # Windows: ysocial-env\Scripts\activate
pip install ysocial-<version>-py3-none-any.whl -c constraints.txt
ysocial --host localhost --port 8080
```

`constraints.txt` pins the dependency versions the release was tested with; leave it out only if you want newer ones. Useful extras:

```bash
pip install "ysocial-<version>-py3-none-any.whl[toxicity]" -c constraints.txt   # toxicity detection (downloads PyTorch, large)
```

Open `http://localhost:8080` and log in with the default administrator (`admin@y-not.social` / `admin`; change it after the first login). To update, install the newer wheel over the old one: the data folder is kept and the database is migrated at the next start.

## Option 3: Installation from source

### Prerequisites

- Python 3.12 recommended
- Git
- required external runtime repositories cloned under `external/`
- a writable working directory

Recommended environment setup:

```bash
conda create --name YSocial python=3.12
conda activate YSocial
```

Clone and install:

```bash
git clone https://github.com/YSocialTwin/YSocial.git
cd YSocial
pip install -r requirements.txt
```

Optional but common extras:

- local LLM runtime for model-backed features
- PostgreSQL if you do not want SQLite
- Redis and Ray if you use the HPC execution path

### First start from source

Browser mode:

```bash
python y_social.py --host localhost --port 8080 --llm-backend ollama
```

Desktop mode via launcher:

```bash
python y_social_launcher.py --llm-backend ollama
```

## Option 4: Docker

A ready image is published for every release on the GitHub Container Registry:

```bash
docker run -d --name ysocial -p 5000:5000 -v ysocial-data:/data ghcr.io/ysocialtwin/ysocial:latest
```

Then open `http://localhost:5000`. The volume keeps the data folder (`/data`) across restarts and upgrades. To start from the repository instead (SQLite, or with PostgreSQL):

```bash
docker compose -f docker/compose.yml up                       # YSocial + SQLite
docker compose -f docker/compose.yml --profile postgres up    # + PostgreSQL
WITH_TOXICITY=1 docker compose -f docker/compose.yml build    # image with toxicity detection
```

LLM servers (Ollama, vLLM, any OpenAI-compatible service) are **not** part of the image: run them outside and set the endpoint in the admin UI (from the container, the host is `http://host.docker.internal:11434` for Ollama). Extra arguments after the image name go to `ysocial` (for example `--db postgresql`). The older compose variants (GPU, reverse proxy) are still described in `deployment/docker/README.md`.

## Runtime dependencies by concern

### Core application

Core dependencies are listed in:

- `requirements.txt`

They include:

- Flask and Flask extensions
- SQLAlchemy
- feed parsing and requests
- NLP and annotation utilities
- authentication and forms
- telemetry and logging support

### Optional feature dependencies

Some features depend on optional external services or packages:

| Concern | Typical requirement |
|---|---|
| local LLM | Ollama, vLLM, or another OpenAI-compatible service |
| notebook analysis | `jupyterlab`, writable notebook workspace |
| HPC execution | Ray, Redis, backend-specific runtime stack |
| PostgreSQL | a running PostgreSQL server and connection settings |

## Where the data lives

All state (databases, experiments, installed plugins, logs) is stored under one folder, `YSOCIAL_HOME`. It defaults to:

| System | Default folder |
|---|---|
| macOS | `~/Library/Application Support/YSocial` |
| Windows | `%USERPROFILE%\AppData\Local\YSocial` |
| Linux | `~/.ysocial` |
| Docker | `/data` |

Set the `YSOCIAL_HOME` environment variable (or, in the desktop installer, *Advanced options > Where to keep your data*) to use another place. Inside it:

- `y_web/db/` and `y_web/experiments/`: dashboard database and one folder per experiment
- `external/`: installed plugins
- `runtime/`: the private Python environment (desktop installer only)
- `logs/launch.log` and `launcher.json`: launcher log and settings (desktop installer only)

Downloaded toxicity models are cached outside it, in `~/.cache/ysocial_models` (change with `YSOCIAL_MODEL_CACHE_DIR`). Back up the data folder to back up YSocial; deleting it resets the installation.
