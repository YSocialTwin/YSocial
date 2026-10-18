# Localization closure checklist (EN + IT)

Status of the localization work and what is left before it can be called closed. Items marked **[you]** need a
person (a decision, a native speaker, a real run or a release); everything else is done and verified. Update the
boxes as items close; this file is the single list.

Scope: UI (gettext, JS catalogs, plugin catalogs), LLM prompts (packs and `prompts_internal`), Agent Memory
plugin texts. Procedure for a new language: [adding-a-language.md](adding-a-language.md).

## 1. Done (nothing to do)

- [x] UI catalogs complete for `it`: core, TrainingModules, ScenarioDesign, frontend_adds-on, reactive_agents, JS catalogs (coverage report 100%).
- [x] Prompt packs `it` (prompts, forum, hpc, ygram, profile_values) and `prompts_internal.it.json` in the 7 prompt-building repos; validator, hash snapshots and glossary checks in CI.
- [x] Agent Memory plugin: texts in `prompts/<lang>.json`, Italian pack with lexicons, `memory_language` passed by the clients.
- [x] Memory UI shown only when the plugin is installed (`memory_plugin_installed`).
- [x] Prompt pilot run twice (2 models x en/it x 3 seeds): protocol compliance and language adherence hold; decision **keep** recorded in `docs/prompt-pilot-report.md`.
- [x] Packaging: translations and `prompts_internal` bundled; plugins no longer in the bundle.
- [x] Guide "Adding a language" in `docs/i18n/`, linked from the README and mkdocs.
- [x] Technical debt: `y_web/__init__.py` split (710 -> 379 lines), global test timeout, shipped packs guarded for `str.format`; the full YWeb test suite passes.
- [x] Recorded as out of scope (see the guide, section "Out of scope by decision"): data-block labels, API error messages, ScenarioDesign draft prompt, the YSimulator `str.format` calls on user-editable templates.

## 2. Needs a person

### 2.1 Review by a native speaker (Italian stays `draft` / beta until done)

- [ ] **[you]** Italian prompt pack: `docs/prompt-review-it.md` (glossary: `docs/prompt-glossary.md`). On approval set the manifest status to the final value and re-run `validate_pack.py` and `snapshot_hashes.py --check`.
- [ ] **[you]** Italian UI strings: `docs/i18n/review-checklist.md`. On approval remove "(beta)" (`LANGUAGE_STATUS` in `y_web/i18n.py`) and update the status test.
- [ ] **[you]** Agent Memory `prompts/it.json` (including the `lex__*` lexicons).

### 2.2 Gates and real runs

- [ ] **[you]** Gates G-M2, G-M4, G-M7 (memory programme) and G3: sign or reject.
- [ ] **[you]** G4: one real experiment per platform (ad hoc agent, social chat, forum, memory on) with a real LLM and `it` selected. Check: no English leakage in agent text, protocol tokens parsed, memory blocks non-empty, language recorded for the experiment.
- [ ] **[you]** Install-from-UI check: install the Agent Memory plugin with the plugin button on a clean install and confirm the memory settings appear.
- [ ] **[you]** Visual regression with the pseudo-locale `en-XA` (needs a browser) and acceptance of the template-render overhead noted in `phase5-report.md`.

### 2.3 Release (nothing has been pushed)

- [ ] **[you]** Push branch `prompts-i18n` of YWeb, YClient, YClientReddit, YSimulator, YPhotoSharing, y_agents_plugins, reactive_agents, y_memory_subsystem, and branch `i18n` of ScenarioDesign, TrainingModules, frontend_adds-on, YServer, YServerReddit.
- [ ] **[you]** Tag / PyPI for `y_memory_subsystem` 0.2.0 only if you decide to publish.
- [ ] **[you]** Open and merge the pull requests (YWeb last, so its plugin pointers match).

## 3. Housekeeping (small, safe)

- [ ] **[you]** Delete the local branch `i18n-before-filter` once nothing needs it.
- [ ] **[you]** Remove untracked leftovers `external/TrainingModules/_to_delete/` (debug test files) and the stale lock refs reported by `git branch -a` (`refs/heads/*.lock.stale-*`); both need delete permission.
- [ ] Optional: language usage in exports (the language of each experiment is stored but not written into exports).

## 4. Before you close

Run, from the YWeb root, with the same Python as CI:

```
python scripts/i18n/coverage_report.py --min 98
python scripts/i18n/check_glossary.py
python scripts/prompts/validate_pack.py
python scripts/prompts/snapshot_hashes.py --check
python -m pytest y_web/tests -q
```

The English output must stay byte-identical (snapshot checks above) and `git status` must be clean in every repo.
