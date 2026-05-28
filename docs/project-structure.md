# Project Structure

## Top-level layout

Important top-level directories and files:

| Path | Role |
|---|---|
| `/Users/rossetti/PycharmProjects/YWeb/y_web/` | main application package |
| `/Users/rossetti/PycharmProjects/YWeb/external/` | external runtime repositories and backends |
| `/Users/rossetti/PycharmProjects/YWeb/packaging/` | packaging and distribution scripts |
| `/Users/rossetti/PycharmProjects/YWeb/docs/` | documentation |
| `/Users/rossetti/PycharmProjects/YWeb/data_schema/` | schema and migrations |
| `/Users/rossetti/PycharmProjects/YWeb/config_files/` | runtime configuration assets |
| `/Users/rossetti/PycharmProjects/YWeb/y_social.py` | main browser-mode entry point |
| `/Users/rossetti/PycharmProjects/YWeb/y_social_launcher.py` | desktop-first launcher and PyInstaller entry |
| `/Users/rossetti/PycharmProjects/YWeb/y_social.spec` | PyInstaller spec |

## Inside `y_web/`

### Routes

- `/Users/rossetti/PycharmProjects/YWeb/y_web/routes/`

Contains admin, public, API, and integration route modules.

### Source services

- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/`

Contains service-layer and domain logic such as:

- simulation execution
- forum and feed logic
- LLM integration
- HPC support
- system utilities
- data access

### Templates

- `/Users/rossetti/PycharmProjects/YWeb/y_web/templates/`

Contains the Jinja templates for:

- admin
- forum
- microblogging
- login
- error pages
- shared partials

### Static assets

- `/Users/rossetti/PycharmProjects/YWeb/y_web/static/`

Contains CSS, JavaScript, vendor assets, images, and runtime UI dependencies.

### Databases and experiment state

Typical runtime paths include:

- `/Users/rossetti/PycharmProjects/YWeb/y_web/db/`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/experiments/`

The dashboard DB and per-experiment directories serve different roles:

- dashboard DB: admin state, users, visibility, scheduling, and metadata
- experiment directories: run-specific configs, logs, exports, and experiment databases

## External directory

- `/Users/rossetti/PycharmProjects/YWeb/external/`

This directory holds backend/runtime repositories used by YSocial when present. Operationally, YSocial adapts available experiment options based on which required external runtimes are installed.

## Packaging directory

- `/Users/rossetti/PycharmProjects/YWeb/packaging/`

Contains:

- executable build docs
- macOS DMG packaging scripts
- entitlements
- uninstall scripts
- user-facing packaged-app readme

## Tests

- `/Users/rossetti/PycharmProjects/YWeb/y_web/tests/`

The test suite is extensive and covers runtime behavior, packaging, template contracts, admin workflows, and execution helpers.

## How to navigate the repository effectively

If you are trying to answer a project question, use this order:

1. check `README.md`
2. check `docs/` and `packaging/`
3. inspect `y_social.py` and `y_social_launcher.py`
4. inspect route handlers under `y_web/routes/`
5. inspect service logic under `y_web/src/`
6. confirm with tests under `y_web/tests/`
