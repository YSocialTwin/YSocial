# Test Coverage Plan — YSocial Refactoring

## Overview

This document reports on the current test coverage of the `y_web/src/` package tree
(the canonical location of all business logic after the Phase 0–9 refactoring) and
defines a phased plan for the additional tests needed to catch regressions, validate
behaviour, and guard against the class of bugs that were introduced — but not caught —
during the refactoring.

**Baseline (as of this analysis):**  
`1 091` tests collected · `1 046` passing · `46` skipped · `1` pre-existing failure  
Modules under `y_web/src/`: `66` Python files across `10` sub-packages

---

## Part 1 — Bugs Found That Were Not Caught by Existing Tests

These bugs were introduced by the refactoring and are not currently caught by any
unittest. They are fixed alongside this document.

### Bug 1 — `hpc/client.py`: missing `env=env` in both `subprocess.Popen` calls

**File:** `y_web/src/hpc/client.py` (lines 205 / 211)  
**Impact:** The HPC client subprocess inherits whatever `os.environ` is in the
interpreter, but the parent never builds a controlled `env` dict, so any environment
customisation (PYTHONPATH, conda activation, virtual-env markers) is never
explicitly forwarded. This is inconsistent with every other Popen call-site in the
codebase, which all build `env = os.environ.copy()` explicitly.  
**Why tests didn't catch it:** The phase-6 import tests and the feature tests for HPC
mock the subprocess or only test high-level outcomes; none inspects the keyword
arguments passed to `subprocess.Popen`.  
**Fix applied:** Added `env = os.environ.copy()` before the try-block and passed
`env=env` to both Popen calls (matching the pattern in `hpc/server.py`).

### Bug 2 — `simulation/server.py` SQLite path: missing `env=env` in both Popen calls

**File:** `y_web/src/simulation/server.py` (lines 806 / 816)  
**Impact:** The gunicorn/PostgreSQL path correctly builds `env` (with `YSERVER_CONFIG`
and `YSERVER_LOG_FILE`) and passes `env=env` to Popen. The SQLite path also built
`env` (setting `YSERVER_LOG_FILE`) but forgot to pass it, so the subprocess ran
without `YSERVER_LOG_FILE`.  
**Why tests didn't catch it:** `test_external_processes_env.py` only tests
`detect_env_handler()`; no test inspects the Popen kwargs on the SQLite code path.  
**Fix applied:** Added `env=env` to both Popen calls in the SQLite branch.

### Bug 3 — `hpc/server.py` SQLite path: missing `env=env` in both Popen calls

Same pattern as Bug 2; `YSERVER_CONFIG` was set in `env` but not forwarded.  
**Fix applied:** Added `env=env` to both Popen calls in the SQLite branch.

### Bug 4 — `client_runner.py` / `server_runner.py`: missing `sys.path` bootstrap

**File:** `y_web/src/simulation/client_runner.py`, `server_runner.py`  
**Impact:** When launched as a standalone subprocess entry-point
(`python /path/to/client_runner.py`), the repo root was not on `sys.path`, causing
`ModuleNotFoundError: No module named 'y_web'`.  
**Fix applied:** Added a `sys.path.insert(0, _REPO_ROOT)` block before the
`from y_web...` import.

---

## Part 2 — Root Cause Analysis: Why These Bugs Were Missed

1. **Phase tests verify structure, not behaviour.** The `test_phase*.py` suite checks
   that modules are importable, that public names exist, and that shim re-exports are
   correct. None exercises the actual logic of any function.

2. **Subprocess tests mock at a high level.** Tests like
   `test_pyinstaller_server_subprocess.py` patch `subprocess.Popen` to return a mock
   process; they never assert on the *arguments* passed to the mock (especially keyword
   arguments like `env`).

3. **The SQLite and gunicorn paths diverge.** Most manual and automated testing uses
   the PostgreSQL/gunicorn path. The SQLite path was refactored in the same commit but
   received less review attention.

4. **Entry-point scripts were new to the refactored layout.** The runner scripts moved
   from top-level to `src/simulation/`; the deeper nesting broke the implicit
   assumption that the repo root is on `sys.path`.

---

## Part 3 — Coverage Gaps by Module

The table below shows each `src/` sub-package, the total number of public functions,
and an assessment of whether they have *behavioural* tests (not just import/structure
tests in the phase files).

| Sub-package | Public functions | Behavioural coverage | Key gaps |
|---|---|---|---|
| `src/data_access/` | 16 | ✅ Good | — |
| `src/forum/` | 23 | ✅ Good | — |
| `src/models/` | 8 | ✅ Good | — |
| `src/recsys/` | 4 | ✅ Good | — |
| `src/telemetry/` | 3 | ✅ Good | — |
| `src/experiment/` | 34 | ⚠️ Partial | `clock.py` logic functions |
| `src/agents/` | 8 | ⚠️ Partial | `platform.infer_population_username_type` |
| `src/simulation/` | 35 | ⚠️ Partial | `process_runner`: 4 functions; subprocess env kwargs |
| `src/hpc/` | 27 | ⚠️ Partial | `log_metrics`: 2 functions; subprocess env kwargs |
| `src/system/` | 33 | ⚠️ Partial | `jupyter_utils` (7), `check_release` (2), `path_utils.get_data_schema_path` |
| `src/content/` | 23 | ❌ Low | `text_utils` (6), `article_extractor` (4), `avatars` (3) |
| `src/llm/` | 12 | ⚠️ Partial | `ollama_manager`, `vllm_manager` internals |

---

## Part 4 — Phased Test Implementation Plan

Tests are grouped so that each phase is independently runnable, builds on the
previous one, and targets a coherent area of the codebase.

---

### Phase A — Subprocess Environment Propagation (Critical Regression Guard)

**Goal:** Ensure that every `subprocess.Popen` call-site passes a controlled `env`
dict and that the child process can import `y_web`.  
**Rationale:** This is the entire class of bugs found during this audit. A targeted
test file makes the invariant machine-checkable.

**File:** `y_web/tests/test_subprocess_env_propagation.py`

| Test | What it validates |
|---|---|
| `test_simulation_server_gunicorn_popen_receives_env` | The gunicorn-path Popen mock is called with an `env` kwarg |
| `test_simulation_server_sqlite_popen_receives_env` | The SQLite-path Popen mock is called with `env` containing `YSERVER_LOG_FILE` |
| `test_hpc_server_gunicorn_popen_receives_env` | Same for hpc/server.py gunicorn path |
| `test_hpc_server_sqlite_popen_receives_env` | Same for hpc/server.py SQLite path (`YSERVER_CONFIG` present) |
| `test_hpc_client_popen_receives_env` | hpc/client.py Popen receives `env` |
| `test_simulation_client_popen_receives_env` | simulation/client.py Popen receives `env` |
| `test_simulation_client_popen_env_contains_pythonpath` | In non-frozen mode the env has `PYTHONPATH` set to project root |
| `test_client_runner_sys_path_contains_repo_root` | Importing `client_runner` does not raise; `_REPO_ROOT` is on `sys.path` |
| `test_server_runner_sys_path_contains_repo_root` | Same for `server_runner` |

**Implementation notes:**  
Each test should `monkeypatch` `subprocess.Popen` to capture calls, trigger the
relevant function with minimal valid arguments, and then assert on
`mock_popen.call_args.kwargs["env"]`.

---

### Phase B — `simulation/process_runner.py` Logic (High Value)

**Goal:** Cover the four public functions that are not yet behaviourally tested.  
**Rationale:** These functions run inside the subprocess and directly determine
simulation behaviour; bugs here produce silent incorrect results.

**File:** `y_web/tests/test_simulation_process_runner_logic.py`

| Test | Target function | What it validates |
|---|---|---|
| `test_get_users_per_hour_returns_zero_for_empty_population` | `get_users_per_hour` | Returns 0 when there are no active agents |
| `test_get_users_per_hour_scales_with_population_size` | `get_users_per_hour` | Value increases proportionally |
| `test_sample_agents_returns_correct_count` | `sample_agents` | Returned list length equals `expected_active_users` |
| `test_sample_agents_empty_returns_empty` | `sample_agents` | Returns `[]` for empty agent list |
| `test_sample_agents_respects_archetypes_filter` | `sample_agents` | Archetype filtering respected |
| `test_ensure_agents_have_archetype_assigns_default` | `ensure_agents_have_archetype` | Agents without archetype get one assigned |
| `test_ensure_agents_have_archetype_preserves_existing` | `ensure_agents_have_archetype` | Already-assigned archetypes are not overwritten |
| `test_resolve_client_package_dir_microblogging` | `_resolve_client_package_dir` | Returns correct path for `microblogging` platform |
| `test_repair_legacy_agent_file_no_op_on_valid` | `_repair_legacy_agent_file` | Returns unchanged path when no repair needed |

---

### Phase C — `experiment/clock.py` Validation Logic

**Goal:** Cover the clock computation and validation functions.  
**Rationale:** Clock functions determine experiment timing; wrong values silently
corrupt scheduled simulations.

**File:** `y_web/tests/test_experiment_clock_logic.py`

| Test | Target function | What it validates |
|---|---|---|
| `test_validate_feed_refresh_accepts_valid_values` | `validate_feed_refresh` | Valid integers pass without error |
| `test_validate_feed_refresh_rejects_negative` | `validate_feed_refresh` | Raises/returns error for negative values |
| `test_parse_anchor_date_returns_date_object` | `parse_anchor_date` | ISO string → `date` |
| `test_parse_anchor_date_invalid_returns_none` | `parse_anchor_date` | Invalid string → `None` |
| `test_wall_clock_slot_known_values` | `wall_clock_slot` | Returns correct slot for known timestamp |
| `test_seconds_until_next_hour_midpoint` | `seconds_until_next_hour` | ~1 800 s at :30 |
| `test_seconds_until_next_hour_at_top` | `seconds_until_next_hour` | ~3 600 s at exactly :00 |
| `test_apply_clock_to_client_simulation_sets_sim_clock` | `apply_clock_to_client_simulation` | Client object gains `sim_clock` attribute |
| `test_ensure_experiment_clock_fills_defaults` | `ensure_experiment_clock` | Missing keys filled from `default_clock_config()` |

---

### Phase D — `hpc/log_metrics.py` Log Processing

**Goal:** Cover the two untested functions that parse execution logs and update DB records.  
**Rationale:** These functions gate the "experiment complete" detection; if broken,
HPC experiments never finish cleanly.

**File:** `y_web/tests/test_hpc_log_metrics_logic.py`

| Test | Target function | What it validates |
|---|---|---|
| `test_get_latest_hourly_summary_returns_none_for_missing_file` | `get_latest_hourly_summary_from_client_log` | Returns `None` when log file does not exist |
| `test_get_latest_hourly_summary_parses_last_entry` | `get_latest_hourly_summary_from_client_log` | Returns the last hourly line from a fixture log |
| `test_get_latest_hourly_summary_empty_file_returns_none` | `get_latest_hourly_summary_from_client_log` | Empty file → `None` |
| `test_update_client_execution_from_log_marks_completed` | `update_client_execution_from_log` | Completion token in log → DB record updated |
| `test_update_client_execution_from_log_no_op_on_missing_file` | `update_client_execution_from_log` | Missing file → no exception, no DB write |

---

### Phase E — `content/text_utils.py` Processing

**Goal:** Cover the text-processing utilities that feed agent content generation.  
**Rationale:** These pure functions are easy to unit-test and bugs produce incorrect
or truncated agent post content.

**File:** `y_web/tests/test_content_text_utils.py`

| Test | Target function | What it validates |
|---|---|---|
| `test_strip_tags_removes_html` | `strip_tags` | HTML tags removed from output |
| `test_strip_tags_empty_string` | `strip_tags` | Empty string → empty string |
| `test_strip_markdown_artifacts_removes_backticks` | `strip_markdown_artifacts` | Triple-backtick code blocks stripped |
| `test_strip_markdown_artifacts_preserves_plain_text` | `strip_markdown_artifacts` | Plain text unchanged |
| `test_calculate_text_similarity_identical` | `calculate_text_similarity` | Returns 1.0 for identical strings |
| `test_calculate_text_similarity_disjoint` | `calculate_text_similarity` | Returns 0.0 for fully disjoint strings |
| `test_normalize_punctuation_spacing_fixes_double_spaces` | `normalize_punctuation_spacing` | Double spaces normalised |
| `test_normalize_punctuation_spacing_comma_no_space` | `normalize_punctuation_spacing` | `word ,word` → `word, word` |
| `test_strip_reproduced_article_content_truncates` | `strip_reproduced_article_content` | Reproducing article text beyond limit is cut |
| `test_process_reddit_post_converts_blankline_title` | `process_reddit_post` | Legacy blank-line title converted |
| `test_extract_components_hashtags` | `extract_components` | Returns list of `#tag` tokens |
| `test_extract_components_mentions` | `extract_components` | Returns list of `@user` tokens |

---

### Phase F — `content/article_extractor.py` and `content/avatars.py`

**Goal:** Cover article parsing and avatar-URL helpers.  
**Rationale:** Both modules contain pure/near-pure functions that are easy to test
with fixtures and avoid real network calls via monkeypatching.

**File:** `y_web/tests/test_content_article_and_avatars.py`

| Test | Target | What it validates |
|---|---|---|
| `test_extract_title_from_og_tag` | `extract_title` | `<meta property="og:title">` used when present |
| `test_extract_title_fallback_to_h1` | `extract_title` | Falls back to `<h1>` when no OG tag |
| `test_extract_description_from_meta` | `extract_description` | `<meta name="description">` parsed |
| `test_extract_source_returns_netloc` | `extract_source` | `https://example.com/page` → `example.com` |
| `test_clean_text_strips_whitespace` | `clean_text` | Leading/trailing whitespace removed |
| `test_deterministic_forum_avatar_url_consistent` | `deterministic_forum_avatar_url` | Same username → same URL across calls |
| `test_normalize_forum_avatar_mode_accepts_valid` | `normalize_forum_avatar_mode` | Valid mode names accepted without error |
| `test_normalize_forum_avatar_mode_rejects_invalid` | `normalize_forum_avatar_mode` | Invalid mode → raises `ValueError` |
| `test_discover_forum_avatar_urls_returns_dict` | `discover_forum_avatar_urls` | Returns a `dict` (may be empty without DB) |

---

### Phase G — `system/path_utils.py` and `system/check_release.py`

**Goal:** Cover the remaining `path_utils` gap and the release-check helpers.  
**Rationale:** Path resolution bugs produce subtle mismatches between development and
production environments; `download_file` validates checksums and its logic should be
verified.

**File:** `y_web/tests/test_system_path_and_release.py`

| Test | Target | What it validates |
|---|---|---|
| `test_get_data_schema_path_returns_absolute_path` | `get_data_schema_path` | Returns an absolute path string |
| `test_get_data_schema_path_ends_with_schema_folder` | `get_data_schema_path` | Path ends with known schema directory segment |
| `test_version_tuple_parses_three_parts` | `version_tuple` | `"1.2.3"` → `(1, 2, 3)` |
| `test_version_tuple_ordering` | `version_tuple` | `"1.10.0"` > `"1.9.0"` as tuples |
| `test_download_file_checksum_mismatch_raises` | `download_file` | `ValueError` (or similar) raised when sha256 mismatches |
| `test_download_file_size_mismatch_raises` | `download_file` | Raises when file size differs from `exp_size` |

---

### Phase H — `system/jupyter_utils.py` (Unit-level)

**Goal:** Cover the pure / near-pure helpers in `jupyter_utils` without requiring a
running Jupyter server.  
**Rationale:** Jupyter-utils functions are called during experiment start-up; import
errors or logic errors are hard to diagnose at runtime.

**File:** `y_web/tests/test_system_jupyter_utils.py`

| Test | Target | What it validates |
|---|---|---|
| `test_get_python_executable_returns_string` | `get_python_executable` | Returns a non-empty string |
| `test_find_free_port_returns_open_port` | `find_free_port` | Returned port is bindable |
| `test_find_free_port_respects_start_port` | `find_free_port` | Result ≥ `start_port` |
| `test_find_instance_by_notebook_dir_returns_none_for_unknown` | `find_instance_by_notebook_dir` | Returns `None` when no running instance matches |
| `test_start_jupyter_calls_subprocess` | `start_jupyter` | `subprocess.Popen` (or equivalent) called with notebook-related args |
| `test_stop_jupyter_noop_on_unknown_id` | `stop_jupyter` | No exception when `instance_id` is not found |
| `test_create_notebook_with_template_produces_file` | `create_notebook_with_template` | Creates a `.ipynb` file in a temp dir |

---

### Phase I — `agents/platform.py` Inference

**Goal:** Cover the one untested function in the agents sub-package.

**File:** Add to `y_web/tests/test_population_username_generation.py` (existing) or
create `y_web/tests/test_agents_platform.py`.

| Test | Target | What it validates |
|---|---|---|
| `test_infer_population_username_type_microblogging` | `infer_population_username_type` | Returns `"microblogging"` for a matching population |
| `test_infer_population_username_type_reddit` | `infer_population_username_type` | Returns `"reddit"` for a Reddit-style population |
| `test_infer_population_username_type_unknown_returns_default` | `infer_population_username_type` | Returns a sensible default for an ambiguous population |

---

## Part 5 — Summary Table

| Phase | File | Tests | Priority | Effort |
|---|---|---|---|---|
| A | `test_subprocess_env_propagation.py` | 9 | 🔴 Critical | Low |
| B | `test_simulation_process_runner_logic.py` | 9 | 🟠 High | Medium |
| C | `test_experiment_clock_logic.py` | 9 | 🟠 High | Low |
| D | `test_hpc_log_metrics_logic.py` | 5 | 🟠 High | Medium |
| E | `test_content_text_utils.py` | 12 | 🟡 Medium | Low |
| F | `test_content_article_and_avatars.py` | 9 | 🟡 Medium | Low |
| G | `test_system_path_and_release.py` | 6 | 🟡 Medium | Low |
| H | `test_system_jupyter_utils.py` | 7 | 🟡 Medium | Medium |
| I | `test_agents_platform.py` | 3 | 🟢 Low | Low |
| **Total** | | **69** | | |

---

## Part 6 — Conventions for New Tests

All new tests should follow the conventions already established in the repository:

1. **Use `pytest` fixtures** defined in `conftest.py` (`app`, `client`, `db`) for
   tests that need an application context.
2. **Use `monkeypatch`** (not `unittest.mock.patch`) for environment variable overrides
   and simple attribute replacement.
3. **Use `unittest.mock.patch`** (or `pytest-mock`'s `mocker`) for patching
   `subprocess.Popen` and external I/O.
4. **Import from canonical paths** (`y_web.src.*`), never from shim modules.
5. **Keep tests side-effect-free.** Tests that write files must use `tmp_path`.
6. **Phase A tests must not require a running process.** They should mock `Popen` and
   assert on call arguments only.
