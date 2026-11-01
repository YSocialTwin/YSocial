# Federation / World Simulation: multi-platform simulations (F0–F7 + extensions X/H/P0–P7)

Branch `federation` in every touched repository. Nothing has been pushed, merged or tagged. Federation is **off by default**: with no `federation` section in a member's config, every runtime behaves as before.

## What this adds

A coordinator-based federation (protocol v1.0, HTTP, `X-YFederation-Token`) that lets several YSocial runtimes (microblogging, forum, photo-sharing, instant messaging, dating) run as members of one "World Simulation":

- canonical clock (tick = day*24 + slot, base 0) with a round gate shared by all members;
- identity map, membership and dormant-account invisibility (INV-01..13);
- affective reports, an attention allocator, exposure.v1, platform discovery and federated leave/churn;
- cross-posting in two modes: `coordinator_rule` and `agent_action` (the agent draws per destination, text from the LLM via `crosspost_adapt_<dest>` prompts or from `rule_text`);
- extensions after F7: sharing of other agents' content across platforms with a structured `quoted` reference (microblogging, photo, IM forward, dating match-progress story; forum gated by `share.enabled`); **topic migration** (topics travel with cross-posts and are created on the destination); **human participants** (`human:<Admin_users.id>`, gateways on every runtime, excluded from group mechanisms, INV-14/15); **quote visibility** tracked by the coordinator (INV-16, `quoted.require_exposure`, event `quote_unseen`, attribution-post fallback); exposure credit for quotes (`discovery.quoted_weight`, default 0); optional **pseudonyms** (HMAC, applied at delivery only); pending-view for stopped members; per-destination text editing in the composers;
- YWeb: "World Simulation" section (create, validate, start/stop, schedule queue, notifications, member badges), derived analytics DB with CSV, export/import/clone/reset, en/it translations and docs.

## Commits per repository (`[MP-*]`)

| Repo | HEAD | Base | [MP-] commits |
|---|---|---|---|
| YSocial | 8f74704e | e47c1ded | 36 |
| YFederation | 96cb798 | be7e519 | 48 |
| YServer | 225a293 | 4ef02b95 | 13 |
| YServerReddit | c170c28 | 7ba9de97 | 14 |
| YClient | ab35c2e | f4d15a00 | 5 |
| YClientReddit | 9f0aa84 | 45ce83dd | 6 |
| YSimulator | ae9a922 | 34f4187b | 9 |
| YPhotoSharing | 9332dde | 160e534a | 11 |
| YInstantMessaging | 0ce875f | 3938965b | 11 |
| YDating | 3fc87ee | cebe3a6c | 12 |
| plugin-registry | 05d120b | (registry entry) | 1 (F5.8) |

Open the PRs in dependency order: YFederation first, then the runtimes and clients, then plugin-registry, then YSocial (which references the others through `external/plugins.json`). Full per-commit lists: `git log <base>..federation --oneline` in each repo.

## Verification

- Per-phase tests in each repo; no real LLM and no network in tests.
- Golden runs (F0.2) show no change in the non-federated behavior of the runtimes. Re-run with federation OFF at the final heads (after the extensions): YServer+YClient, YServerReddit+YClientReddit, YSimulator, YInstantMessaging and YDating compare **identical** to the baselines; YPhotoSharing differs only by the table `reported`, a drift that also exists at the merge-base (rounds and schema hashes equal).
- Extensions: tests per repo (quoted, topics, humans, visibility, pseudonyms, pending); P0 full suites without new failures; P2 fault tests (coordinator/member killed, delayed network) and a three-runtime federated run with determinism controls.
- Three-platform federated golden run (G3), fault tests (coordinator/member killed, delayed network), control experiments for the attention allocator.
- F7.3b: export → import → export gives equal content; the restored coordinator DB is identical; a real coordinator run with fake members gives the same logical DB for original and imported; a negative control differs.
- i18n ratchets (JS catalog keys, unmarked strings, `.po`/`.mo`) pass.

## Not verified / open items

- **F6.3 pilot not run** (Ollama qwen3:4b-instruct, 10 agents, 3 days, 3 platforms). Go criterion: cross-post rate within ±50% of the configured value and coherent sampled texts. Protocol in `docs/world-simulation.md`; to be run by the maintainer. Gate G6 closed by the maintainer's decision, not by this run.
- No run with the real runtimes and a real LLM end to end.
- **P6 pilot** with the extended protocol (`docs/world-simulation-pilot.md`) to be run by the maintainer; its verdict is not recorded here.
- `quoted` not exercised in a real-runtime run (needs news articles); covered by tests and the fake coordinator.
- YSimulator full test suite not completed (Ray stall); its golden run is identical.
- Browser checks of the new UI (attribution, humans, pseudonym option) not done; rendered banner not visually checked.
- The coordinator visibility check costs about 100 ms per tick.
- Human participants on HPC: no-go (out of scope).
- Forum share is gated (off unless `share.enabled` or agent_action); interpretation of the maintainer's request to re-enable it is by that gate.

## Deviations from the plan

1. F6.3 pilot not executed (above).
2. Cross-post destination member names must equal the platform type (needed to find the `crosspost_adapt_<dest>` prompt).
3. The YFederation registry entry is in `registry.json`, not in the builtin list.
4. The `external/plugins.json` commit also includes the previously local YDating/IM entries (per maintainer's decision).
5. D-04 = B: `attention.normalization` defaults to raw.
6. Commits `[MP-F8.1..3]` carry a mislabeled phase tag (they belong to the sharing extension X1–X3); history not rewritten without the maintainer's consent.
7. Human ids are `human:<Admin_users.id>` (D1); humans may join while the federation runs (D3); gateways for microblogging, forum and photo (D4); humans excluded from group mechanisms (D7); humans may share with `quoted` and local-username attribution (D8).

## Known baseline failures (unchanged by this work)

- YWeb: `test_im_experiment_switches::test_the_update_action_writes_server_and_client_files`; 4 dating, 2 IM, 2 chunk-05 tests; 3 HPC fault-injection.
- plugin-registry: `test_validate_registry::test_published_builtin_is_valid` (14 vs 13).
- YServer 3, YServerReddit 1, YClientReddit 3, YPhotoSharing 1 plus 8 collection errors.

## Notes for reviewers

- No existing tables, signatures or tests were modified; migrations are additive.
- plugin-registry tracks `__pycache__` files (pyc noise, not committed).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01DWbEUGGfGygHDZvdNDEM5G
