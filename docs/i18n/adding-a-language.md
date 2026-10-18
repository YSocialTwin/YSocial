# Adding a language to YSocial

This is the single reference for adding a new language (examples use French, `fr`) to YSocial. It is written for human contributors and for coding agents: every step names the files, the command that checks it and the invariant it must not break. Follow it in order and do not skip the checks; the checks are what prevent regressions.

Reading map: general rules for translatable code are in [`conventions.md`](conventions.md), the review process in [`review-checklist.md`](review-checklist.md) and [`contributing.md`](contributing.md), the memory plugin has its own short guide in `external/y_memory_subsystem/docs/languages.md`.

## 0. The two independent layers

A language in YSocial is **two separate things**. They are enabled separately, stored separately and can be released separately.

| Layer | What it translates | Who sees it | Selected by | Source of truth |
| --- | --- | --- | --- | --- |
| **Interface (UI)** | Admin panel, participant frontend, JS, plugin screens, flash/error messages | Humans | Admin user's language; per-experiment simulation language (`Exps.language`, `language_switch_allowed`) | gettext catalogs (`.po/.mo`) and JS catalogs (`.json`) |
| **Prompts** | Every sentence sent to an LLM: agent prompts, annotators, chat/interview, memory blocks | The LLM | Per-experiment `Exps.prompt_language`, optionally per client (`Client.prompt_language`) | Prompt packs (`data_schema/prompts/<lang>/`, `prompts_internal.<lang>.json`, `yclient_memory/prompts/<lang>.json`) |

Rules that hold for both layers (they are part of the program's contract; do not relax them):

1. **English is the source and must stay byte-identical.** Adding a language never changes English output. CI enforces it for prompts (`snapshot_hashes.py --check`) and for the memory plugin (golden snapshot).
2. **No runtime auto-translation.** Every text is a reviewed file. Nothing is translated by a model at run time.
3. **Protocol tokens are never translated** (see section 3.4). Code parses them back from model output or stored data.
4. **Users' content is never translated or run through catalogs**: posts, comments, agent names/bios, users' custom prompts.
5. **A missing key or a missing language falls back to English** (with one warning for prompts). A half-translated language must degrade to English, never crash.
6. **Do not "improve" the English text** while translating. A change to English is a separate change with its own hash update. Example of a maintainer-approved change: the photo caption prompts no longer mention the simulation day and slot (models copied them into the caption); the English and Italian packs changed together and the affected entries of `docs/prompt-hashes.json` were updated one by one, never regenerated wholesale.
7. **Plugins are optional.** With a plugin absent or disabled the core behaves as before; a language added to a plugin never makes the core depend on it.
8. Git hygiene used by this program: work on a branch, commit incrementally, do not push or tag on behalf of the maintainers.
9. **The prompt language does not set the language of the generated text.** `prompt_language` (experiment or client) chooses the language of the instructions sent to the model. The language agents write in is the `language` attribute of the population (rendered into prompts such as "Write in {self.language}", localised, e.g. "inglese"). An Italian experiment with an English population produces English posts by design; to get Italian posts, create the population with language Italian.

## 1. Prerequisites and decisions

Before writing anything, settle these (they are decisions for the maintainers, not for an agent to take silently):

- **Language code**: lowercase ISO 639-1/-3, optionally with region (`fr`, `pt-br`). The validators accept `^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$`. Use the same code in every layer and every repository. Do not use `en-XA` (reserved pseudo-locale).
- **Scope of the first release**: UI only, prompts only, or both. Both layers work independently.
- **Native reviewer** identified (required to leave *beta*, section 8).
- **Glossary** for the language (section 2.6) approved by the reviewer.
- **Model support**: prompts only help if the LLMs used in experiments handle the language. State this in the release note.

Environment for the commands below (YWeb repo root):

```bash
pip install -r requirements.txt       # includes Flask-Babel and Babel
git checkout -b i18n-<code>            # in YWeb and in every plugin you touch
```

## 2. Interface layer (UI)

### 2.1 Enable the code in the core

| Step | File | Change |
| --- | --- | --- |
| Display name | `y_web/i18n.py` → `LANGUAGE_NAMES` | Add `"fr": "Français"` (native name). Unknown codes show the raw code. |
| Enabled languages | `y_web/config.py` → `YSOCIAL_LANGUAGES` default (`"en,it"`) | Add the code to the default only when the language is ready to be offered. English is always added. |
| Maturity label | `y_web/i18n.py` → `LANGUAGE_STATUS` | Add `"fr": "beta"` so selectors show "Français (beta)" until section 8 is satisfied. |
| Docker/CI | Environment | `YSOCIAL_LANGUAGES=en,it,fr` overrides the default without a code change (also the kill switch: `YSOCIAL_LANGUAGES=en` withdraws every non-English language at the next restart; saved user/experiment languages fall back to English). |

Language resolution (do not change while adding a language): admin pages use the admin user's saved language, then the `ys_lang` cookie, then `Accept-Language`, then English. Participant pages use the `ys_lang_sim` cookie (only if the experiment allows overrides), then the experiment language, then English; `Accept-Language` is ignored on purpose. `<html lang>` always comes from `get_locale()`.

### 2.2 Core gettext catalog (Python and Jinja)

```bash
python scripts/i18n/catalogs.py update                       # refresh messages.pot, merge into every .po
pybabel init -i y_web/translations/messages.pot -d y_web/translations -l fr   # first time only
python scripts/i18n/catalogs.py update                       # now merges into the new fr/messages.po
# translate every empty msgstr in y_web/translations/fr/LC_MESSAGES/messages.po
python scripts/i18n/catalogs.py compile                      # writes messages.mo for every language
python scripts/i18n/catalogs.py check                        # fails if committed .pot/.mo are stale
```

Rules for translators and agents:

- The English text is the msgid. Keep every `%(name)s` placeholder exactly (same names, same count); keep `%%` literal percent signs; keep punctuation and markup that is inside the msgid.
- Never concatenate translated fragments in code; if a sentence needs a link or bold part, the code already passes it as a placeholder (`wrap('b', ...)`).
- Plurals: set the correct `Plural-Forms` header for the language in the `.po` (Babel fills it from the locale on `init`) and provide all forms.
- Commit **both** `.po` and `.mo` (decision G0: there is no compile step in build or packaging). **Packaging:** `y_social.spec` bundles `y_web/translations` and `y_web/prompts_internal*.json`, and the listed `external/` runtimes whole (their `prompts_internal*.json` and catalogs travel with them). After adding a language, still build one executable and check that the catalogs and prompt files are in the bundle. Only the simulation runtimes (YServer, YClient, YServerReddit, YClientReddit, YSimulator, YPhotoSharing) are in the spec's `external` list; every other plugin (`ScenarioDesign`, `TrainingModules`, `frontend_adds-on`, `reactive_agents`, `y_agents_plugins`, `y_memory_subsystem`) are installed later from the plugin page; their catalogs and prompt files arrive with the plugin itself, so they must be committed in the plugin repository (section 2.4).
- Translate the msgids that come from the plugin registry (plugin names/descriptions in `y_web/src/external_runtime/registry.py`, `RUNTIME_TEXTS`, marked with `N_()`); they live in the core catalog.

### 2.3 JavaScript catalogs (browser strings)

Catalogs live in `y_web/translations/js/<domain>/<lang>.json`, served at `/i18n/<domain>/<lang>.json`. Core domains: `core`, `admin`, `simulation`, `tutorials`. `en.json` is mandatory and is the fallback for missing keys.

- Create `fr.json` next to every `en.json` in the four core domains with the same keys. Key style differs by domain: `core` uses symbolic keys (`login.show_password`), the others use the English text as key (`"Add Topic": "Add Topic"`). Keep each file's existing style.
- Keep `{placeholder}` names. No HTML in values.
- Check: `python scripts/i18n/jscatalog.py missing <domain> fr` and `python scripts/i18n/jscatalog.py check <domain> fr` (placeholder consistency + missing count). When a JS string is added to code, `python scripts/i18n/jscatalog.py sync <domain> <js files>` regenerates `en.json`.
- Inline `<script>` blocks are not allowed (project test constraint); server values reach JS via `data-*` attributes.

### 2.4 Plugin catalogs

Each plugin that shows text opts in with `"i18n": {"domain": "<domain>", "translations": "translations"}` in its `meta/registry.json`. Plugins with UI catalogs today:

| Plugin (`external/…`) | Domain | Gettext | JS catalog |
| --- | --- | --- | --- |
| `frontend_adds-on` | `frontend_adds_on` | yes | yes |
| `ScenarioDesign` | `scenario_design` | yes | yes |
| `TrainingModules` | `training_modules` | yes | no |
| `reactive_agents` | `reactive_agents` | yes | no |
| `y_agents_plugins` | `y_agents_plugins` | yes | no |

`y_memory_subsystem` (Agent Memory) has no UI strings of its own: its name/description are in the core catalog (section 2.2) and its configuration screens are core templates.

For each plugin, from the YWeb root:

```bash
python scripts/i18n/plugin_catalogs.py extract external/<plugin> --domain <domain>
python scripts/i18n/plugin_catalogs.py update  external/<plugin> --domain <domain> --langs it fr   # creates fr/LC_MESSAGES/<domain>.po if missing
# translate the empty msgstr
python scripts/i18n/plugin_catalogs.py compile external/<plugin> --domain <domain>
python scripts/i18n/plugin_catalogs.py check   external/<plugin> --domain <domain> --langs fr
# plugins with a JS catalog:
python scripts/i18n/plugin_catalogs.py js-sync  external/<plugin> --domain <domain>
python scripts/i18n/plugin_catalogs.py js-check external/<plugin> --domain <domain> --lang fr
# create translations/js/<domain>/fr.json from en.json, translate values
```

Manifest strings (names and labels in `meta/*.json`) are extracted by the same tool (`catalogs.py manifests <plugin_dir> --domain <domain>`). `.po` and `.mo` are committed **in the plugin repository** (the core never edits plugin catalogs). If a plugin repo has its own docs about i18n (e.g. TrainingModules' Italian guide), add the language there too.

### 2.5 Hard-coded `it` in the tooling and tests (known coupling)

Some checks still name Italian explicitly and must be extended, otherwise the new language is silently unchecked:

- `scripts/i18n/check_glossary.py`: reads only `.../translations/it/...` catalogs and the `it`/`forbid_it` columns of `docs/i18n/glossary.csv`. Add a `fr`/`forbid_fr` column pair and make the script iterate over the languages that have a column.
- `y_web/tests/test_i18n_*.py` (smoke, selector, kill switch, plugins, experiment language, glossary, admin layout…): several parametrize or assert on `"it"`. Add `fr` to the parametrization where the test is about "every supported language"; do not remove the Italian cases.
- `scripts/i18n/coverage_report.py` discovers languages automatically but applies `--min 98` to **every** language found. A new language below 98% in any area (core, each plugin, each JS domain) makes the CI step fail. Either reach 98% before opening the PR, or agree with the maintainers on a temporary per-language threshold; do not lower the global threshold silently.
- `scripts/i18n/scan_unmarked.py --check` is a ratchet on unmarked English strings; a language addition does not change it. It must not go up.

### 2.6 Glossary and style

`docs/i18n/glossary.csv` fixes the translation of project terms (experiment, agent, client, population…) and lists forbidden variants. Add the new language's columns, get the native reviewer's approval, then run `python scripts/i18n/check_glossary.py` (must report 0 violations). Terms: "AI agent" is never "bot".

### 2.7 UI verification

```bash
python scripts/i18n/catalogs.py check
python scripts/i18n/scan_unmarked.py --check
python scripts/i18n/check_glossary.py
python scripts/i18n/coverage_report.py --min 98
python -m pytest y_web/tests -k "i18n" -q
```

Then, in a browser (not automatable from CI): start YSocial with `YSOCIAL_LANGUAGES=en,it,fr`, pick the language in the admin selector and in an experiment (Experiment configuration → simulation language), and check: no raw English left on the touched pages, long words do not overflow (use the pseudo-locale for padding tests: `YSOCIAL_PSEUDO_LOCALE=1`, `python scripts/i18n/catalogs.py pseudo`, cookie `ys_lang=en-XA`), dates and numbers use Babel formats, `<html lang="fr">`.

Known limits of the UI layer you should state in the release note: sentiment annotation uses VADER (an English lexicon; scores for other languages are unreliable), toxicity depends on the Perspective API's language support; neither is changed by a UI translation.

## 3. Prompt layer (texts sent to LLMs)

### 3.1 How prompts are organised

- **Prompt packs** (`data_schema/prompts/<lang>/`): `manifest.json`, `prompts.json` (microblogging agents), `prompts_forum.json`, `prompts_hpc.json` (HPC/YSimulator), `prompts_ygram.json` (photo sharing), `profile_values.json` (how agent attribute values read in the language: gender, leaning, education level, toxicity, big five, action, nationality, language, profession). English is the source; the packs are copied into the experiment/client when it is created (`y_web/src/system/prompt_packs.py`). Users' later edits to their prompts are never touched.
- **Internal prompts** (`prompts_internal.<lang>.json` next to the English `prompts_internal.json`): texts that used to live in Python (annotators, interview, chat, URL summary, agent plugins). Seven locations, all required: `y_web/`, `external/YClient/y_client/`, `external/YClientReddit/y_client/`, `external/YSimulator/YSimulator/`, `external/YPhotoSharing/YPhotoSharing/`, `external/y_agents_plugins/src/y_agents_plugins/`, `external/reactive_agents/src/reactive_agents/`. A language file only needs the keys it translates.
- **Renderer** (`prompt_store.py`, the *same file* is copied into each of those repositories; keep the copies identical): fills only the closed list of fields a caller passes (`{topic}`, `{self.age}`, `{article['title']}`, `{', '.join(items)}`, `{trust:.2f}`), never evaluates anything, raises `PromptError` if a named field is not passed, and leaves every other brace (JSON examples) untouched.
- **Memory plugin texts** (`external/y_memory_subsystem/src/yclient_memory/prompts/<lang>.json`): section 4.
- **Language flow**: YWeb stores `Exps.prompt_language` (and `Client.prompt_language`), writes `prompt_language.json` into the experiment folder, and starts clients with `YSOCIAL_PROMPT_LANGUAGE`; Ray workers get it through `runtime_env`; the language is re-read from the experiment on every call by chat, interview, annotators, URL summary and reactive agents.
- **Discovery**: a language is offered in the prompt-language selector as soon as `data_schema/prompts/<lang>/manifest.json` exists. No code change is required for the core selector. Any alembic migration is **not** needed (`prompt_language` is a free VARCHAR(10), migration 0010).

### 3.2 Create the packs

1. Copy `data_schema/prompts/en/` to `data_schema/prompts/fr/`; set the manifest:

   ```json
   {"language": "fr", "name": "French", "native_name": "Français", "status": "draft",
    "files": ["prompts.json", "prompts_forum.json", "prompts_hpc.json", "prompts_ygram.json", "profile_values.json"],
    "reviewed_by": null}
   ```

   `status` stays `draft` until the native review (section 8); `reviewed_by` is set only by the reviewer's sign-off. The manifest must list exactly the files present.
2. Translate the values of every file; keep keys identical at every depth. For `profile_values.json` translate the values for each key (nationality, language and profession lists are long; a missing value falls back to the English word).
3. For each of the seven locations copy `prompts_internal.json` to `prompts_internal.fr.json` and translate.
4. Follow `docs/prompt-glossary.md` (register: the Italian pack uses second person singular and the imperative; fix the equivalent for the new language in a short "Register and voice" section of a language glossary, e.g. `docs/prompt-glossary-fr.md`, and have the reviewer approve it). Keep the structure of the English text: same paragraphs, same `##MARKER##` lines, same bullet layout; only the words change. Texts the agent must write are asked "in the agent's language" via `{self.language}`.
5. Do not put explicit insults in the instructions about aggressive/toxic content; follow what the Italian pack does (describe the behaviour, do not list slurs).

### 3.3 Field rules (enforced by the validator)

- The same `{fields}` in each text, **the same number of times**. A field may move inside the sentence but never change, disappear or be added. Do not translate a field name.
- Anything that looks like a field but is not one (JSON examples) must stay as in English.
- Escape rules are the English ones: if the English text contains literal braces for a JSON example, keep them literally.

### 3.4 Protocol tokens: never translate

The authoritative list is `external/YClient/y_client/protocol_tokens.py` (the validator reads it). It includes answer tokens (`YES`, `NO`, `NEUTRAL`, `LEFT`, `RIGHT`, `NONE`, `AGREE`, `DISAGREE`, `LIKE`, `DISLIKE`, `LOVE`, `LAUGH`, `ANGRY`, `SAD`, `IGNORE`), action names (`POST`, `COMMENT`, `READ`, `SEARCH`, `FOLLOW`, `SHARE`, `IMAGE`, `CAST`, `REPORT`, `SHARE_LINK`, `SHARE_IMAGE`, `NEWS` (legacy alias of `SHARE_LINK` read by the forum client, never offered to the model), `REPORT_TOXIC`, `REPORT_OFFENSIVE`), the emotion labels handed to the model and parsed back (GoEmotions), JSON keys and enum values inside prompts (`relation_label`, `summary_text`, `agree`, `hostile`…), `##MARKER##` lines, `@username`, `#hashtags` syntax, and `[M n]`, `r<N>` memory markers. A token written in the English text must appear, untranslated, in the translation. If you add a token to the code, add it to `protocol_tokens.py` and to the glossary table, never only to a pack.

Also keep untranslated: data-block labels the code or models use as markers (`Text:`, `Post:`, `Topic:`), which are intentionally English in the Italian pack.

### 3.5 Validate and verify the prompt layer

```bash
python scripts/prompts/validate_pack.py                  # all languages: keys, fields, tokens, manifests
python scripts/prompts/validate_pack.py --language fr    # only the new one
python scripts/prompts/validate_pack.py --language fr --allow-partial   # while the translation is in progress
python scripts/prompts/snapshot_hashes.py --check        # English prompts byte-identical (never run --write for a language addition)
python -m pytest y_web/tests -q -k "prompt"              # prompt_store, packs, contracts, render equivalence, chat/adhoc language
```

Relevant tests: `test_prompt_store.py` (renderer), `test_prompt_packs.py`, `test_prompt_pack_contracts.py` and `test_hpc_prompt_contracts.py` (every pack keeps the contracts the code relies on), `test_prompt_render_equivalence.py` (English rendering equals the historic output), `test_chat_prompt_language.py`, `test_adhoc_prompt_language.py`, `test_alembic_0010_prompt_language.py`. In each client repository run its tests (`tests/test_memory_language.py` in YClient and YClientReddit, `YSimulator/tests/test_memory_runtime.py`, and the prompt tests of the plugins).

`snapshot_hashes.py --write` is only for the maintainers when English text legitimately changes. A failing `--check` after adding a language means English was touched: revert.

A real experiment is the final gate (no test replaces it): run one experiment per platform (microblogging, forum, HPC/photo) with the model that will be used, prompt language `fr`, with at least an ad hoc client, a chat/interview and (if installed) memory, and read the generated posts and logs for English leakage, malformed protocol answers (LLM answers that no longer parse), and `PromptError`s. Record the outcome (model, platform, date) in the release note; the pilot harness is `scripts/prompts/pilot.py` (its comparison between languages is only valid if the seed does not depend on the language; it was fixed, keep it that way).

## 4. The Agent Memory plugin (`yclient_memory`)

The plugin is optional. All memory UI in YWeb (client setup, client details, experiment details, embedding settings) is hidden when the plugin is not installed (`y_web/src/system/memory_plugin.py`, template variable `memory_plugin_installed`), and the wording about memory/embeddings in experiment details switches to the memory-free variant. Adding a language must not change that gating.

What it contains and how a language is added (full text in `external/y_memory_subsystem/docs/languages.md`):

1. Copy `src/yclient_memory/prompts/en.json` to `prompts/fr.json` and translate **every** value. Keep `{fields}`, protocol tokens (`affinity`, `conflict`, `humor`, `trust`, `[M1]`, `@username`, `r<N>`) and the leading `[` of block headers.
2. Entries starting with `lex__` are **lexicons**: lowercase word lists/stems used by keyword heuristics that read *incoming* messages (affect triggers, interaction notes, callback markers, stop words). English matches plain substrings; every other language matches at the **start of a word** (stem `sbagliat` covers `sbagliato`), symbols such as `?` stay substrings. These are behaviour, not wording: write them for the language, and measure them.
3. Limits: the cue block ≤ 900 characters, thread block ≤ 220, style block ≤ 280; longer translations are cut by the engines.
4. Stored values (e.g. vote summaries `upvote on @user: …`) stay English by design; they are filtered before reaching a prompt.
5. The package falls back to English with one warning for a missing language or key; `MemoryConfig.language` (`memory_language`/`language`) selects it. Clients pass the experiment prompt language automatically; a pre-0.2.0 package logs one warning and stays English.

Checks (run inside `external/y_memory_subsystem`):

```bash
python -m pytest                                  # tests/test_i18n.py runs for every pack found: same keys/fields, protocol tokens, block limits
python scripts/golden_snapshot.py --check         # English output byte-identical to 0.1.x
python scripts/measure_heuristics.py              # recall of the lexicons; add the language column to tests/data/heuristics_corpus.json
python scripts/measure_retrieval.py               # top-1 retrieval on topical pairs
python scripts/e2e_memory_sim.py --check-golden   # deterministic EN/language simulation, no LLM
```

Acceptance rule for a new language's heuristics: recall at least 80% of English on the parallel corpus, false positives within ten points; also write a small hold-out set *after* the lexicons to see how they generalise. Also review the stop list: English keeps its historic 16-word stop list on purpose (changing it would change English behaviour); a new language should have a realistic list, otherwise function words inflate the hybrid backend's "strong" scope. Document the numbers in the plugin's `CHANGELOG.md` and bump its version.

## 5. Other plugins and components: what to check

| Component | Needs a language file? | Where |
| --- | --- | --- |
| `y_web` core | gettext + JS + prompt packs + `prompts_internal.<lang>.json` | sections 2 and 3 |
| `YClient`, `YClientReddit`, `YSimulator`, `YPhotoSharing` | `prompts_internal.<lang>.json` each; YSimulator and YClientReddit also pass `memory_language` | section 3 |
| `y_agents_plugins`, `reactive_agents` | `prompts_internal.<lang>.json` + UI catalog | sections 2.4, 3 |
| `frontend_adds-on`, `ScenarioDesign`, `TrainingModules` | UI catalogs (gettext, JS where listed) | section 2.4 |
| `y_memory_subsystem` | `prompts/<lang>.json` | section 4 |
| `YServer`, `YServerReddit` | no prompt files (they do not build prompts); API error messages stay English | n/a |
| Out of scope by decision (do not translate) | data-block labels in interview/chat (protocol markers, kept English); API error messages of `YServer`/`YServerReddit`; the ScenarioDesign draft-generation prompt (`prompt_builder.py`, English instructions, output language set by its `agent_language` parameter); the ~49 `str.format` calls in YSimulator, which fill the user-editable `system_template`/`user_template` and keep `str.format` semantics for custom prompts (`y_web/tests/test_pack_format_safety.py` guards the shipped packs) | recorded as out of scope (str.format: confirmed by the maintainer); revisit only with a new decision |

When a new plugin is added later, it must follow the same pattern: UI catalog through its `meta/registry.json` `i18n` key, prompts through a pack and `prompt_store`, and a new-language section in its own docs.

## 6. Order of work (checklist for an agent)

1. Read this guide, `docs/prompt-glossary.md`, `docs/i18n/conventions.md`. Create the branch in every repo you will touch.
2. Record baselines: `python scripts/prompts/snapshot_hashes.py --check`, `python scripts/prompts/validate_pack.py`, the i18n tests, and in the memory plugin `golden_snapshot.py --check` and `pytest`. All must pass **before** you start; if not, stop and report.
3. UI: code entries (2.1) → core `.po` (2.2) → JS catalogs (2.3) → plugin catalogs (2.4) → tooling/tests (2.5) → glossary (2.6). Commit after each.
4. Prompts: packs (3.2) → internal packs in seven locations (3.2) → validator (3.5). Commit after each.
5. Memory plugin (section 4). Commit in its repository.
6. Run every command of sections 2.7, 3.5 and 4. Compare failures with the baseline of step 2: only pre-existing, unrelated failures (e.g. missing optional dependencies such as `ray` in a light environment) are acceptable, and you must show they are identical before/after (`git stash`).
7. Mark the language `beta`/`draft`. Update this guide's table if you changed a coupling in 2.5, update `docs/i18n/contributing.md`, the README language mention, and release notes.
8. Hand over to the humans: native review, real experiment per platform, push/tag/release. An agent stops here.

## 7. Regression guard: what must not change

- English prompt hashes (`docs/prompt-hashes.json` via `snapshot_hashes.py --check`).
- English rendering of every internal prompt (`test_prompt_render_equivalence.py`).
- English memory output (`golden_snapshot.py --check`, `e2e_memory_sim.py --check-golden`).
- Protocol tokens and the `{field}` multiset of every text.
- The set of `.po` message ids of the core (`catalogs.py check` is clean) and the unmarked-strings ratchet (`scan_unmarked.py --check`).
- Italian translations: a new language must not edit any `it` file.
- Memory gating: `y_web/tests/test_memory_plugin_gate.py` (templates conditional on the plugin) keeps passing.

## 8. Release levels and sign-off

- **beta / draft**: translation complete enough to run but not natively reviewed or below 98% somewhere. The UI selector shows "(beta)" (`LANGUAGE_STATUS`), the prompt pack manifest says `"status": "draft"`.
- **stable**: coverage ≥ 98% in every area, glossary 0 violations, native review done (`reviewed_by` set in the manifest, language removed from `LANGUAGE_STATUS`), and the real experiment per platform passed (gate G4). The memory lexicons need their own review.
- Release notes list the new/promoted language, the plugins whose catalogs changed (their `.mo` are committed with each plugin), the models tested, and the known limits (sentiment, toxicity, missing coverage areas in section 5).

## 9. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Language missing from the UI selector | not in `YSOCIAL_LANGUAGES` / config default, or `.mo` not compiled/committed |
| Selector shows the raw code | no entry in `LANGUAGE_NAMES` |
| Some pages English | string unmarked (use the pseudo-locale), msgid not in the `.po`, plugin catalog not compiled |
| `validate_pack.py`: "files differ from English" | manifest `files` list does not match the folder |
| `validate_pack.py`: field mismatch | a `{field}` was translated, dropped or duplicated |
| `validate_pack.py`: protocol token missing | a token such as `COMMENT` was translated |
| `snapshot_hashes.py --check` fails | an English file was edited; revert |
| Generated posts in English although prompts are `fr` | the population language is English (agents' `language` attribute), not a prompt problem: create the population with the wanted language |
| Experiment prompts in English though `fr` selected | `prompt_language.json` not written for the experiment (client created before the language was set), pack missing, or model-side fallback warning in the logs |
| Memory blocks English in a French run | `memory_language` not passed (package older than 0.2.0) or `fr.json` missing a key (see the single warning in the log) |
| CI `coverage_report.py` fails | the new language is below 98% in some area (core, a plugin, or a JS domain) |
