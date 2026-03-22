# YSocial — Comprehensive Refactoring Analysis

**Date:** 2026-03-22  
**Branch:** `copilot/refactor-business-logic-scripts`  
**Scope:** Whole-project analysis covering `y_web/` Python package

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Completed Work — Phases 0-9](#2-completed-work--phases-0-9)
3. [Current State Assessment](#3-current-state-assessment)
4. [Remaining Issues](#4-remaining-issues)
5. [Proposed Future Phases](#5-proposed-future-phases)
   - [Phase 10 — Split Large Route Files](#phase-10--split-large-route-files)
   - [Phase 11 — Split `__init__.py` App Factory](#phase-11--split-__init__py-app-factory)
   - [Phase 12 — Split Large `src/` Modules](#phase-12--split-large-src-modules)
   - [Phase 13 — Routes / API Coverage Completion](#phase-13--routes--api-coverage-completion)
6. [Regression-Prevention Strategy](#6-regression-prevention-strategy)
7. [Validation Reference](#7-validation-reference)

---

## 1. Executive Summary

YSocial has undergone a major structural refactoring (Phases 0–9) that successfully
migrated ~16 000 lines of business logic out of a flat `utils/` catch-all directory
and into a well-structured `y_web/src/` package tree.  All legacy shim packages have
been removed; every internal caller uses the canonical `y_web.src.*` import paths.
The test suite has grown to ~100 files covering the new structure.

**What remains:**

| Area | Issue | Severity |
|---|---|---|
| `routes/admin/sub/experiments.py` | 10 352-line god object | **High** |
| `routes/admin/sub/clients.py` | 6 336-line god object | **High** |
| `routes/api/interview.py` | 3 676-line mixed-concern file | **Medium** |
| `y_web/__init__.py` | 1 243-line app factory with embedded DB logic | **Medium** |
| `src/simulation/process_runner.py` | 1 054-line mixed-concern module | **Medium** |
| `src/hpc/log_parser.py` | 942-line module (parseable into sub-tasks) | **Low** |
| Test markers | `unit` / `integration` / `slow` markers declared but unused | **Low** |

---

## 2. Completed Work — Phases 0-9

The following phases have been completed and are documented in
[`BUSINESS_LOGIC_REFACTORING.md`](BUSINESS_LOGIC_REFACTORING.md).

| Phase | Deliverable | Tests |
|---|---|---|
| 0 | `y_web/src/__init__.py` namespace root | — |
| 1 | `src/models/` split: `admin.py`, `experiment.py`, `config.py` | `test_phase1_src_models.py` (22 tests) |
| 2 | `src/data_access/` split: `posts.py`, `users.py`, `profiles.py`, `trends.py` | `test_phase2_src_data_access.py` (31 tests) |
| 3 | `src/experiment/`: `context.py`, `access.py`, `clock.py`, `helpers.py`, `schema.py`, `schedule_monitor.py` | `test_phase3_src_experiment.py` (45 tests) |
| 4 | `src/agents/`, `src/content/`, `src/recsys/`, `src/telemetry/`, `src/system/` | `test_phase4_src_packages.py` (60 tests) |
| 5 | `src/llm/`: `content_annotation.py`, `image_annotator.py`, `ollama_manager.py`, `vllm_manager.py` | `test_phase5_src_llm.py` |
| 6 | `src/hpc/`: `server.py`, `client.py`, `log_parser.py`, `log_metrics.py`, `log_sync_scheduler.py`, `population_backup.py` | `test_phase6_src_hpc.py` (36 tests) |
| 7 | `src/simulation/`: `process_registry.py`, `watchdog.py`, `execution_backend.py`, `port_manager.py`, `server.py`, `client.py`, `process_runner.py` | `test_phase7_src_simulation.py` (31 tests) |
| 8 | `src/forum/`: `hot_rank.py`, `actions/`, `service/` | `test_phase8_src_forum.py` (67 tests) |
| 9 + cleanup | `utils/` shim removed; all callers updated to `y_web.src.*` canonical imports | `test_phase9_utils_shim.py` |

**Result:** The legacy flat-file directories `utils/`, `reddit/`, `recsys_support/`,
and `llm_annotations/` have been completely removed.

---

## 3. Current State Assessment

### 3.1 Package Tree (post-Phase-9)

```
y_web/
├── __init__.py              1 243 lines  ← app factory + DB init (see §4.2)
├── src/
│   ├── models/              1 501 lines  ✔ well-split
│   ├── data_access/         1 740 lines  ✔ well-split
│   ├── experiment/          1 680 lines  ✔ well-split
│   ├── agents/              2 831 lines  ✔ reasonably sized
│   ├── content/             1 220 lines  ✔ well-split
│   ├── recsys/               530 lines  ✔ well-split
│   ├── telemetry/            467 lines  ✔ single-concern
│   ├── system/             2 040 lines  ✔ well-split
│   ├── llm/                  760 lines  ✔ well-split
│   ├── hpc/                2 720 lines  ← log_parser.py (942 L) warrants split (§4.4)
│   ├── forum/              5 000 lines  ✔ already sub-packaged
│   └── simulation/         5 600 lines  ← process_runner.py (1054 L) (§4.3)
├── routes/
│   ├── social/             2 700 lines  ✔ well-split
│   ├── interactions/       1 100 lines  ✔ well-split
│   ├── auth/                 240 lines  ✔ small
│   ├── errors/               180 lines  ✔ small
│   ├── api/
│   │   ├── interview.py    3 676 lines  ← large (§4.5)
│   │   └── reddit.py         919 lines  ✔ acceptable
│   └── admin/
│       ├── dashboard.py      661 lines  ✔ acceptable
│       └── sub/
│           ├── experiments.py  10 352 lines  ← CRITICAL (§4.1)
│           ├── clients.py       6 336 lines  ← HIGH    (§4.1)
│           ├── populations.py   1 214 lines  ✔ acceptable
│           ├── users.py         1 308 lines  ✔ acceptable
│           ├── tutorial.py      1 056 lines  ✔ acceptable
│           ├── pages.py           437 lines  ✔ small
│           ├── agents.py          370 lines  ✔ small
│           ├── jupyterlab.py      192 lines  ✔ small
│           └── ollama.py          153 lines  ✔ small
└── tests/                  ~100 files   ✔ good coverage
```

### 3.2 Import Hygiene

All internal callers use the canonical `y_web.src.*` paths.  
No remaining `from y_web.utils`, `from y_web.reddit`, `from y_web.recsys_support`
imports exist anywhere in the live codebase (confirmed by grep).

### 3.3 Template Structure

The `templates/` directory has already been reorganised into domain sub-folders:
`admin/`, `forum/`, `microblogging/`, `login/`, `error_pages/`.  This is complete.

---

## 4. Remaining Issues

### 4.1 God-Object Route Files (`experiments.py` and `clients.py`)

`routes/admin/sub/experiments.py` (10 352 lines) and
`routes/admin/sub/clients.py` (6 336 lines) are the largest files in the entire
codebase and violate the single-responsibility principle in the same way the
original `utils/external_processes.py` did before Phase 7.

**`experiments.py` concerns identified:**

| Concern | Approximate lines | Candidate module |
|---|---|---|
| Experiment CRUD (create, copy, upload, delete, settings) | ~2 500 | `admin/sub/experiments/_crud.py` |
| Opinion / LLM configuration | ~2 000 | `admin/sub/experiments/_opinion.py` |
| Feed / RSS / content configuration | ~1 500 | `admin/sub/experiments/_feeds.py` |
| Schedule group management | ~1 200 | `admin/sub/experiments/_schedule.py` |
| HPC-specific experiment actions | ~1 500 | `admin/sub/experiments/_hpc.py` |
| Notifications and download management | ~700 | `admin/sub/experiments/_notifications.py` |
| Shared helpers (`_normalize_*`, `_load_forum_*`, etc.) | ~950 | `admin/sub/experiments/_helpers.py` |

**`clients.py` concerns identified:**

| Concern | Approximate lines | Candidate module |
|---|---|---|
| Standard client CRUD and control | ~2 000 | `admin/sub/clients/_standard.py` |
| Forum client CRUD and control | ~1 500 | `admin/sub/clients/_forum.py` |
| HPC client CRUD and control | ~1 800 | `admin/sub/clients/_hpc.py` |
| Shared helpers and form processing | ~1 036 | `admin/sub/clients/_helpers.py` |

### 4.2 `y_web/__init__.py` App Factory (1 243 lines)

The application entry module mixes:
1. **Database initialisation** for SQLite (`create_app`) — ~400 lines
2. **Database initialisation** for PostgreSQL (`create_postgresql_db`) — ~250 lines
3. **Flask-Login / Blueprint wiring** — ~200 lines
4. **Atexit / cleanup logic** — ~100 lines
5. **Schema enforcement** helpers — ~150 lines

These concerns should be extracted into:

| Proposed file | Responsibility |
|---|---|
| `y_web/app.py` or `y_web/__init__.py` (kept small) | Flask `create_app()` — 50 lines max |
| `y_web/db_init/sqlite.py` | SQLite DB setup |
| `y_web/db_init/postgresql.py` | PostgreSQL DB setup |
| `y_web/db_init/__init__.py` | `init_db(app, db_type)` dispatcher |

### 4.3 `src/simulation/process_runner.py` (1 054 lines)

This module merges two original scripts (`y_client_process_runner.py` and
`y_server_process_runner.py`) and contains at least three distinct concerns:

| Concern | Functions | Candidate module |
|---|---|---|
| Server entry-point | `run_server_main` | `src/simulation/server_runner.py` (already exists as runner script — could hold logic too) |
| Client entry-point and agent sampling | `run_client_main`, `get_users_per_hour`, `sample_agents`, `ensure_agents_have_archetype`, `process_agent` | `src/simulation/agent_sampler.py` |
| Full simulation loop | `start_client_process`, `run_simulation` | `src/simulation/client_runner.py` (already exists) or keep in `process_runner.py` |

### 4.4 `src/hpc/log_parser.py` (942 lines)

Contains both parsing logic and database I/O:

| Concern | Functions | Candidate module |
|---|---|---|
| File offset tracking | `get_log_file_offset`, `update_log_file_offset` | `src/hpc/log_offset.py` |
| Server log parsing | `parse_server_log_incremental` | `src/hpc/server_log_parser.py` |
| Client log parsing | `parse_client_log_incremental`, `get_rotating_log_files`, `has_server_log_files` | `src/hpc/client_log_parser.py` |
| DB session helpers | `_ensure_session_clean`, `_commit_with_retry` | `src/hpc/_db_utils.py` or folded into `src/system/` |

### 4.5 `routes/api/interview.py` (3 676 lines)

The interview API file mixes:

| Concern | Approximate lines | Candidate module |
|---|---|---|
| Session management (create/list/get/end session) | ~800 | `routes/api/interview/_sessions.py` |
| Message exchange and LLM interaction | ~1 200 | `routes/api/interview/_messages.py` |
| Memory management (vector store, legacy) | ~700 | `routes/api/interview/_memory.py` |
| Export and reporting | ~400 | `routes/api/interview/_export.py` |
| Shared helpers | ~576 | `routes/api/interview/_helpers.py` |

### 4.6 Test Marker Discipline

The `pytest.ini` declares `unit`, `integration`, and `slow` markers, but very few
tests are actually decorated with `@pytest.mark.unit` etc.  This means the
selective-run features (`-m unit`) do not work.  Adding markers to existing tests
costs nothing and aids CI optimisation.

---

## 5. Proposed Future Phases

Each phase follows the same pattern as Phases 0–9:
1. Create new canonical sub-modules with the real code.
2. Replace the original file with a thin re-export shim (backward compatibility).
3. Write a focused `test_phaseN_*.py` test file confirming all public names
   are importable from both the old and the new paths.
4. Update all internal callers to use the canonical path.
5. Remove the shim in a follow-up cleanup commit.

---

### Phase 10 — Split Large Route Files

**Goal:** Reduce `experiments.py` and `clients.py` below ~1 500 lines each by
extracting cohesive sub-modules.

**Priority:** High — these are the most critical maintainability liabilities.

#### Step 10a — `experiments.py` → `admin/sub/experiments/` package

1. Create `routes/admin/sub/experiments/__init__.py` that re-exports the
   existing blueprint and all route functions (backward-compatible).
2. Extract helpers: `_helpers.py`
3. Extract opinion/LLM logic: `_opinion.py`
4. Extract feed/RSS logic: `_feeds.py`
5. Extract schedule logic: `_schedule.py`
6. Extract HPC logic: `_hpc.py`
7. Extract notifications logic: `_notifications.py`
8. Keep CRUD in `_crud.py` (the blueprint registration file).

**Validation:**
```bash
# All route functions still importable
python -c "from y_web.routes.admin.sub.experiments import experiments_bp"
# All url_for targets still resolve
pytest y_web/tests/test_admin_routes.py y_web/tests/test_app_structure.py -x
```

#### Step 10b — `clients.py` → `admin/sub/clients/` package

Same pattern as 10a.

**Validation:**
```bash
pytest y_web/tests/test_client_form_fields.py \
       y_web/tests/test_client_details_agent_type.py \
       y_web/tests/test_client_logs.py \
       y_web/tests/test_simulation_process_runner_logic.py -x
```

#### Step 10c — `routes/api/interview.py` → `routes/api/interview/` package

**Validation:**
```bash
pytest y_web/tests/test_interview_server_runtime.py -x
```

---

### Phase 11 — Split `__init__.py` App Factory

**Goal:** Reduce `y_web/__init__.py` from 1 243 lines to ~100 lines by extracting
database initialisation into `y_web/db_init/`.

#### Step 11a — Extract PostgreSQL DB setup

1. Create `y_web/db_init/__init__.py` with `init_db(app, db_type)` dispatcher.
2. Create `y_web/db_init/postgresql.py` with `create_postgresql_db(app)` logic.
3. In `y_web/__init__.py`, replace the inline function with:
   ```python
   from y_web.db_init.postgresql import create_postgresql_db  # noqa: F401
   ```

#### Step 11b — Extract SQLite DB setup

Move the SQLite path-calculation and schema-init block into
`y_web/db_init/sqlite.py`.

#### Step 11c — Extract blueprint wiring

Move `register_blueprints` into `y_web/routes/__init__.py` (it already handles
blueprint registration; the call site in `__init__.py` should be a 3-line call).

**Validation:**
```bash
# App still creates successfully in both modes
pytest y_web/tests/test_app_structure.py y_web/tests/test_auth_routes.py -x
python -c "from y_web import create_app; app = create_app('sqlite'); print('OK')"
```

---

### Phase 12 — Split Large `src/` Modules

**Goal:** Keep every `src/` leaf module below ~600 lines.

#### Step 12a — `src/simulation/process_runner.py`

Extract agent-sampling helpers into `src/simulation/agent_sampler.py`:

```
process_runner.py  →  process_runner.py  (simulation entry-points)
                   +  agent_sampler.py   (get_users_per_hour, sample_agents,
                                          ensure_agents_have_archetype, process_agent)
```

Update `src/simulation/__init__.py` lazy exports.

**Validation:**
```bash
pytest y_web/tests/test_simulation_process_runner_logic.py \
       y_web/tests/test_y_client_process_runner.py -x
```

#### Step 12b — `src/hpc/log_parser.py`

Extract file-offset helpers into `src/hpc/log_offset.py`:

```
log_parser.py  →  log_parser.py   (parse_*_log_incremental, get_rotating_log_files)
               +  log_offset.py   (get_log_file_offset, update_log_file_offset,
                                   reset_hpc_*_metrics, _ensure_session_clean,
                                   _commit_with_retry)
```

Update `src/hpc/__init__.py` exports.

**Validation:**
```bash
pytest y_web/tests/test_hpc_log_metrics_logic.py \
       y_web/tests/test_incremental_log_reading.py \
       y_web/tests/test_hpc_progress_tracking.py -x
```

---

### Phase 13 — Routes / API Coverage Completion

**Goal:** Confirm all blueprint URL endpoints are covered by at least one test
and add `@pytest.mark.unit` / `@pytest.mark.integration` decorators throughout.

#### Step 13a — Audit uncovered endpoints

```bash
# List all Flask route functions
grep -rn "@.*_bp\.route\|@.*\.route" y_web/routes/ --include="*.py" | wc -l
# Compare with grep of test files
grep -rn "client\.get\|client\.post" y_web/tests/ --include="*.py" | wc -l
```

#### Step 13b — Add pytest markers

For each test file, add one of:
```python
pytestmark = pytest.mark.unit          # pure-logic, no Flask/DB
pytestmark = pytest.mark.integration  # requires Flask test client / DB
```

**Validation:**
```bash
# Selective run should yield non-zero results
pytest -m unit -q
pytest -m integration -q
```

---

## 6. Regression-Prevention Strategy

### 6.1 The Shim Pattern

Every phase that **moves** code must leave a backward-compatible re-export shim at
the original import path.  The shim must:

1. Import every public name from the new canonical location.
2. Raise a `DeprecationWarning` only for *external* callers (not used internally).
3. Remain in place until all internal callers are updated.

```python
# Example shim — do not import this directly in new code
import warnings
warnings.warn(
    "Import from 'y_web.old_path' is deprecated; use 'y_web.src.new_path'.",
    DeprecationWarning,
    stacklevel=2,
)
from y_web.src.new_path import *  # noqa: F401,F403
```

### 6.2 Phase-Specific Test Files

Each phase must ship with a dedicated `test_phaseN_*.py` that:

- Imports every public name from both the **old** (shim) and **new** (canonical)
  paths and asserts they are the same object.
- Calls at least one non-trivial function to confirm the logic works.
- Passes `pytest` without network, filesystem, or external process side-effects.

### 6.3 Full Suite Baseline

Before starting any phase, record the current pass/fail baseline:

```bash
cd /path/to/repo
pytest y_web/tests/ -q --tb=no 2>&1 | tail -3
```

After completing the phase, re-run the full suite.  **Zero new failures** is the
acceptance criterion.

### 6.4 Blueprint Name Freeze

The following Flask blueprint names are hardcoded in `url_for()` calls across
Python **and** Jinja2 templates.  They **must not** be renamed during any
refactoring:

| Blueprint name | Registered in |
|---|---|
| `auth` | `routes/auth/routes.py` |
| `main` | `routes/social/_blueprint.py` |
| `user_actions` | `routes/interactions/_blueprint.py` |
| `admin` | `routes/admin/dashboard.py` |
| `errors` | `routes/errors/_blueprint.py` |
| `experiments` | `routes/admin/sub/experiments.py` |
| `clients` | `routes/admin/sub/clients.py` |
| `users` | `routes/admin/sub/users.py` |
| `api_reddit` | `routes/api/reddit.py` |
| `api_interview` | `routes/api/interview.py` |

### 6.5 CI Gating

The project uses `pytest.ini` with `--strict-markers`.  Any new marker used in a
test file must be declared in `pytest.ini` before use.

---

## 7. Validation Reference

The table below maps each proposed phase to its specific validation commands.

| Phase | Targeted tests | Full-suite indicator |
|---|---|---|
| 10a (experiments split) | `test_admin_routes.py`, `test_app_structure.py`, `test_copy_experiment*.py` | `pytest -q --tb=no \| tail -1` |
| 10b (clients split) | `test_client_form_fields.py`, `test_client_details*.py`, `test_client_logs.py` | same |
| 10c (interview split) | `test_interview_server_runtime.py` | same |
| 11 (init.py split) | `test_app_structure.py`, `test_auth_routes.py`, `test_simple_auth.py` | same |
| 12a (process_runner split) | `test_simulation_process_runner_logic.py`, `test_y_client_process_runner.py` | same |
| 12b (log_parser split) | `test_hpc_log_metrics_logic.py`, `test_incremental_log_reading.py` | same |
| 13 (markers + coverage) | all tests with `-m unit`, `-m integration` | same |

### Quick health check (run after any phase)

```bash
# Import all canonical src packages
python -c "
import y_web.src.models
import y_web.src.data_access
import y_web.src.experiment
import y_web.src.agents
import y_web.src.content
import y_web.src.recsys
import y_web.src.telemetry
import y_web.src.system
import y_web.src.llm
import y_web.src.hpc
import y_web.src.simulation
import y_web.src.forum
print('All src packages importable OK')
"

# Run phase-specific tests
pytest y_web/tests/test_phase1_src_models.py \
       y_web/tests/test_phase2_src_data_access.py \
       y_web/tests/test_phase3_src_experiment.py \
       y_web/tests/test_phase4_src_packages.py \
       y_web/tests/test_phase5_src_llm.py \
       y_web/tests/test_phase6_src_hpc.py \
       y_web/tests/test_phase7_src_simulation.py \
       y_web/tests/test_phase8_src_forum.py \
       y_web/tests/test_phase9_utils_shim.py \
       -v --tb=short
```

---

*This document supersedes the notes in `BUSINESS_LOGIC_REFACTORING.md` for future
work.  That document remains the authoritative record for the completed Phases 0–9.*
