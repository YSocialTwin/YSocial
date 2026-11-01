# Federation / World Simulation: multi-platform simulations (F0–F7)

Branch `federation` in every touched repository. Nothing has been pushed, merged or tagged. Federation is **off by default**: with no `federation` section in a member's config, every runtime behaves as before.

## What this adds

A coordinator-based federation (protocol v1.0, HTTP, `X-YFederation-Token`) that lets several YSocial runtimes (microblogging, forum, photo-sharing, instant messaging, dating) run as members of one "World Simulation":

- canonical clock (tick = day*24 + slot, base 0) with a round gate shared by all members;
- identity map, membership and dormant-account invisibility (INV-01..13);
- affective reports, an attention allocator, exposure.v1, platform discovery and federated leave/churn;
- cross-posting in two modes: `coordinator_rule` and `agent_action` (the agent draws per destination, text from the LLM via `crosspost_adapt_<dest>` prompts or from `rule_text`);
- YWeb: "World Simulation" section (create, validate, start/stop, schedule queue, notifications, member badges), derived analytics DB with CSV, export/import/clone/reset, en/it translations and docs.

## Commits per repository (`[MP-*]`)

| Repo | HEAD | Base | [MP-] commits |
|---|---|---|---|
| YSocial | 5e81ae21 | e47c1ded | 16 (F5.1–F5.8, F6.2j, F7.1–F7.4, F7.3b, F5.7b) |
| YFederation | 9f13c89 | be7e519 | 38 (F0.2a–F7.4) |
| YServer | 690cad8 | 4ef02b95 | 7 |
| YServerReddit | 543bded | 7ba9de97 | 7 |
| YClient | 91d2bc4 | f4d15a00 | 4 |
| YClientReddit | 24dc97b | 45ce83dd | 5 |
| YSimulator | 22accc9 | 34f4187b | 8 |
| YPhotoSharing | e972601 | 160e534a | 7 |
| YInstantMessaging | 59634f5 | 3938965b | 7 |
| YDating | cf34b3f | cebe3a6c | 7 |
| plugin-registry | 05d120b | (registry entry) | 1 (F5.8) |

Open the PRs in dependency order: YFederation first, then the runtimes and clients, then plugin-registry, then YSocial (which references the others through `external/plugins.json`). Full per-commit lists: `git log <base>..federation --oneline` in each repo.

## Verification

- Per-phase tests in each repo; no real LLM and no network in tests.
- Golden runs (F0.2) show no change in the non-federated behavior of the runtimes.
- Three-platform federated golden run (G3), fault tests (coordinator/member killed, delayed network), control experiments for the attention allocator.
- F7.3b: export → import → export gives equal content; the restored coordinator DB is identical; a real coordinator run with fake members gives the same logical DB for original and imported; a negative control differs.
- i18n ratchets (JS catalog keys, unmarked strings, `.po`/`.mo`) pass.

## Not verified / open items

- **F6.3 pilot not run** (Ollama qwen3:4b-instruct, 10 agents, 3 days, 3 platforms). Go criterion: cross-post rate within ±50% of the configured value and coherent sampled texts. Protocol in `docs/world-simulation.md`; to be run by the maintainer. Gate G6 closed by the maintainer's decision, not by this run.
- No run with the real runtimes and a real LLM end to end.
- F8 (optional) not started; only after explicit go-ahead.

## Deviations from the plan

1. F6.3 pilot not executed (above).
2. Cross-post destination member names must equal the platform type (needed to find the `crosspost_adapt_<dest>` prompt).
3. The YFederation registry entry is in `registry.json`, not in the builtin list.
4. The `external/plugins.json` commit also includes the previously local YDating/IM entries (per maintainer's decision).
5. D-04 = B: `attention.normalization` defaults to raw.

## Known baseline failures (unchanged by this work)

- YWeb: `test_im_experiment_switches::test_the_update_action_writes_server_and_client_files`; 4 dating, 2 IM, 2 chunk-05 tests; 3 HPC fault-injection.
- plugin-registry: `test_validate_registry::test_published_builtin_is_valid` (14 vs 13).
- YServer 3, YServerReddit 1, YClientReddit 3, YPhotoSharing 1 plus 8 collection errors.

## Notes for reviewers

- No existing tables, signatures or tests were modified; migrations are additive.
- plugin-registry tracks `__pycache__` files (pyc noise, not committed).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01DWbEUGGfGygHDZvdNDEM5G
