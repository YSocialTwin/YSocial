# Changelog

All notable changes to YSocial (YWeb) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Added

- Populations: the platform menus of the upload, empty population and merge forms are gone too (an uploaded file is recognised as a YSocial export or a YDating document by its content); when a population is deployed on a Dating experiment the agents under 18 are skipped with a notice instead of making the deployment fail.
- Populations: a population is no longer tied to a platform and can be deployed on any simulation (the platform select of the creation form and the compatibility checks of the clients, the merge and the upload of other platforms are gone). The fields only one platform reads are optional, advanced sections of the creation form, tagged with the badge of the platform and offered only when its simulator is installed: *Photo Sharing Configuration* (stored as agent extensions) and *Dating fields* (Dating profile, appearance, latent variables and affective traits, activity; stored as `dating.*` custom features of the same agents, which keep their own demographics, paired by gender and age with the YDating generator). A population deployed on a Dating experiment without dating fields gets them with the generator defaults; the populations table shows the platform fields each one carries (IR-D-05, IR-D-06).
- Dating observer: the viewpoint and time controls are one compact sticky bar (segmented Overview/Public/As account, time slider with step buttons and a Time travel / Latest pill, info popover) and the invasive banners and side panel are gone; *View as account* searches by username with a live list and profile-picture thumbnails (`/dating/api/accounts`); the Discover page in that mode is an account header with decision counts, filterable card tiles and a reader lightbox (IR-D-05, IR-D-06).
- Dating: administrators can reset the credits (the likes and super likes of the day) of one human participant, or of all of them, from the experiment's Participants page. The reset is recorded in the database (`quota_resets`, schema version 4), so a restart keeps it. Needs the YDating commit that adds the `reset_quota` gateway operation (IR-D-05, IR-D-06).

- Dating pages: search with one rounded box, filters behind a button with a count and compact portrait tiles; profile page with a swipeable photo stage, thumbnails, quote cards and a tabbed researcher block (latent traits, relationship statistics with counters); *Your profile* page with completeness, tabs (About you, Photos, Who you see, Account), a photo grid with a drop tile and live values; Notifications is a link only when something is to read, with the count as a badge (opening a chat marks its messages as read). Matches and chat no longer read every message of the run (faster on long runs); needs the YDating commit that runs its SQLite database in WAL mode, so the observer no longer waits for the server's commits (IR-D-05, IR-D-06).

- Dating observer: the matches table shows how each match went (date good / so-so / bad, i.e. not continuing off the platform, declined or unanswered proposals, ghosting, no opener, unmatched, blocked, left the platform, left together), the chat adds the same markers, and the agent profile carries lifecycle statistics (conversations, ghosting both ways, dates and outcomes, exits) visible to researchers and admins only; an account sees only a generic "match ended" for what others decided (IR-D-05, IR-D-06). Needs the YDating commit that writes date proposals and answers in the chat.

- Dating: reorganised client page (language model with *Fetch* like the other platforms, image model right after it, per-client recommender with an explanation of each model, 30-day duration with *Run until stopped*, defaults that follow whether the experiment uses language models, components that are off are hidden); style of the profile photos (photorealistic faces or cartoon characters); the daily rhythm of the agents uses the activity profiles of the population form; human participation is always on; the experiment settings are editable whenever the experiment is not running (IR-D-05, IR-D-06). The Dating population page is no longer separate: its statistics are on the standard population details page and the Available Populations table shows education, leanings and activity profiles for Dating too. Experiment settings are one form with tabs, a recommender description in the side column and collapsible advanced panels (also in the client page); saving no longer fails when the stored default recommender is missing. Image model chosen from small Hugging Face models; the distance filter of the matching is an experiment switch (`matching.common.distance_filter`, off by default); the client page no longer repeats the daily rhythm. Generated dating populations get real-looking names; photos show the agent in the scene of the caption (`images.use_caption`); the dating profile page is redesigned (gallery with lightbox, animated cards, bars for the latent variables); adding a human user to a Dating experiment no longer fails on the NOT NULL `match_recsys` column of the runtime. Adding a human user no longer fails on the `status` CHECK of the runtime either, and a registered participant who chooses a Dating experiment keeps the account session and lands on the play view (no more "Please log in"). The play view is a compact full-photo card that is really swiped (stamps, fly-off, next card rising), without photo descriptions or the "playing as" banner; the join page is a four-step profile builder; the settings expose `revisit_after_days` (profiles already decided on come back and are judged anew, the earlier decision remembered) and `swipe.revisit_inertia`. Needs the YDating commit that adds `profile_generation.images.style` and the generator key `archetypes`.

- **Dating admin pages aligned with YSimulator**: the dating population is created in the standard population form
  (platform *Dating*, also for file upload); client and experiment settings use switches, tags, the 0-10 importance
  scale, sliders, an hourly activity chart, a quick reference guide and an advanced-settings switch.
  The Dating population uses the same selectors and percentages (total 100) as the other platforms, including age
  classes, nationality and spoken language; Big Five, cities and interests are sampled; the matching recommender is
  chosen in the client; every dating parameter has a proposed default.
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
