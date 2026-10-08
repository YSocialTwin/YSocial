# Scenario Design

Admin-only authoring tool for YWeb/YSocial: design multi-round interaction
scenarios (threads, posts, round scheduling) ahead of an experiment run,
generate draft content with an LLM, and publish a validated scenario into
a microblogging experiment's real data — Standard or HPC alike. Drafts
are stored alongside the experiment they belong to (`db_exp`) and are
promoted/published into the experiment's own data only once validated.
Already-published real content can subsequently be corrected or removed
through the same admin UI, without touching anything else.

This repo is a **"backend settings" plugin suite** for YWeb — structurally
parallel to a "frontend plugins" suite (see
`y_web/src/external_runtime/frontend_plugins.py`), but admin-only and
always active once installed and valid (no per-experiment enable/disable,
no entry in `/admin/frontend_settings`). See the platform's
`y_web/src/external_runtime/backend_plugins.py` for the loader this suite
plugs into.

## Status

**Backend API: complete** (Fasi 0-8 of the implementation plan; Fase 9
packaging/release work below). See `docs/decisions.md` for the
phase-by-phase decision log and `docs/acceptance.md` for the
acceptance-criteria traceability table — the latter also documents an
important gap: **no visual frontend editor has been built** (only a
`static/placeholder.txt` exists from Fase 1); every feature below is a
tested backend API, driveable today via HTTP, with no admin UI in front
of it yet. Feature set:

- Scenario CRUD, experiment copy (agents-only or keep-all), compatibility
  check (microblogging only, Standard and HPC alike).
- Thread/post editor: CRUD, author search, static topic vocabulary,
  built-in "standard" role plus optional ad hoc roles discovered from the
  `agent_plugins` repo, draft subtree deletion, scenario-wide bulk
  deletion with a reinforced server-side name confirmation.
- Thread invariants enforced on every edit and re-verified on the whole
  draft graph at publish time (single root, no cycle, no orphan parent).
- LLM-assisted draft generation, with secrets redaction in logs/audit and
  a generation-cancel endpoint.
- Validate / preview / publish / audit for a scenario, behind one
  `MaterializationAdapter` interface with a Standard and an HPC
  implementation (opaque ids throughout: Python `int` for Standard,
  UUID `str` for HPC) — single-transaction atomicity, fingerprint-based
  staleness detection, an application-level lock, idempotency-key replay.
- Modification/deletion of **already-published** real content
  (`PUT`/`DELETE .../real_posts/<id>`,
  `POST .../real_posts/<id>/delete_subtree`) — content/author edits and
  full-subtree cascade delete across every satellite table, blocked
  while the experiment is running. Re-parenting published content is
  deliberately out of scope (see `real_content.py`'s module docstring).
- Centralized free-text sanitization and length limits
  (`sanitize.py`), a transversal `sd_audit_log` recording every mutating
  operation (`audit.py`), and the reinforced bulk-delete confirmation
  above — all three cutting across every phase of the feature set rather
  than being specific to one of them.

## Installation

From the YWeb admin panel, `/admin/external_runtimes` → **Backend
Extensions** category → **Scenario Design**:

- **GitHub Release** (recommended): installs the tagged release archive
  for the version selected. This is the supported path for a production
  deployment.
- **Git checkout** (advanced/development): points the loader at a local
  clone of this repository instead of a downloaded release — useful
  when iterating on the plugin itself, not recommended otherwise.

Either way, installation validates `meta/registry.json` against the
expected `backend_plugins` manifest schema before the module is
registered; an invalid or missing manifest fails installation cleanly,
with the core app otherwise unaffected (verified end-to-end in
`y_web/tests/test_scenario_design_install_uninstall.py` and
`y_web/tests/test_backend_plugins_registry.py`). Once installed, Scenario
Design is **always active** for every eligible experiment (no
per-experiment toggle) and gets its own per-experiment schema, created
just-in-time on first access (`ensure_scenario_design_schema`) — nothing
is migrated until an admin actually opens Scenario Design for a given
experiment.

## Configuration

No separate configuration file: Scenario Design reads the host YWeb
app's own configuration (database binds, the LLM backend already
configured for the platform) and needs nothing additional at install
time. The only per-experiment prerequisite is eligibility:
`Exps.platform_type == "microblogging"` (both `simulator_type`s —
Standard and HPC — are supported; forum and photo-sharing experiments
are explicitly out of scope for v1, by design, not by omission).

## Known limitations

- **No visual frontend editor yet.** The admin-facing scenario/thread
  editor described in the piano tecnico (§14, illustrated by
  `scenario_design_mockup_*.svg`) has not been built — only the backend
  API behind it has. See `docs/acceptance.md` for exactly which
  acceptance criteria this affects.
- **PostgreSQL HPC backends are not supported.** The HPC adapter
  (`adapters/hpc.py`) and the real-content endpoints both go through
  `hpc_session.py`, which opens a direct SQLAlchemy session against the
  experiment's physical **sqlite** file using YSimulator's own ORM
  models. An HPC experiment backed by PostgreSQL is an explicit,
  documented gap (`docs/decisions.md`), not a silent failure: every
  precondition check (`hpc_unavailable`, `hpc_database_not_found`) is
  sqlite-path-based.
- **Re-parenting a published real post is not supported.** Only
  `content`/`author_user_id` edits and (sub)tree deletion are offered on
  already-materialized content — see `real_content.py`'s module
  docstring for why this was deliberately narrowed rather than mirrored
  from the draft editor's full CRUD.
- **No generic cross-plugin cleanup hook in core.** A separate, minimal
  core PR for a cleanup hook other plugins' data could register against
  was scoped as non-blocking for v1 (`docs/decisions.md` §S): without it,
  uninstalling Scenario Design leaves its `sd_*` tables as orphaned,
  non-destructive data in the experiment's `db_exp` — already-published
  real content and every other core table are entirely unaffected.
- **Uninstalling does not touch published content.** Simulations already
  published through Scenario Design remain fully usable after the
  plugin itself is uninstalled; only the `sd_*` staging/audit tables
  become unreachable orphans (see previous point).

## Repo layout

- `meta/info.json`, `meta/registry.json` — suite manifest (registry.json's
  top-level `backend_plugins` key, not `frontend_plugins` — a backend
  module has no participant-facing surface).
- `modules/scenario_editor/backend/` — the Flask blueprint
  (`scenario_design_bp`, named after the *suite*, not the module, so a
  future second module can share the same sidebar entry point). See each
  module's own docstring for what it covers; `__init__.py`'s docstring
  lists every phase's routes in registration order.
- `modules/scenario_editor/static/` — module-local static assets, served
  through YWeb's path-traversal-protected static route.
- `tests/` — this repo's own, YWeb-independent standalone test suite
  (pure logic: invariants, sanitization, audit, adapters' dispatch
  shape, manifest/blueprint shape). Run with `python run_tests.py` or
  `pytest tests/`. Integration-level tests against a real YWeb boot
  (end-to-end registration, real `db_exp` writes, static asset serving,
  sidebar visibility) live in YWeb core's `y_web/tests/
  test_scenario_design_fase*.py` and `test_backend_plugins_registry.py`
  instead — see `docs/decisions.md` for why the split exists (this repo
  must stay importable without the rest of the YWeb stack installed).
- `docs/decisions.md` — running decision log, updated at the end of
  every implementation phase; the authoritative record of every design
  choice made during development and why.
- `docs/acceptance.md` — the 27 acceptance-criteria traceability table
  (piano tecnico §26), one row per criterion, each pointing at the test
  (or documented manual verification) that covers it.

## Requirements

Only Flask is required to run this repo's own standalone test suite
(`pip install flask && python run_tests.py`). No dependency on the rest
of the YWeb stack for that suite. The YWeb-core integration tests
(`y_web/tests/test_scenario_design_*.py`) need a full YWeb checkout and,
for the HPC-family tests specifically, `external/YSimulator` checked out
alongside it — both skip cleanly when their prerequisite isn't present
in the environment running them.

## CI

`.github/workflows/ci.yml` runs on every push/PR, two jobs:

- **lint**: `flake8 --select=E9,F63,F7,F82` — critical-only selection
  (syntax errors, undefined names, and similarly real defects), not a
  full style gate, so it does not fail on pre-existing style choices
  this phase didn't touch. A deliberate, documented scope decision
  (`docs/decisions.md`), not an oversight.
- **test**: `pytest tests/` — this repo's own standalone suite only. It
  does not run the YWeb-core integration suite (that needs a full YWeb
  checkout with its own dependencies — `external/YSimulator` for the HPC
  tests specifically — and is exercised from YWeb core's own CI
  instead).

Both jobs run against the Python version this repo targets (see the
workflow file for the exact matrix).
