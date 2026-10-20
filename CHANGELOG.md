# Changelog

All notable changes to YSocial (YWeb) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [4.0.0] - 2026-10-20

YSocial 4.0.0 turns the web application into an installable product: a Python
wheel, a desktop installer, a Docker image and a public plugin registry, with
a fully localized interface (English and Italian) and prompt packs per language.

### Added

- **Packaging and distribution**
  - `ysocial` wheel with entry point and content check, SPDX license
    expression and pinned dependencies (`requirements.lock`, `PIP_CONSTRAINT`).
  - Desktop installer (Tauri v2) for macOS, Windows and Linux (x64 and arm64):
    native application window, Start/Stop/Uninstall, advanced options (host,
    port, database, LLM, CLI flags), launcher translated to English and Italian,
    installed-version display and update from GitHub releases.
  - Managed Python 3.12 environment bootstrapped with `uv`; plugins install
    into it (`YSOCIAL_PYTHON`).
  - User data separated from the code in `YSOCIAL_HOME`.
  - Docker image built from the wheel, entrypoint and Compose profiles
    (including PostgreSQL); release workflow that stamps the tag version into
    wheel, installers and image.
  - Avatars are downloaded on first start (resumable, lightweight background
    download); `detoxify` is an optional extra.
  - Guides: building the desktop installer from scratch, adding a language,
    localization closure checklist.
- **Plugins**
  - Public plugin registry (official and community) and generated
    `builtin_plugins.json`; built-in plugins carry their description.
  - Install and update from a GitHub release archive or from a branch archive
    (no git needed); branch listing with API pagination and `git ls-remote`
    fallback.
  - Plugin list shows the installed version as a tag and, when a newer release
    exists, an arrow and an orange tag with the available version.
  - Compact install page: "GitHub release" first, git checkout moved under a
    collapsed "Alternative installation".
  - Public repositories that turn public become visible automatically.
  - Agent Memory plugin (`y_memory_subsystem`): memory settings appear only when
    it is installed.
- **Internationalization**
  - Italian interface, validated by a native speaker (no "beta" label).
  - Prompt packs per language: chats with agents, interviews, annotators, URL
    summary and ad hoc plugin agents follow the experiment's prompt language;
    follow action and reciprocal-follow verb localized; language selector on the
    prompts pages.
  - CI ratchet for unmarked strings (`scripts/i18n/`).
- **Admin panel**
  - Dashboard: compact "Quick guide" and "News from the Agents" box (latest four
    posts of the Y blog, stored in the admin database), compact Simulations and
    Training boxes, pagination by experiment group.
  - Errors and notifications unified as floating top-right cards; dashboard
    progress and notifications poll every 30 s.
  - Photo-sharing sidebar links back to the admin panel (admins only).
- Hashtags are stored in canonical form (duplicates merged); camel-case
  usernames are displayed as separate words in microblogging.

### Changed

- Python 3.12 or later is required.
- Built-in plugins list moved to `builtin_plugins.json`; the bundled externals
  no longer include `y_agents_plugins` and `y_memory_subsystem`.
- Photo profile: spoken language is a list, as in microblogging and forum.
- Shutdown terminates simulator process trees in parallel and closes database
  state.
- Template context processors and startup migrations moved out of
  `y_web/__init__.py` (behaviour unchanged).
- PyInstaller packaging retired in favour of the wheel and the Tauri installer.

### Fixed

- Login "Remember me" now survives restarts (secret key persisted in the data
  folder; `YSOCIAL_SECRET_KEY` overrides it).
- "Release download failed (415)" when installing plugins from a release.
- Wrong "update available" message when installed and latest versions are equal
  (versions are now compared numerically).
- Plugin description falls back to the core translation catalog.
- Legacy databases: missing columns are realigned at startup, Alembic `0003`
  adds missing `category`/`enabled`.
- HPC: Ray token authentication disabled for the local cluster, which stalled
  simulations; server/client start through a space-free alias of the data
  folder; missing `last_active_day` and schema caching issues on new
  experiments; `prompt_language` resolved before writing the prompt pack.
- Forum: undefined variable when publishing a post.
- Trending hashtags no longer show a double `#`.
- Venv symlink is no longer resolved by the plugin manager and environment
  detection (pip ended up in the base Python).
- Installer: the app window no longer intercepts iframe navigations (Stripe),
  gives focus on first click and the launcher stops YSocial when the window
  closes.

### Known issues

- On Windows, stopping a simulation terminates processes with `taskkill /F`
  (forced, no graceful shutdown).

### Bundled plugin versions

| Plugin | Version |
| --- | --- |
| YServer, YServerReddit | 2.1.0 |
| YClient, YClientReddit | 2.1.0 |
| YPhotoSharing | 2.1.0 |
| YSimulator | 2.1.0 |
| ScenarioDesign | 1.1.0 |
| TrainingModules | 1.33.0 |
| frontend_adds-on | 0.2.0 |
| reactive_agents | 0.11.0 |
| y_agents_plugins | 0.2.0 |
| y_memory_subsystem | 0.2.0 |

[Unreleased]: https://github.com/YSocialTwin/YSocial/compare/v4.0.0...HEAD
[4.0.0]: https://github.com/YSocialTwin/YSocial/compare/v3.0.0...v4.0.0
