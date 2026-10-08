# Acceptance criteria traceability (piano tecnico §26)

One row per criterion, each referencing the piano tecnico section(s) it
maps to (per §26's own mapping, reproduced verbatim below) and the test
(or documented manual verification) that covers it. Built backwards from
the tests that already exist, not written first and then "checked off" —
per the piano di implementazione's own risk mitigation for Fase 9: a
criterion with no covering test is marked **not covered**, not glossed
over as covered anyway.

> §26 mapping (piano tecnico, verbatim): 1→§9-10; 2→§8, §22; 3→§14;
> 4→§4, §15; 5→§15; 6→§14, §18-19; 7→§14-15; 8→§15, §20; 9→§14, §21;
> 10→§14-15; 11→§14; 12→§14, §16; 13→§16; 14→§16; 15→§16 (riuso
> `/admin/api/fetch_models`); 16→§16, §18-19; 17→§17; 18→§17; 19→§12,
> §23; 20→§18-19, §21; 21→§4, §18-19; 22→§21; 23→§18-19, §24; 24→§22,
> §24; 25→§21; 26→§4, §15; 27→(verifica dedicata, `run_tests.py` del
> core eseguito con plugin installato).

## Important gap found while compiling this table

**Every phase implemented in this session (Fasi 1-8) is backend-only.**
`modules/scenario_editor/static/` holds a single `placeholder.txt` and
nothing else — no HTML/CSS/JS visual editor was ever built. §14 ("Flussi
UI") describes a visual scenario/thread editor; the mockups in
`scenario_design_mockup_*.svg` illustrate it; but no frontend
implementing it exists in this repository. Every criterion below whose
**only** §26 reference is §14 is therefore marked **not covered** here,
honestly, rather than inferred from the (fully tested) backend API that
would sit behind it. Criteria that reference §14 *alongside* another
section are marked covered **for the non-UI part only**, with the UI
half called out explicitly.

This is reported here, not silently resolved, because it bears directly
on Fase 9's own completion gate ("tutti i 27 criteri di accettazione
verificati... non un'affermazione generica") — tagging v1.0.0 while
claiming full acceptance would not be accurate while this gap stands.

## Traceability table

| # | §26 ref. | Area | Status | Covered by |
|---|---|---|---|---|
| 1 | §9-10 | Repo structure, install/discovery mechanism | Covered | `tests/test_backend_suite_validation.py`, `tests/test_blueprint_registration.py`, `y_web/tests/test_scenario_design_install_uninstall.py`, `y_web/tests/test_backend_plugins_registry.py` |
| 2 | §8, §22 | Core/plugin boundary minimal, compat/packaging/uninstall | Covered | `y_web/tests/test_backend_plugins_registry.py`, `y_web/tests/test_scenario_design_install_uninstall.py` |
| 3 | §14 | UI flow (which one — n/a, section is general) | **Not covered** | No frontend implementation exists (see gap note above) |
| 4 | §4, §15 | Eligibility (`platform_type=="microblogging"`) + API contract | Covered | `y_web/tests/test_scenario_design_fase2_routes.py` (eligibility filter, uniform error envelope) |
| 5 | §15 | API/services backend | Covered | `y_web/tests/test_scenario_design_fase2_routes.py`, `y_web/tests/test_scenario_design_fase3_threads.py` |
| 6 | §14, §18-19 | UI + Standard/HPC materialization | Partially covered | Materialization: `y_web/tests/test_scenario_design_fase6_publish.py`, `test_scenario_design_fase7_publish_hpc.py`. UI half: **not covered** |
| 7 | §14-15 | UI + API | Partially covered | API: `test_scenario_design_fase2_routes.py`, `test_scenario_design_fase3_threads.py`. UI half: **not covered** |
| 8 | §15, §20 | API + destructive operations | Covered | `y_web/tests/test_scenario_design_fase3_threads.py` (draft subtree/bulk delete), `y_web/tests/test_scenario_design_fase8_real_content.py` (real-content subtree delete) |
| 9 | §14, §21 | UI + security/integrity/audit | Partially covered | Security/audit: `tests/test_sanitize.py`, `tests/test_audit.py`. UI half: **not covered** |
| 10 | §14-15 | UI + API | Partially covered | API: route tests above. UI half: **not covered** |
| 11 | §14 | UI flow | **Not covered** | No frontend implementation exists |
| 12 | §14, §16 | UI + LLM generation | Partially covered | LLM: `tests/test_llm_client.py`, `tests/test_prompt_builder.py`, `y_web/tests/test_scenario_design_fase4_llm.py`. UI half: **not covered** |
| 13 | §16 | LLM: backend/model selection, prompt building | Covered | `tests/test_prompt_builder.py`, `tests/test_llm_client.py`, `y_web/tests/test_scenario_design_fase4_llm.py` |
| 14 | §16 | LLM: preview, regeneration, audit | Covered | `y_web/tests/test_scenario_design_fase4_llm.py` |
| 15 | §16 | LLM: reuse of `/admin/api/fetch_models`, no duplicate endpoint | Covered | `tests/test_llm_client.py` |
| 16 | §16, §18-19 | LLM-generated content flows into materialization | Covered | `y_web/tests/test_scenario_design_fase4_llm.py` + `test_scenario_design_fase6_publish.py`/`test_scenario_design_fase7_publish_hpc.py` (generated drafts are ordinary draft posts, publish-tested the same way) |
| 17 | §17 | Ad hoc roles: discovery | Covered | `tests/test_roles.py`, `y_web/tests/test_scenario_design_fase5_roles.py` |
| 18 | §17 | Ad hoc roles: fallback when `agent_plugins` absent/invalid | Covered | `tests/test_roles.py`, `y_web/tests/test_scenario_design_fase5_roles.py` |
| 19 | §12, §23 | Scenario lifecycle (draft/validated/published, copy modes) + incremental plan process | Covered | `y_web/tests/test_scenario_design_fase2_routes.py` (agents-only/keep-all copy), `docs/decisions.md` (phase-by-phase process record) |
| 20 | §18-19, §21 | Materialization + security (fault injection, locking, fingerprint) | Covered | `y_web/tests/test_scenario_design_fase6_publish.py`, `test_scenario_design_fase7_publish_hpc.py` (fault injection, idempotency replay, fingerprint mismatch, running-experiment rejection) |
| 21 | §4, §18-19 | Eligibility re-checked at materialization time | Covered | `adapters/standard.py`/`adapters/hpc.py`'s own re-verification steps, exercised in the same fase6/fase7 publish tests above |
| 22 | §21 | Security/audit | Covered | `tests/test_audit.py`, `tests/test_sanitize.py`, bulk-delete confirmation test in `y_web/tests/test_scenario_design_fase3_threads.py` |
| 23 | §18-19, §24 | Materialization + test strategy | Covered | Fase 6/7 publish tests + this repo's full test suite (both standalone and YWeb-core) |
| 24 | §22, §24 | Packaging/compat + test strategy | Covered | `y_web/tests/test_scenario_design_install_uninstall.py` + full suite |
| 25 | §21 | Security: XSS/script injection, secrets redaction | Covered | `tests/test_sanitize.py` (script/HTML tag stripping), `tests/test_secrets_redaction.py` |
| 26 | §4, §15 | Eligibility + API contract (duplicate of #4's references) | Covered | Same as #4 |
| 27 | (dedicated verification) | Full core suite with plugin installed | Covered | This session's own Fase 8 non-regression run (`docs/decisions.md` §F8.7): `python3 -m pytest y_web/tests -q` → 1931 passed, 80 skipped, 2 pre-existing/environmental failures unrelated to this plugin (`test_client_logs.py`, sandbox file-permission, documented since Fase 1). Re-run with the plugin **absent** via `y_web/tests/test_scenario_design_install_uninstall.py`'s uninstall path (2/2 passed) rather than a second full-suite run, since the plugin's own tests are the only ones sensitive to its presence. |

## Summary

20 of 27 criteria are fully backed by an automated test, run in this
session, covering every backend phase (0-8) end to end. 7 criteria (3, 6,
7, 9, 10, 11, 12) reference §14; of these, 2 (3, 11) reference §14 only
and are **entirely not covered**, and the other 5 (6, 7, 9, 10, 12) have
their non-UI half covered but their UI half **not covered** — because no
frontend editor exists in this repository. Closing
this gap (building `modules/scenario_editor/frontend/`'s actual visual
editor, not just the `plugin.js` placeholder mentioned in Fase 1's
scope) is outside what this session's instructions asked for so far and
has not been scoped or estimated here — flagged for the product owner's
decision before a v1.0.0 release can honestly claim full acceptance.
