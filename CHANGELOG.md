# Changelog

All notable changes to YSocial (YWeb) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Added

- **Instant messaging platform** (YInstantMessaging runtime, installed from the Plugins page)
  - Experiment, population and client creation, validation with `yim-validate`, start/stop/resume, clone, reset,
    download, upload, export and reports.
  - Observer pages with three viewpoints, time travel, search and profiles, read-only on the run database.
  - Analytics through a derived database (`analytics_im.db`); mapping in `docs/im-analytics-mapping.md`.
  - Frontend settings for the instant messaging pages; one defaults table for all platforms.
  - Optional human participation (off by default): participant mode, a loopback gateway with a per-run token, CSRF,
    server-side enforcement of the interaction settings, optional minimum round time and participant notice.
    Runs with humans are not reproducible.
  - Guide: `docs/instant-messaging.md`.
- **Dating platform** (YDating runtime, installed from the Plugins page, group Dating)
  - Experiment, population (standard agents with `dating.*` custom fields; upload or seeded generator) and client
    creation, validation with the runtime's offline validator, start/stop/resume, clone, reset, download and upload.
  - Settings and recommenders generated from the runtime's JSON Schemas, locked once the run has started; prompt page
    with English and Italian packs, per-key overrides and a hash per prompt recorded with the run.
  - Observer pages (researcher overview, account, public) read-only on the run database, with time travel and the
    guarantee that reserved fields never reach the account and public views.
  - Analytics through a derived database (`analytics_dating.db`); mapping in `docs/dating-analytics-mapping.md`;
    comparison of two experiments.
  - Optional human participation (off by default): entry form, notice, swipe deck, chat, dates, block and report,
    profile and pause, through a loopback gateway with a per-run token and CSRF, server-side enforcement of the
    interaction settings, optional minimum round time, photo uploads (checked and re-encoded), profile views recorded in the run database, play with every action while the server is stopped, and an admin page of participants. Runs with
    humans are not reproducible.
  - Guided tours for every dating admin page; Italian catalog (draft, native review pending).
  - Guide: `docs/dating.md`.
  - Dating population creation form (all variables of the standard form plus the dating-specific ones; shown only
    when YDating is installed) and a Dating section in the agent form that stores `dating.*` custom fields.
  - Settings pages reorganised into titled sections with readable labels and hints (client and experiment settings no
    longer repeat each other or the Experiment Configuration); dedicated client details page with extension and restart
    of the remaining days; cities follow the nationality of the agents; profile images are generated in the
    background and written in the experiment folder (they were not shown before); human participation is always on.
  - Frontend: photos as cards and avatars, YSocial header with the YDating accent, no simulation banner, better chat
    pages and a live, filterable search.
- Forum clients can use the Reddit-style content recommenders `HotRanking`, `TopRanking` and `MostCommented`
  (new `content_recsys` rows reserved to forums: template database, PostgreSQL seed and Alembic `0011`).

### Fixed

- Documentation of the backend plugin hooks lists all five (`staff_experiment_access` and `experiment_page_widget`
  were missing).
- Italian: "turno passato" now follows the glossary ("round passato").
- Forum clients: the *Content RecSys* menu (client creation, client details, experiment matrix) offers the
  "Standard" recommenders plus the forum-only ones; every listed recommender now exists in YClientReddit.
- Forum client details: the content recommender selection is preselected also for uncategorized entries
  (the template compared it with the friendship recommender).

## [4.0.0] - 2026-10-23

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

### Aligned plugin versions

| Plugin | Version |
| --- | --- |
| YServer, YServerReddit | 2.1.1 |
| YClient, YClientReddit | 2.1.1 |
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
