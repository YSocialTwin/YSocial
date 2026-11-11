# Changelog

All notable changes to YSocial (YWeb) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Forum clients (Standard and HPC): a *Communities* section of the creation form lets the agents found new thematic communities (a topic, with a probability and an optional cap) and cross-post a post to related communities (probability, posts per cross-post); both are off by default and written as `communities` in the client configuration, which YClientReddit and YForum read (`y_web/src/forum/communities.py`)
- Populations: *Appearance* is its own optional, advanced, collapsed section of the creation form (hair, eyes, skin, build, height, glasses...), no longer part of the Dating fields: the traits are drawn with the chosen weights and stored as `appearance.*` custom features of the agents of any population (a Dating population keeps them as `dating.appearance.*`). A switch inside the section, off by default, generates a profile picture for each agent with a Stable Diffusion model (style, generator, model and denoising steps as in the YDating client): the pictures are written in the media folder (`<home>/media/agents`, served at `/media/agents/`), linked to the agent (`profile_pic`) and deleted with it; the generation runs in the background and its progress (bar and count) is shown in the notifications menu. A population whose agents have a generated profile picture shows it on every platform: microblogging, Photo Sharing, Forum (whatever the avatar mode) and the Instant Messaging avatars use it, and agents without one keep the current logic. In Dating the agents that already have a picture use it as their photo (copied into the experiment's media folder) and the runtime does not generate it again; the others are generated as usual. A generation interrupted by a server restart resumes at startup with the agents that still have no picture (a job file per generation in `<home>/media/jobs`). The client creation pages of every platform no longer hide populations for other platforms (the leftover filter and the "populations for other platforms are hidden" notes are gone). A failed population creation no longer errors while discarding the partial population (IR-D-05, IR-D-06).
- Populations: the details page (`admin/population_details`) has KPI tiles, a sticky page index and a *Custom fields* section with the statistics of the fields stored with the agents (appearance, Dating profile, latent variables, affective traits, other Dating fields, Photo Sharing and any other custom field), in ordered collapsible groups of Chart.js cards (coverage, distribution, mean/median for numbers); the section is absent when the agents have no custom field. Forum experiments get a *Force placeholders* switch (off by default): a picture generated for an agent is used on the forum unless the placeholders are forced (`force_placeholder_avatars` in `config_server.json`); microblogging keeps the server-assigned pictures when the agent has no generated one (IR-D-05, IR-D-06).
- Agent details (`admin/agent_details`): a header with the agent's profile picture (when it has one) and its main traits, and a *Custom attributes* section of cards in ordered groups (interests and opinions, appearance, Dating profile, latent variables with bars, affective traits, other Dating fields, Photo Sharing, other custom fields, plugin extensions) with flags, chips and bars instead of the single unstructured list (IR-D-05, IR-D-06).
- Agents: the creation form (`admin/agents`) follows the structure of the population form. *Appearance* is an optional, collapsed section (same traits, one value each, stored as `appearance.*`) with a switch, off by default, that generates the agent's profile picture with a Stable Diffusion model in the background (progress in the notifications menu); the platform fields are in a *Platform-specific fields* group with one optional section per platform, tagged with its badge and offered only when the simulator is installed: *Photo Sharing Configuration* (bio, private and verified account, attention budget, favourite filters, story visibility, creator tier; stored as agent extensions) and *Dating fields* (no longer always open; its own appearance fields are replaced by the Appearance section, which also feeds `dating.appearance.*`). Sections that are off are not submitted (IR-D-05, IR-D-06).
- Populations: the platform menus of the upload, empty population and merge forms are gone too (an uploaded file is recognised as a YSocial export or a YDating document by its content); when a population is deployed on a Dating experiment the agents under 18 are skipped with a notice instead of making the deployment fail.
- Populations: a population is no longer tied to a platform and can be deployed on any simulation (the platform select of the creation form and the compatibility checks of the clients, the merge and the upload of other platforms are gone). The fields only one platform reads are optional, advanced sections of the creation form, tagged with the badge of the platform and offered only when its simulator is installed: *Photo Sharing Configuration* (stored as agent extensions) and *Dating fields* (Dating profile, appearance, latent variables and affective traits, activity; stored as `dating.*` custom features of the same agents, which keep their own demographics, paired by gender and age with the YDating generator). A population deployed on a Dating experiment without dating fields gets them with the generator defaults; the populations table shows the platform fields each one carries (IR-D-05, IR-D-06).
- Forum clients can use the Reddit-style content recommenders `HotRanking`, `TopRanking` and `MostCommented`
  (new `content_recsys` rows reserved to forums: template database, PostgreSQL seed and Alembic `0011`).

### Fixed

- HPC (YMicroblogging) clients: the *API Key* of the main model typed in the creation form was dropped (`"NULL"` was always written); it is now written to the client configuration, so hosted providers (OpenAI, DeepSeek, ...) work.
- Model lists of the admin pages (users, populations, client details, agents, pages): they were requested without credentials and came back empty for a default server that needs a key. `get_llm_models()` now uses `LLM_API_KEY` or, for the same server, the logged-in administrator's own key; an explicit key (or an explicit empty one) is still taken as given.
- Instant Messaging and Dating clients: the API key of the model is a normal setting, like in the other platforms. The *API Key* field is written to the client configuration (`llm.llm_api_key` / `llm.api_key`) and stored with the client, and *Fetch Models* sends it; the environment variable of the previous versions (`llm_api_key_env` / `api_key_env`) is still accepted and wins when it is set.
- An Ollama endpoint that needs a key (hosted ones) receives it as a bearer token.
- Documentation of the backend plugin hooks lists all five (`staff_experiment_access` and `experiment_page_widget`
  were missing).
- Italian: "turno passato" now follows the glossary ("round passato").
- Forum clients: the *Content RecSys* menu (client creation, client details, experiment matrix) offers the
  "Standard" recommenders plus the forum-only ones; every listed recommender now exists in YClientReddit.
- Forum client details: the content recommender selection is preselected also for uncategorized entries
  (the template compared it with the friendship recommender).

### Fixed

- **LLM servers that need an API key (OpenAI, DeepSeek, ...)**: "Fetch Models" sent the
  request without credentials and failed with HTTP 401. The key typed in the form
  (client forms, vision model, ad hoc clients, add/edit user) is now sent as an
  `Authorization: Bearer` header by the server, and travels from the browser in a
  header, never in the URL. A refused key is reported as such instead of "could not
  connect", and a 401/403 no longer marks the server as unreachable.

### Added

- **API Key field in the user LLM configuration** (Update LLM Configuration and Add User; Add User now also saves the Custom LLM URL it already showed).
  The key is stored in the new `admin_users.llm_api_key` column (added automatically at
  start-up), is never written back into the page (an empty field keeps it, a checkbox removes
  it) and is used by the annotations, image descriptions, link summaries and interviews that
  run on the user's LLM. "Fetch Models" uses the stored key when the field is empty.

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
