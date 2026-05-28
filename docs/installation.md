# Installation

## Installation modalities

YSocial supports three practical installation paths:

1. Standalone executable
   Best for end users who do not want to manage Python dependencies.

2. Installation from source
   Best for development, local customization, and notebook-enabled workflows.

3. Container-based deployment
   Best for controlled server-style environments.

## Option 1: Standalone executable

Pre-built executables are the simplest distribution form.

Typical flow:

1. Download the package for your operating system.
2. Install or unpack it.
3. Start YSocial.
4. Log in with your configured credentials.

Notes:

- Desktop mode is the normal default in packaged builds.
- Browser mode remains available through command-line flags.
- Packaged builds bundle most Python dependencies and static assets.
- Notebook support is intentionally constrained in PyInstaller builds.

## Option 2: Installation from source

### Prerequisites

- Python 3.11 recommended
- Git
- required external runtime repositories cloned under `external/`
- a writable working directory

Recommended environment setup:

```bash
conda create --name YSocial python=3.11
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

## Option 3: Container-based deployment

The repository includes Docker and docker-compose assets.

Relevant files:

- `/Users/rossetti/PycharmProjects/YWeb/Dockerfile`
- `/Users/rossetti/PycharmProjects/YWeb/deployment/docker/compose/docker-compose.yml`
- `/Users/rossetti/PycharmProjects/YWeb/deployment/docker/compose/docker-compose-postgresql.yml`
- `/Users/rossetti/PycharmProjects/YWeb/deployment/docker/compose/docker-compose_gpu.yml`
- `/Users/rossetti/PycharmProjects/YWeb/deployment/docker/compose/docker-compose-postgresql_gpu.yml`

Use containers when you want:

- deployment guidance organized under `/Users/rossetti/PycharmProjects/YWeb/deployment/docker/README.md`
- advanced reverse-proxy and GPU assets documented under `/Users/rossetti/PycharmProjects/YWeb/deployment/docker/advanced/README.md`

- repeatable local deployment
- isolated dependency management
- a PostgreSQL-backed runtime
- a server-style installation instead of a desktop workflow

## Runtime dependencies by concern

### Core application

Core dependencies are listed in:

- `/Users/rossetti/PycharmProjects/YWeb/requirements.txt`

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

## Persistence and working directory

YSocial writes runtime data into the working directory or application data folders depending on execution mode.

Important locations include:

- `/Users/rossetti/PycharmProjects/YWeb/y_web/db/`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/experiments/`
- `/Users/rossetti/PycharmProjects/YWeb/config_files/`
- `/Users/rossetti/PycharmProjects/YWeb/logs/` when created by runtime scripts
- notebook and export directories created during execution

If you want clean separation between code and runtime state, launch the application from a dedicated data directory when using packaged executables.
