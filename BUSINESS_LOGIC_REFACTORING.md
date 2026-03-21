# YSocial Business Logic Refactoring Plan

This document analyses the Python scripts that implement YSocial's business logic and
proposes a rational refactoring.  It covers:

1. [Current State and Problems](#1-current-state-and-problems)
2. [Proposed Package Architecture](#2-proposed-package-architecture)
3. [Phased Implementation Plan](#3-phased-implementation-plan)
4. [Validation Steps](#4-validation-steps)
5. [Regression-Prevention Strategy](#5-regression-prevention-strategy)

---

## 1. Current State and Problems

The files in scope are those inside `y_web/utils/`, `y_web/recsys_support/`,
`y_web/llm_annotations/`, `y_web/reddit/`, and the top-level module files
`y_web/data_access.py`, `y_web/models.py`, and `y_web/experiment_context.py`.

### 1.1 File Inventory

| Location | File | Lines | Domain |
|---|---|---:|---|
| `y_web/` | `models.py` | 1,383 | ORM model definitions |
| `y_web/` | `data_access.py` | 1,495 | Cross-entity query functions |
| `y_web/` | `experiment_context.py` | 179 | Multi-experiment DB binding |
| `y_web/utils/` | `external_processes.py` | 3,170 | Process / subprocess management |
| `y_web/utils/` | `log_metrics.py` | 1,690 | HPC log parsing and metric storage |
| `y_web/utils/` | `y_client_process_runner.py` | 954 | Client simulation runner |
| `y_web/utils/` | `process_watchdog.py` | 875 | Process monitoring daemon |
| `y_web/utils/` | `jupyter_utils.py` | 699 | Jupyter Lab lifecycle |
| `y_web/utils/` | `agents.py` | 516 | Agent population generation |
| `y_web/utils/` | `text_utils.py` | 405 | Text / NLP utilities |
| `y_web/utils/` | `desktop_file_handler.py` | 311 | PyWebview desktop file downloads |
| `y_web/utils/` | `check_release.py` | 230 | GitHub release update checker |
| `y_web/utils/` | `experiment_helpers.py` | 223 | Experiment DB helpers |
| `y_web/utils/` | `article_extractor.py` | 216 | Web article metadata scraping |
| `y_web/utils/` | `miscellanea.py` | 203 | Miscellaneous helpers |
| `y_web/utils/` | `avatars.py` | 244 | Forum avatar resolution |
| `y_web/utils/` | `log_sync_scheduler.py` | 175 | HPC log-sync background thread |
| `y_web/utils/` | `check_blog.py` | 176 | YSocial blog RSS checker |
| `y_web/utils/` | `experiment_schema.py` | 166 | Experiment DB schema enforcement |
| `y_web/utils/` | `experiment_clock.py` | 146 | Simulated-clock configuration |
| `y_web/utils/` | `experiment_schedule_monitor.py` | 125 | Schedule advancement daemon |
| `y_web/utils/` | `hpc_population_backup.py` | 109 | HPC population JSON backup |
| `y_web/utils/` | `path_utils.py` | 109 | Cross-platform path helpers |
| `y_web/utils/` | `experiment_access.py` | 107 | Experiment permission checks |
| `y_web/utils/` | `population_platform.py` | 74 | Platform-to-population mapping |
| `y_web/utils/` | `execution_backend.py` | 51 | Start/stop backend abstraction |
| `y_web/utils/` | `feeds.py` | 34 | RSS feed fetch helper |
| `y_web/utils/` | `y_server_process_runner.py` | 84 | Server simulation runner |
| `y_web/recsys_support/` | `content_recsys.py` | 128 | Post recommendation algorithms |
| `y_web/recsys_support/` | `follow_recsys.py` | 231 | Follow recommendation algorithms |
| `y_web/llm_annotations/` | `content_annotation.py` | 233 | LLM emotion / topic annotation |
| `y_web/llm_annotations/` | `image_annotator.py` | 101 | LLM image description |
| `y_web/reddit/` | `actions.py` | 954 | Forum write actions |
| `y_web/reddit/` | `service.py` | 1,425 | Forum read / display service |
| `y_web/reddit/` | `hot_rank.py` | 110 | Hot-score ranking algorithm |

### 1.2 Identified Problems

#### P1 — `utils/` is a catch-all bucket (26 files, ≈11,000 lines)

`utils/` contains code from at least seven unrelated domains:

- **Simulation process management**: `external_processes.py`, `y_client_process_runner.py`, `y_server_process_runner.py`, `execution_backend.py`
- **Process monitoring**: `process_watchdog.py`
- **Experiment management**: `experiment_access.py`, `experiment_clock.py`, `experiment_helpers.py`, `experiment_schema.py`, `experiment_schedule_monitor.py`
- **HPC operations**: `hpc_population_backup.py`, `log_metrics.py`, `log_sync_scheduler.py`
- **Content utilities**: `text_utils.py`, `article_extractor.py`, `feeds.py`, `avatars.py`
- **Agent/population generation**: `agents.py`, `population_platform.py`
- **System infrastructure**: `path_utils.py`, `miscellanea.py`, `check_release.py`, `check_blog.py`, `desktop_file_handler.py`, `jupyter_utils.py`

#### P2 — `external_processes.py` is a god object (3,170 lines)

A single file manages seven distinct concerns:

1. **Process registry** — `_register_process`, `_unregister_process`, `cleanup_*`
2. **Port management** — `_is_port_available`, `_find_new_available_port`, `_get_ports_allocated_to_experiments`
3. **Standard server lifecycle** — `start_server`, `terminate_server_process`
4. **Standard client lifecycle** — `start_client`, `terminate_client`
5. **HPC server lifecycle** — `start_hpc_server`, `stop_hpc_server`
6. **HPC client lifecycle** — `start_hpc_client`, `stop_hpc_client`
7. **LLM runtime management** — Ollama install/start/pull/delete, vLLM detection/start

#### P3 — `log_metrics.py` spans two concerns (1,690 lines)

The file mixes low-level log parsing logic with higher-level metric persistence
and HPC experiment completion detection.

#### P4 — `models.py` is a monolith (1,383 lines, 60+ classes)

All ORM classes—experiment simulation models, admin/researcher models, and
lookup/configuration tables—are declared in one file with no internal grouping.

#### P5 — `data_access.py` is a flat bag of queries (1,495 lines)

Fourteen independent query families (posts, users, hashtags, trends, emotions,
topics, mentions, profile pictures …) are declared as top-level functions with no
logical grouping.

#### P6 — `reddit/actions.py` mixes write concerns (954 lines)

The file conflates four domains: voting/reactions, comment and post creation,
media handling (image download, format conversion, URL detection), and NLP
annotation triggering.

#### P7 — `reddit/service.py` mixes read concerns (1,425 lines)

The file conflates five domains: display data classes, SQLAlchemy query helpers,
feed construction, time/display formatting, and text clean-up utilities.

#### P8 — `recsys_support/` and `llm_annotations/` have inconsistent naming

Both packages follow a `<domain>_support` / `<domain>_annotations` naming
pattern that is less clear than plain domain names (`recsys`, `llm`).

#### P9 — `reddit/` is named after an external platform

The package implements the generic *forum* platform; its name couples the
codebase to one specific third-party service name.

---

## 2. Proposed Package Architecture

The guiding principles are:

- **Single responsibility**: each package and each module covers one domain.
- **Stable public API**: every refactored module exposes the same names at the
  same import path as before; backward-compatibility shims ensure no call site
  outside `y_web/` needs to change.
- **Incremental deliverability**: phases are ordered from lowest to highest risk so
  each phase can be reviewed and merged independently.

### 2.1 Target Structure

```
y_web/
├── __init__.py                         # Flask app factory (unchanged)
├── experiment_context.py               # Remains at top level (already clean)
│
├── models/                             # Replaces models.py
│   ├── __init__.py                     # Re-exports every model class
│   ├── experiment.py                   # Simulation-DB models
│   ├── admin.py                        # Admin / researcher models
│   └── config.py                       # Lookup tables (Profession, Education …)
│
├── data_access/                        # Replaces data_access.py
│   ├── __init__.py                     # Re-exports every query function
│   ├── posts.py                        # Post / thread queries
│   ├── users.py                        # User / social-graph queries
│   ├── trends.py                       # Trending hashtags / emotions / topics
│   └── profiles.py                     # Profile picture helpers
│
├── experiment/                         # New – consolidates experiment concerns
│   ├── __init__.py                     # Re-exports
│   ├── context.py                      # Moved from experiment_context.py
│   ├── access.py                       # Moved from utils/experiment_access.py
│   ├── clock.py                        # Moved from utils/experiment_clock.py
│   ├── helpers.py                      # Moved from utils/experiment_helpers.py
│   ├── schema.py                       # Moved from utils/experiment_schema.py
│   └── schedule_monitor.py             # Moved from utils/experiment_schedule_monitor.py
│
├── agents/                             # New – agent / population generation
│   ├── __init__.py                     # Re-exports
│   ├── population.py                   # Moved from utils/agents.py
│   └── platform.py                     # Moved from utils/population_platform.py
│
├── simulation/                         # New – splits external_processes.py
│   ├── __init__.py                     # Re-exports start_server, start_client …
│   ├── process_registry.py             # _register_process, _unregister_process, cleanup_*
│   ├── port_manager.py                 # Port allocation helpers
│   ├── server.py                       # Standard server lifecycle
│   ├── client.py                       # Standard client lifecycle
│   ├── process_runner.py               # Merges y_client/y_server_process_runner.py
│   ├── network.py                      # Network bootstrap (generate_network*)
│   ├── execution_backend.py            # Moved from utils/execution_backend.py
│   └── watchdog.py                     # Moved from utils/process_watchdog.py
│
├── hpc/                                # New – HPC-specific operations
│   ├── __init__.py                     # Re-exports
│   ├── server.py                       # start_hpc_server, stop_hpc_server
│   ├── client.py                       # start_hpc_client, stop_hpc_client
│   ├── population_backup.py            # Moved from utils/hpc_population_backup.py
│   ├── log_parser.py                   # parse_server/client_log_incremental (split from log_metrics.py)
│   ├── log_metrics.py                  # Metrics persistence (update_*_log_metrics)
│   └── log_sync_scheduler.py           # Moved from utils/log_sync_scheduler.py
│
├── llm/                                # Replaces llm_annotations/ + Ollama/vLLM from external_processes.py
│   ├── __init__.py                     # Re-exports Annotator, ContentAnnotator
│   ├── content_annotation.py           # Moved from llm_annotations/
│   ├── image_annotator.py              # Moved from llm_annotations/
│   ├── ollama_manager.py               # Extracted from utils/external_processes.py
│   └── vllm_manager.py                 # Extracted from utils/external_processes.py
│
├── forum/                              # Replaces reddit/ with domain-neutral name
│   ├── __init__.py                     # Re-exports
│   ├── hot_rank.py                     # Unchanged
│   ├── actions/                        # Splits reddit/actions.py
│   │   ├── __init__.py                 # Re-exports create_post_reddit, apply_vote …
│   │   ├── posts.py                    # create_post_reddit, create_comment_reddit
│   │   ├── reactions.py                # apply_vote, _calculate_vote_tallies
│   │   └── media.py                    # Image download, URL detection, article handling
│   └── service/                        # Splits reddit/service.py
│       ├── __init__.py                 # Re-exports feed functions
│       ├── data_classes.py             # FeedPost, PostStats, ArticlePreview, FeedPage
│       ├── queries.py                  # fetch_feed_page, build_user_feed_posts, _*_subquery
│       └── formatters.py               # Time / text / image display formatting
│
├── recsys/                             # Replaces recsys_support/
│   ├── __init__.py                     # Re-exports get_suggested_posts, get_suggested_users
│   ├── content_recsys.py               # Moved unchanged from recsys_support/
│   └── follow_recsys.py                # Moved unchanged from recsys_support/
│
├── content/                            # New – content/text utility functions
│   ├── __init__.py                     # Re-exports
│   ├── text_utils.py                   # Moved from utils/
│   ├── article_extractor.py            # Moved from utils/
│   ├── feeds.py                        # Moved from utils/
│   └── avatars.py                      # Moved from utils/
│
├── system/                             # New – system / infrastructure utilities
│   ├── __init__.py                     # Re-exports
│   ├── path_utils.py                   # Moved from utils/
│   ├── miscellanea.py                  # Moved from utils/
│   ├── check_release.py                # Moved from utils/
│   ├── check_blog.py                   # Moved from utils/
│   ├── desktop_file_handler.py         # Moved from utils/
│   └── jupyter_utils.py                # Moved from utils/
│
└── utils/                              # Kept as a backward-compatibility shim
    └── __init__.py                     # Re-exports from new locations (deprecated)
```

### 2.2 Mapping: Old → New

| Old path | New path | Notes |
|---|---|---|
| `y_web/models.py` | `y_web/models/` | Packages split by model group |
| `y_web/data_access.py` | `y_web/data_access/` | Split by query subject |
| `y_web/experiment_context.py` | `y_web/experiment/context.py` | Moved into `experiment/` |
| `y_web/utils/experiment_access.py` | `y_web/experiment/access.py` | — |
| `y_web/utils/experiment_clock.py` | `y_web/experiment/clock.py` | — |
| `y_web/utils/experiment_helpers.py` | `y_web/experiment/helpers.py` | — |
| `y_web/utils/experiment_schema.py` | `y_web/experiment/schema.py` | — |
| `y_web/utils/experiment_schedule_monitor.py` | `y_web/experiment/schedule_monitor.py` | — |
| `y_web/utils/agents.py` | `y_web/agents/population.py` | Renamed |
| `y_web/utils/population_platform.py` | `y_web/agents/platform.py` | Moved |
| `y_web/utils/external_processes.py` (registry) | `y_web/simulation/process_registry.py` | Split out |
| `y_web/utils/external_processes.py` (ports) | `y_web/simulation/port_manager.py` | Split out |
| `y_web/utils/external_processes.py` (server) | `y_web/simulation/server.py` | Split out |
| `y_web/utils/external_processes.py` (client) | `y_web/simulation/client.py` | Split out |
| `y_web/utils/external_processes.py` (network) | `y_web/simulation/network.py` | Split out |
| `y_web/utils/y_client_process_runner.py` | `y_web/simulation/process_runner.py` | Merged with server runner |
| `y_web/utils/y_server_process_runner.py` | `y_web/simulation/process_runner.py` | Merged with client runner |
| `y_web/utils/execution_backend.py` | `y_web/simulation/execution_backend.py` | Moved |
| `y_web/utils/process_watchdog.py` | `y_web/simulation/watchdog.py` | Moved |
| `y_web/utils/external_processes.py` (HPC server) | `y_web/hpc/server.py` | Split out |
| `y_web/utils/external_processes.py` (HPC client) | `y_web/hpc/client.py` | Split out |
| `y_web/utils/hpc_population_backup.py` | `y_web/hpc/population_backup.py` | Moved |
| `y_web/utils/log_metrics.py` (parsing) | `y_web/hpc/log_parser.py` | Split out |
| `y_web/utils/log_metrics.py` (persistence) | `y_web/hpc/log_metrics.py` | Split out |
| `y_web/utils/log_sync_scheduler.py` | `y_web/hpc/log_sync_scheduler.py` | Moved |
| `y_web/utils/external_processes.py` (Ollama) | `y_web/llm/ollama_manager.py` | Extracted |
| `y_web/utils/external_processes.py` (vLLM) | `y_web/llm/vllm_manager.py` | Extracted |
| `y_web/llm_annotations/content_annotation.py` | `y_web/llm/content_annotation.py` | Moved |
| `y_web/llm_annotations/image_annotator.py` | `y_web/llm/image_annotator.py` | Moved |
| `y_web/reddit/hot_rank.py` | `y_web/forum/hot_rank.py` | Moved |
| `y_web/reddit/actions.py` (posts) | `y_web/forum/actions/posts.py` | Split |
| `y_web/reddit/actions.py` (reactions) | `y_web/forum/actions/reactions.py` | Split |
| `y_web/reddit/actions.py` (media) | `y_web/forum/actions/media.py` | Split |
| `y_web/reddit/service.py` (data classes) | `y_web/forum/service/data_classes.py` | Split |
| `y_web/reddit/service.py` (queries) | `y_web/forum/service/queries.py` | Split |
| `y_web/reddit/service.py` (formatters) | `y_web/forum/service/formatters.py` | Split |
| `y_web/recsys_support/content_recsys.py` | `y_web/recsys/content_recsys.py` | Package renamed |
| `y_web/recsys_support/follow_recsys.py` | `y_web/recsys/follow_recsys.py` | Package renamed |
| `y_web/utils/text_utils.py` | `y_web/content/text_utils.py` | Moved |
| `y_web/utils/article_extractor.py` | `y_web/content/article_extractor.py` | Moved |
| `y_web/utils/feeds.py` | `y_web/content/feeds.py` | Moved |
| `y_web/utils/avatars.py` | `y_web/content/avatars.py` | Moved |
| `y_web/utils/path_utils.py` | `y_web/system/path_utils.py` | Moved |
| `y_web/utils/miscellanea.py` | `y_web/system/miscellanea.py` | Moved |
| `y_web/utils/check_release.py` | `y_web/system/check_release.py` | Moved |
| `y_web/utils/check_blog.py` | `y_web/system/check_blog.py` | Moved |
| `y_web/utils/desktop_file_handler.py` | `y_web/system/desktop_file_handler.py` | Moved |
| `y_web/utils/jupyter_utils.py` | `y_web/system/jupyter_utils.py` | Moved |

---

## 3. Phased Implementation Plan

Each phase is self-contained and must pass validation before the next one starts.
Phases 1–4 are purely additive (new packages alongside old files) and carry minimal
risk.  Phases 5–9 restructure larger or more interconnected files and carry
progressively more risk.

---

### Phase 1 — Split `models.py` into a package

**Goal**: replace the monolithic `y_web/models.py` with `y_web/models/` while
keeping every existing `from y_web.models import SomeModel` import working.

**Steps**:

1. Create the directory `y_web/models/`.
2. Create `y_web/models/experiment.py` containing the experiment-simulation ORM classes:
   `User_mgmt`, `Post`, `Hashtags`, `Emotions`, `Post_emotions`, `Post_hashtags`,
   `Mentions`, `ReplyInboxState`, `Reactions`, `Follow`, `Rounds`,
   `Recommendations`, `Articles`, `Websites`, `Voting`, `Interests`,
   `User_interest`, `Post_topics`, `Images`, `ImagePosts`, `Article_topics`,
   `Post_Sentiment`, `Post_Toxicity`, `Agent_Opinion`.
3. Create `y_web/models/admin.py` containing the admin/researcher ORM classes:
   `Admin_users`, `AdminInterviewSession`, `AdminInterviewMessage`, `Exps`,
   `ExperimentScheduleGroup`, `ExperimentScheduleItem`, `ExperimentScheduleStatus`,
   `ExperimentScheduleLog`, `Exp_stats`, `Population`, `Agent`, `Agent_Population`,
   `Agent_Profile`, `Page`, `Population_Experiment`, `Page_Population`,
   `User_Experiment`, `Client`, `Client_Execution`, `Ollama_Pull`,
   `ReleaseInfo`, `BlogPost`, `DownloadNotification`, `Jupyter_instances`.
4. Create `y_web/models/config.py` containing lookup/configuration tables:
   `Profession`, `Nationalities`, `Education`, `Leanings`, `Languages`,
   `Toxicity_Levels`, `AgeClass`, `Content_Recsys`, `Follow_Recsys`,
   `Topic_List`, `Exp_Topic`, `Page_Topic`, `ActivityProfile`,
   `PopulationActivityProfile`.
5. Create `y_web/models/__init__.py` that imports and re-exports all classes from the
   three sub-modules.
6. **Do not delete** `y_web/models.py` yet; convert it to a thin shim that does
   `from y_web.models import *` so older import sites continue to work during
   transition.

**Estimated effort**: 1–2 hours  
**Risk**: Low — ORM class definitions carry no mutable state.

---

### Phase 2 — Split `data_access.py` into a package

**Goal**: replace `y_web/data_access.py` with `y_web/data_access/` organized by
query subject.

**Steps**:

1. Create the directory `y_web/data_access/`.
2. Create `y_web/data_access/profiles.py` with `get_safe_profile_pic`.
3. Create `y_web/data_access/posts.py` with `get_user_recent_posts`,
   `augment_text`, `get_posts_associated_to_hashtags`,
   `get_posts_associated_to_interest`, `get_posts_associated_to_emotion`,
   `get_elicited_emotions`, `get_topics`, `get_unanswered_mentions`.
4. Create `y_web/data_access/users.py` with `get_user_friends`,
   `get_mutual_friends`, `get_user_recent_interests`.
5. Create `y_web/data_access/trends.py` with `get_trending_hashtags`,
   `get_trending_emotions`, `get_trending_topics`, `get_top_user_hashtags`.
6. Create `y_web/data_access/__init__.py` re-exporting all public functions.
7. Convert `y_web/data_access.py` to a shim.

**Estimated effort**: 2–3 hours  
**Risk**: Low-medium — functions have stable signatures; the risk is in missing an
import in the `__init__.py` re-export list.

---

### Phase 3 — Create `experiment/` package

**Goal**: move all experiment-management code out of `utils/` into a dedicated
`y_web/experiment/` package.

**Steps**:

1. Create `y_web/experiment/`.
2. Move (copy then verify, delete original only after tests pass):
   - `y_web/experiment_context.py` → `y_web/experiment/context.py`
   - `y_web/utils/experiment_access.py` → `y_web/experiment/access.py`
   - `y_web/utils/experiment_clock.py` → `y_web/experiment/clock.py`
   - `y_web/utils/experiment_helpers.py` → `y_web/experiment/helpers.py`
   - `y_web/utils/experiment_schema.py` → `y_web/experiment/schema.py`
   - `y_web/utils/experiment_schedule_monitor.py` → `y_web/experiment/schedule_monitor.py`
3. Update intra-package imports in each moved file.
4. Create `y_web/experiment/__init__.py` with re-exports.
5. Add shim code to each original location.

**Estimated effort**: 2–3 hours  
**Risk**: Low — each file is small and well-defined.

---

### Phase 4 — Create `agents/`, `content/`, `recsys/`, and `system/` packages

**Goal**: extract four groups of small, self-contained modules out of `utils/` and
rename `recsys_support/`.

**Sub-steps (can be done in parallel)**:

#### 4a — `agents/`
Move `utils/agents.py` → `agents/population.py` and
`utils/population_platform.py` → `agents/platform.py`.

#### 4b — `content/`
Move `utils/text_utils.py`, `utils/article_extractor.py`, `utils/feeds.py`,
`utils/avatars.py` into `content/`.

#### 4c — `recsys/`
Copy `recsys_support/content_recsys.py` and `recsys_support/follow_recsys.py`
into `recsys/`.  Add shim `__init__.py` to `recsys_support/`.

#### 4d — `system/`
Move `utils/path_utils.py`, `utils/miscellanea.py`, `utils/check_release.py`,
`utils/check_blog.py`, `utils/desktop_file_handler.py`, `utils/jupyter_utils.py`
into `system/`.

Each sub-step follows the same pattern: copy, update imports, add `__init__.py`,
leave a shim at the old location.

**Estimated effort**: 3–4 hours  
**Risk**: Low — all modules are small and have few inter-module dependencies.

---

### Phase 5 — Create `llm/` package

**Goal**: consolidate LLM annotation classes from `llm_annotations/` with LLM
runtime management extracted from `external_processes.py`.

**Steps**:

1. Create `y_web/llm/`.
2. Move `llm_annotations/content_annotation.py` → `llm/content_annotation.py`.
3. Move `llm_annotations/image_annotator.py` → `llm/image_annotator.py`.
4. Extract the Ollama management functions from `external_processes.py`
   (`is_ollama_installed`, `is_ollama_running`, `start_ollama_server`,
   `pull_ollama_model`, `start_ollama_pull`, `get_ollama_models`,
   `delete_ollama_model`, `delete_model_pull`) into `llm/ollama_manager.py`.
5. Extract the vLLM management functions (`is_vllm_installed`, `is_vllm_running`,
   `start_vllm_server`, `get_vllm_models`, `get_llm_models`) into
   `llm/vllm_manager.py`.
6. Create `llm/__init__.py` re-exporting `Annotator`, `ContentAnnotator` and the
   manager functions.
7. Replace extracted functions in `external_processes.py` with thin delegating
   imports; add shim to `llm_annotations/__init__.py`.

**Estimated effort**: 3–4 hours  
**Risk**: Medium — extraction from `external_processes.py` requires careful
identification of internal helpers used only by the extracted functions.

---

### Phase 6 — Create `hpc/` package

**Goal**: group all HPC-specific logic into a dedicated package.

**Steps**:

1. Create `y_web/hpc/`.
2. Move `utils/hpc_population_backup.py` → `hpc/population_backup.py`.
3. Move `utils/log_sync_scheduler.py` → `hpc/log_sync_scheduler.py`.
4. Extract the HPC server functions (`start_hpc_server`, `stop_hpc_server`,
   `start_server_screen`) from `external_processes.py` into `hpc/server.py`.
5. Extract the HPC client functions (`start_hpc_client`, `stop_hpc_client`) from
   `external_processes.py` into `hpc/client.py`.
6. Split `utils/log_metrics.py` into two files:
   - `hpc/log_parser.py` — raw log parsing functions
     (`parse_server_log_incremental`, `parse_client_log_incremental`,
     `get_rotating_log_files`, `has_server_log_files`).
   - `hpc/log_metrics.py` — metric persistence and completion detection
     (`update_server_log_metrics`, `update_client_log_metrics`,
     `check_hpc_client_execution_completion`, `monitor_hpc_client_execution_logs`).
7. Create `hpc/__init__.py` re-exporting the most-used public symbols.
8. Replace extracted functions in their old locations with thin delegating imports.

**Estimated effort**: 4–6 hours  
**Risk**: Medium-high — `log_metrics.py` has many internal cross-references between
parsing and persistence; the split boundary must be identified carefully.

---

### Phase 7 — Create `simulation/` package

**Goal**: fully decompose `external_processes.py` (the largest risk in this
refactoring) into cohesive submodules.

**Steps**:

1. Create `y_web/simulation/`.
2. Extract `process_registry.py`: `_register_process`, `_unregister_process`,
   `cleanup_server_processes_from_db`, `cleanup_client_processes_from_db`,
   `stop_all_exps`.
3. Extract `port_manager.py`: `_is_port_available`, `_get_ports_allocated_to_experiments`,
   `_find_new_available_port`, `_find_available_port`, `terminate_process_on_port`,
   `_terminate_processes_on_port`.
4. Extract `server.py`: `start_server`, `terminate_server_process`,
   `get_server_process_status`, `_register_server_with_watchdog`,
   `_update_server_port_in_configs`, internal environment-detection helpers
   (`detect_env_handler`, `build_screen_command`).
5. Extract `client.py`: `start_client`, `terminate_client`, `_is_client_process`,
   `_register_client_with_watchdog`.
6. Extract `network.py`: network generation entry points (`generate_network`,
   `generate_reddit_network` and any helpers from `external_processes.py` and
   `y_client_process_runner.py`).
7. Merge `y_client_process_runner.py` and `y_server_process_runner.py` into
   `process_runner.py`.
8. Move `utils/execution_backend.py` → `simulation/execution_backend.py`.
9. Move `utils/process_watchdog.py` → `simulation/watchdog.py`.
10. Create `simulation/__init__.py` re-exporting `start_server`, `start_client`,
    `terminate_server_process`, `terminate_client`, and `stop_all_exps`.
11. Replace all remaining code in `external_processes.py` with import-delegation
    shims.

**Estimated effort**: 6–8 hours  
**Risk**: High — `external_processes.py` has complex shared state (process registry
dict), subtle HPC/non-HPC branches, and many callers in `routes/`.  The process
registry module must be the first submodule created to avoid circular dependencies.

---

### Phase 8 — Reorganize `forum/` (rename + split `reddit/`)

**Goal**: give the forum platform a domain-neutral name and break its two large
files into focused submodules.

**Steps**:

1. Create `y_web/forum/`.
2. Copy `reddit/hot_rank.py` → `forum/hot_rank.py` (no changes needed).
3. Split `reddit/actions.py`:
   - `forum/actions/media.py`: URL detection helpers (`_looks_like_*`,
     `_extract_candidate_media_url`, `_remote_looks_like_image`,
     `_download_image_to_uploads`), article handling.
   - `forum/actions/reactions.py`: `apply_vote`, `_calculate_vote_tallies`.
   - `forum/actions/posts.py`: `create_post_reddit`, `create_comment_reddit`,
     helper functions `_normalize_comment_for_dedupe`, `_comment_dedupe_key`,
     `_ensure_experiment_context`, `_get_current_round`.
   - `forum/actions/__init__.py`: re-exports public symbols.
4. Split `reddit/service.py`:
   - `forum/service/data_classes.py`: `ArticlePreview`, `PostStats`, `FeedPost`,
     `FeedPage`, `_article_payload`.
   - `forum/service/formatters.py`: time/text/image formatting functions
     (`clean_reddit_formatting`, `extract_reddit_summary_image`,
     `_format_display_time*`, `_resolve_article`, `_resolve_image*`,
     `_media_type_from_url`, `_upgrade_reddit_image_url`, `_strip_article_title_from_body`).
   - `forum/service/queries.py`: feed construction and DB query helpers
     (`fetch_feed_page`, `build_user_feed_posts`, `serialize_feed_posts`,
     `_*_subquery`, `_fetch_*_map`, `_build_feed_posts`, `_create_feed_post`,
     `fetch_thread`).
   - `forum/service/__init__.py`: re-exports.
5. Create `forum/__init__.py` re-exporting the public API.
6. Add a shim `reddit/__init__.py` re-exporting everything from `forum/`.

**Estimated effort**: 5–7 hours  
**Risk**: Medium-high — `service.py` has many internal helper dependencies that must
be partitioned correctly.

---

### Phase 9 — Clean up `utils/` shim

**Goal**: finalize the `utils/` package as a thin backward-compatibility shim.

**Steps**:

1. Replace every file that was moved with a one-liner re-export:
   ```python
   # Deprecated: use y_web.<new_package>.<module> instead
   from y_web.<new_package>.<module> import *  # noqa: F401,F403
   ```
2. Update `utils/__init__.py` to re-export the original public symbols.
3. Add deprecation warnings using `warnings.warn(... DeprecationWarning)` on the
   shim files so callers are notified during development.
4. Update all internal `y_web/routes/` callers to use the new import paths.
5. Update `y_web/__init__.py` to import from new paths.

**Estimated effort**: 2–3 hours  
**Risk**: Low — purely mechanical import-path updates.

---

## 4. Validation Steps

Apply the following checklist at the end of **every phase**:

### 4.1 Import Verification

Run a quick import check to ensure every public symbol is still reachable:

```bash
python - <<'EOF'
# Old-style imports must still work through shims
from y_web.models import User_mgmt, Post, Admin_users, Profession
from y_web.data_access import get_user_recent_posts, get_trending_hashtags
from y_web.utils.agents import generate_population_from_config
from y_web.utils.experiment_access import user_can_view_experiment
from y_web.utils.external_processes import start_server, start_client
from y_web.utils.log_metrics import update_client_log_metrics
from y_web.llm_annotations import Annotator, ContentAnnotator
from y_web.recsys_support import get_suggested_posts, get_suggested_users
from y_web.reddit.actions import create_post_reddit, apply_vote
from y_web.reddit.service import fetch_feed_page, serialize_feed_posts
print("All legacy imports OK")
EOF
```

### 4.2 New-Path Import Verification

After each phase, verify the new canonical paths also work:

```bash
python - <<'EOF'
# New canonical imports for each completed phase
# Phase 1
from y_web.models.experiment import User_mgmt, Post
from y_web.models.admin import Admin_users, Exps
from y_web.models.config import Profession, Education
# Phase 2
from y_web.data_access.posts import get_user_recent_posts
from y_web.data_access.trends import get_trending_hashtags
# (continue for each completed phase)
print("All new-path imports OK")
EOF
```

### 4.3 Unit Test Suite

```bash
cd y_web
python -m pytest tests/ -x -q
```

All tests must pass.  Pay special attention to:

- `tests/test_utils.py`, `tests/test_utils_comprehensive.py` — generic utils
- `tests/test_recsys_support.py` — recommendation system
- `tests/test_llm_annotations.py`, `tests/test_llm_backend.py` — LLM layer
- `tests/test_forum_*.py` — forum / Reddit functionality
- `tests/test_external_processes_env.py`, `tests/test_process_watchdog.py` — process management
- `tests/test_hpc_*.py` — HPC path
- `tests/test_incremental_log_reading.py` — log metrics
- `tests/test_app_structure.py` — Flask application structure

### 4.4 Circular Import Check

```bash
python -c "import y_web" 2>&1 | grep -i "circular\|ImportError" && echo "FAIL" || echo "OK"
```

### 4.5 Flask Application Start-up

```bash
FLASK_APP=y_social.py flask --app y_social shell -c "print('Flask context OK')"
```

### 4.6 Static Analysis

```bash
# Check for unresolved imports
python -m py_compile y_web/**/*.py

# Optional: run flake8 on changed files only
flake8 y_web/<changed_package>/ --select=E,F --max-line-length=120
```

---

## 5. Regression-Prevention Strategy

### 5.1 Backward-Compatibility Shims

Every original import path **must** continue to work after the refactoring.
Shim files use `from new.location import *` so they require zero changes in any
external code.  Shims are explicitly marked as deprecated to drive gradual
migration by contributors.

### 5.2 Incremental, Reviewable Phases

Each phase produces one focused pull request.  The PR diff contains only:
- New package directory with moved/split files
- A shim at the old location
- Updated imports within moved files

No logic changes are made during a phase.  Logic changes happen in separate PRs.

### 5.3 Test Coverage Before Moving Files

Before touching any file in a phase, verify existing test coverage:

```bash
python -m pytest tests/ -q --tb=no -q 2>&1 | tail -5
```

Record the passing count.  After the phase, re-run and confirm the same or higher
count.

### 5.4 Git Discipline

- Each phase is committed as a **single atomic commit** (or a small sequence if
  sub-steps are large).
- Commit message format: `refactor(phase-N): <brief description>`.
- Use `git mv` for file moves so history is preserved.

### 5.5 Import-Shadowing Check

Python's package shadowing rules can cause a `models/` directory to shadow the
old `models.py` silently.  Verify that the shim is not bypassed:

```bash
python -c "import y_web.models; print(y_web.models.__file__)"
# Must print the __init__.py path, not the old .py file
```

### 5.6 CI Pipeline Enforcement

Add a CI step that runs the import verification script (§ 4.1 and § 4.2) and the
unit tests after every push to a refactoring branch.  The CI step must pass before
merge.

### 5.7 Feature-Flag Isolation (Optional but Recommended for Phases 7–8)

For the highest-risk phases (simulation/ decomposition and forum/ split), consider
wrapping the new import paths behind a thin feature flag:

```python
# y_web/__init__.py or conftest.py
import os
USE_NEW_SIMULATION_PACKAGE = os.getenv("YSOCIAL_NEW_SIM_PKG", "0") == "1"
```

This allows the new package to be exercised in CI without affecting the running
production instance until all phases are complete and stable.

---

## Summary

| Phase | Scope | Effort | Risk |
|---|---|---|---|
| 1 | Split `models.py` | 1–2 h | Low |
| 2 | Split `data_access.py` | 2–3 h | Low-medium |
| 3 | Create `experiment/` package | 2–3 h | Low |
| 4 | Create `agents/`, `content/`, `recsys/`, `system/` | 3–4 h | Low |
| 5 | Create `llm/` package | 3–4 h | Medium |
| 6 | Create `hpc/` package | 4–6 h | Medium-high |
| 7 | Create `simulation/` package | 6–8 h | High |
| 8 | Reorganize `forum/` (rename `reddit/`) | 5–7 h | Medium-high |
| 9 | Clean up `utils/` shim | 2–3 h | Low |
| **Total** | | **~28–40 h** | |

Phases 1–4 can be completed and merged within the first week with minimal
coordination overhead.  Phases 5–8 should be scheduled with dedicated review time
and run with the full test suite before each merge.  Phase 9 is a clean-up pass
that can follow once phases 5–8 are stable.
