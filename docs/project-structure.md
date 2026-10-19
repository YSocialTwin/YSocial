# Project Structure

## Top-level layout

Important top-level directories and files:

| Path | Role |
|---|---|
| `y_web/` | main application package |
| `external/` | external runtime repositories and backends |
| `installer/` | desktop installer/launcher (Tauri app, UI, Rust backend) |
| `scripts/packaging/` | packaging helpers (wheel check, asset sync, avatars archive) |
| `docker/` | Dockerfile, compose file, entrypoint |
| `docs/` | documentation |
| `data_schema/` | schema and migrations |
| `config_files/` | runtime configuration assets |
| `y_social.py` | main browser-mode entry point |
| `y_social_launcher.py` | optional desktop window (pywebview) when running from a checkout |
| `pyproject.toml` | package definition; installs the `ysocial` command |

## Inside `y_web/`

### Routes

- `y_web/routes/`

Contains admin, public, API, and integration route modules.

### Source services

- `y_web/src/`

Contains service-layer and domain logic such as:

- simulation execution
- forum and feed logic
- LLM integration
- HPC support
- system utilities
- data access

### Templates

- `y_web/templates/`

Contains the Jinja templates for:

- admin
- forum
- microblogging
- login
- error pages
- shared partials

### Static assets

- `y_web/static/`

Contains CSS, JavaScript, vendor assets, images, and runtime UI dependencies.

### Databases and experiment state

Typical runtime paths include:

- `y_web/db/`
- `y_web/experiments/`

The dashboard DB and per-experiment directories serve different roles:

- dashboard DB: admin state, users, visibility, scheduling, and metadata
- experiment directories: run-specific configs, logs, exports, and experiment databases

## External directory

- `external/`

This directory holds backend/runtime repositories used by YSocial when present. Operationally, YSocial adapts available experiment options based on which required external runtimes are installed.

## Packaging

- `installer/`: the desktop installer/launcher (static UI in `ui/`, Rust backend in `src-tauri/`)
- `scripts/packaging/`: wheel content check, installer asset sync, avatars archive
- `docker/`: image and compose file
- `.github/workflows/release-packaging.yml`: builds wheel, installers and image on a `v*` tag

## Tests

- `y_web/tests/`

The test suite is extensive and covers runtime behavior, packaging, template contracts, admin workflows, and execution helpers.

## How to navigate the repository effectively

If you are trying to answer a project question, use this order:

1. check `README.md`
2. check `docs/` and `installer/`
3. inspect `y_social.py` and `y_social_launcher.py`
4. inspect route handlers under `y_web/routes/`
5. inspect service logic under `y_web/src/`
6. confirm with tests under `y_web/tests/`
