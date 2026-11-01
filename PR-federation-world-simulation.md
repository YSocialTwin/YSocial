# Federation / World Simulation: multi-platform simulations (F0–F7 + extensions X/H/P0–P7, H9/H10, P12/P13)

Branch `federation` in every touched repository. Nothing has been pushed, merged or tagged. Federation is **off by default**: with no `federation` section in a member's config, every runtime behaves as before.

## What this adds

A coordinator-based federation (protocol v1.0, HTTP, `X-YFederation-Token`) that lets several YSocial runtimes (microblogging, forum, photo-sharing, instant messaging, dating) run as members of one "World Simulation":

- canonical clock (tick = day*24 + slot, base 0) with a round gate shared by all members;
- identity map, membership and dormant-account invisibility (INV-01..13);
- affective reports, an attention allocator, exposure.v1, platform discovery and federated leave/churn;
- cross-posting in two modes: `coordinator_rule` and `agent_action` (the agent draws per destination, text from the LLM via `crosspost_adapt_<dest>` prompts or from `rule_text`);
- extensions after F7: sharing of other agents' content across platforms with a structured `quoted` reference (microblogging, photo, IM forward, dating match-progress story; forum gated by `share.enabled`); **topic migration** (topics travel with cross-posts and are created on the destination); **human participants** (`human:<Admin_users.id>`, gateways on every runtime, excluded from group mechanisms, INV-14/15); **quote visibility** tracked by the coordinator (INV-16, `quoted.require_exposure`, event `quote_unseen`, attribution-post fallback); exposure credit for quotes (`discovery.quoted_weight`, default 0); optional **pseudonyms** (HMAC, applied at delivery only); pending-view for stopped members; per-destination text editing in the composers;
- YWeb: "World Simulation" section (create, validate, start/stop, schedule queue, notifications, member badges), derived analytics DB with CSV, export/import/clone/reset, en/it translations and docs;
- later extensions (H9, H10, P12, P13), described in "Extensions H9, H10, P12, P13" below: people on HPC microblogging through a gateway script, profile badges and an Agents tab, flexible populations (identity by username, late clients, discovery and provisioning on platforms where the agent was not deployed, protocol 1.2) and `crosspost.content` (which agent content may be cross-posted).

## Commits per repository (`[MP-*]`)

| Repo | HEAD | Base | [MP-] commits |
|---|---|---|---|
| YSocial | 01ada0e7 | e47c1ded | 47 |
| YFederation | 2810fd4 | be7e519 | 61 |
| YServer | 984fb12 | 4ef02b95 | 17 |
| YServerReddit | 729411d | 7ba9de97 | 18 |
| YClient | bac6bb6 | f4d15a00 | 8 |
| YClientReddit | 2160a5e | 45ce83dd | 9 |
| YSimulator | 023f57b | 34f4187b | 13 |
| YPhotoSharing | 039dbae | 160e534a | 13 |
| YInstantMessaging | e10324b | 3938965b | 13 |
| YDating | 29f49f7 | cebe3a6c | 14 |
| plugin-registry | 05d120b | (registry entry) | 1 (F5.8, unchanged) |

HEADs and counts updated to the state after H9, H10, P12 and P13 (counted with `git log <base>..HEAD --oneline | grep -c '\[MP-'` in each repo; YSocial also has 16 commits without the `[MP-]` tag in the range, YServerReddit 2 and YClientReddit 1).

Open the PRs in dependency order: YFederation first, then the runtimes and clients, then plugin-registry, then YSocial (which references the others through `external/plugins.json`). Full per-commit lists: `git log <base>..federation --oneline` in each repo.

## Verification

- Per-phase tests in each repo; no real LLM and no network in tests.
- Golden runs (F0.2) show no change in the non-federated behavior of the runtimes. Re-run with federation OFF at the heads of the previous version of this text (after X/H/P0–P7): YServer+YClient, YServerReddit+YClientReddit, YSimulator, YInstantMessaging and YDating compare **identical** to the baselines; YPhotoSharing differs only by the table `reported`, a drift that also exists at the merge-base (rounds and schema hashes equal). **After H9, H10, P12 and P13 only the YServer and YServerReddit quick runs were re-executed (identical to the baselines, before and after the P12 fixes); the golden runs of YSimulator, YInstantMessaging, YDating, YPhotoSharing and of the two clients were NOT re-run at the new heads.**
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
- Human participants on HPC: now implemented for microblogging through the gateway script (H9, see below); photo sharing, messaging and dating were already on HPC with their own gateways.
- Forum share is gated (off unless `share.enabled` or agent_action); interpretation of the maintainer's request to re-enable it is by that gate.

## Extensions H9, H10, P12, P13

All of them are additive and off by default: without a `federation` section nothing runs, and a World Simulation that does not use the new options writes the same files as before.

### H9: people on microblogging experiments of the HPC backend

The HPC server (YSimulator) is a Ray actor with no HTTP surface, so the gateway is a script, `run_human_gateway.py`, that works with the server running or stopped (JSON on stdin, file lock) and writes the same marks as an agent (`federation_export`, `federation_crosspost`) plus the table `federation_human`. Identity `human:<id>` without fallback to the local id; people are left out of exposures, affective report, churn and attention (INV-14, INV-15). YWeb uses `RuntimeGateway(hpc=True)`; YWeb still writes no runtime database (INV-11).

| Repo | Commit |
|---|---|
| YSimulator | `6cd417d` [MP-H9.1] human gateway for HPC microblogging |
| YFederation | `fe5881b` [MP-H9.2] docs: humans on the HPC simulator |
| YSocial | `262809db` [MP-H9.3] people on microblogging experiments of the HPC backend |

Limits: the gateway writes the database directly and the server reads the rows at its next barrier; Redis-backed caches are not refreshed by it (as for posts written by YWeb on that backend); `quoted` is not implemented in the YSimulator adapter.

### H10: profile badges and Agents tab (YSocial, read-only on `federation.db`)

| Commit | What |
|---|---|
| YSocial `feff66e9` [MP-H10.1] | the profile page of every platform shows one badge for each other member where the same identity has an account, linking to the profile there (dormant and left accounts hidden; nothing rendered outside a World Simulation) |
| YSocial `3ca8ae56` [MP-H10.2] | page `/admin/world_simulation/<id>/agents`: state of each agent or person per platform (active, dormant, left, ineligible, not started), counts per platform, filters, pagination, CSV |

### P12: flexible populations (INV-17, INV-18, INV-19; protocol 1.2, additive, the version string stays `1.0`)

Identity by username (the local account id is reported by the runtime: `POST /v1/expected`, `POST /v1/bind`, `GET /v1/provision`); members with disjoint or partly overlapping populations; clients added while the simulation runs (active when bound, full action rate, no barrier stall); discovery of platforms where the agent was not deployed (a join decision becomes a provision request, the runtime creates the account, the client adopts it). SDK: `BindingBook`, `BoundAccountsMixin`, adapter methods `account_bindings`, `bindings_reported`, `provision_accounts`. Specification: `external/YFederation/docs/flexible-populations.md` and the technical reference.

| Repo | Commits |
|---|---|
| YFederation | `11c54af` P12.1 coordinator (identity by username, late clients, discovery); `4dff359` P12.2 SDK; `74c1c32` P12.4 BindingBook; `af3ae2d` P12.5 binding marker; `3dc513f` P12.7 BoundAccountsMixin; `ea55069` P12.16 real-server run; `eeabe29` P12.18 docs; `706e4a6` P12.22 attention fix; `2810fd4` P12.27 quantitative run |
| YServer | `9ec0b53` P12.6 report by username; `986a2c0` P12.13 provision; `984fb12` P12.23 stale clients released |
| YServerReddit | `03ccf79` P12.8; `f3364ec` P12.19; `729411d` P12.24 |
| YSimulator | `e9c5dd6` P12.9; `e0d11da` P12.17 |
| YPhotoSharing | `068d28f` P12.10; `039dbae` P12.21 |
| YInstantMessaging | `51d5e53` P12.11; `e10324b` P12.15 |
| YDating | `c4025d1` P12.12; `29f49f7` P12.16 |
| YClient | `c2f1f85` P12.14 adopt provisioned accounts; `bac6bb6` P12.25 agent class of the experiment |
| YClientReddit | `534fa2b` P12.20; `2160a5e` P12.26 |
| YSocial | `77a8d49b` P12.3 populations may differ, agents by username; `188db6d0` P12.15 bindings file, provisioning option, populations declared at run time; `48ecbd13` P12.17 configuration reference; `115928f1` P12.22 docs |

Measured end to end (`tests/integration/test_p12_quantitative.py`, 4 passed in 103 s; real YServer + YClient and YServerReddit + YClientReddit, YInstantMessaging as a third member in one scenario; rule-based agents, no language model; disjoint and overlapping populations, a late client on day 3, discovery with provisioning, forum member killed and restarted on day 5; standalone controls with the same seed and settings): actions per agent per platform, federated against control, ratio 0.90 to 1.03 over 3 seeds of 8 days pooled (|z| below 1.3); every attention multiplier 1.0; barrier 192 of 192 ticks, never stalled (restart gap about 2 s); no duplicate account and no identity mismatch after the member restart; messaging ratio 1.0; no `inv02_violation`. The measurement found two defects, both fixed in this PR set: an agent that discovered a provisioned platform started at attention weight 0 and ended with multiplier 0.3 instead of 1.0 (`706e4a6`), and a restarted member could hold the barrier forever because the killed client stayed `active` (`984fb12`, `729411d`).

### P13: which agent content may be cross-posted (`crosspost.content`)

`crosspost.content` is `["all"]` (default, nothing changes: all content, the agent's own and that of other agents) or a non-empty list of additive options `own_content`, `news`, `images` (`own_posts` is the legacy alias): each adds a category and content is eligible when it fits at least one (OR), so choosing more never reduces what travels; a stored list of two or more entries from the earlier AND form now reads as OR. The coordinator is the single authority (`content_policy.py`): content that is eligible for none is dropped (agent_action) or not drawn (coordinator_rule), the batch is never rejected, and one `crosspost_filtered` event (`not_eligible`, with the chosen options) records it; people are never filtered. Optional `link` field in `content.v1` and `crosspost.v1` (article URL), written by the servers only when `crosspost.content` includes `news`. The clients offer the cross-post of a share only when it can be eligible (`all`, `news` or `images`). YWeb: an explicit "All content" option ticked by default plus three additive checkboxes in the creation form and in the detail page, at least one required, editable while the simulation is stopped (read at each start or restart), exported, imported and cloned.

| Repo | Commit |
|---|---|
| YFederation | `3e7e114` P13.1 coordinator, policy, event, `link` field |
| YServer | `9c284ff` P13.2 article link in the content |
| YServerReddit | `85d7059` P13.3 |
| YSimulator | `023f57b` P13.4 |
| YClient | `06fae46` P13.5 no cross-posted share when only `own_content` is chosen |
| YClientReddit | `4721d76` P13.6 |
| YSocial | `7c75418d` P13.7 YWeb option; `01ada0e7` P13.8 docs |

### What was and was not verified for these extensions

Verified: unit and integration tests of each commit (see the commit messages), the quantitative run above, and the YServer and YServerReddit quick golden runs (identical to the baselines).

Not verified, stated honestly:

- Golden runs of YSimulator, YInstantMessaging, YDating, YPhotoSharing and of the clients with federation off were **not** re-run after these extensions (only YServer and YServerReddit were).
- **No browser check** of the new UIs (Agents tab, profile badges, the content checkboxes, the HPC enrolment of people); they were checked through tests only.
- `crosspost.content` was **not tested with YPhotoSharing, YInstantMessaging or YDating**.
- Adoption of provisioned accounts by the clients is only **partly covered end to end**: real servers and clients for YServer + YClient and YServerReddit + YClientReddit; the other runtimes are covered by unit tests of their adapters.
- YSimulator with flexible populations was **not run on Ray**.
- The quantitative run uses rule-based agents; no run with a real language model.
- Pre-existing failing tests are listed under "Known baseline failures".
- World Simulations created before protocol 1.2 must be relaunched (created again, or saved and started again) to get `bindings_file` and identities by username; the same holds for `crosspost.content`, which is read at each start.
- The three extra commits `[MP-F8.1..3]` keep a mislabeled phase tag (deviation 6).

## Deviations from the plan

1. F6.3 pilot not executed (above).
2. Cross-post destination member names must equal the platform type (needed to find the `crosspost_adapt_<dest>` prompt).
3. The YFederation registry entry is in `registry.json`, not in the builtin list.
4. The `external/plugins.json` commit also includes the previously local YDating/IM entries (per maintainer's decision).
5. D-04 = B: `attention.normalization` defaults to raw.
6. Commits `[MP-F8.1..3]` carry a mislabeled phase tag (they belong to the sharing extension X1–X3): YFederation `7448496` (F8.1), YServer `e0ac368` (F8.2) and YClient `ab35c2e` (F8.3); history not rewritten without the maintainer's consent. These are the only `[MP-F8.*]` commits; they are counted in the table above.
7. Human ids are `human:<Admin_users.id>` (D1); humans may join while the federation runs (D3); gateways for microblogging, forum and photo (D4); humans excluded from group mechanisms (D7); humans may share with `quoted` and local-username attribution (D8).

## Known baseline failures (unchanged by this work)

Failing tests reported as pre-existing, that is, not caused by H9, H10, P12 or P13 (none was investigated or fixed here):

- `test_report_route_persists_report` (the test exists in YServer and YServerReddit);
- `test_length_enforcement` (3 failures);
- `test_run_server_readiness`;
- the photo linkification test (`test_photo_feed_template::test_photo_text_linkification` in YWeb, which fails also without the profile-badge change);
- the YServerReddit barrier test fixture, which fails with `no such table: user_mgmt`.

The repository of `test_length_enforcement` and `test_run_server_readiness` is not recorded in this text (the names were not found in the working trees when it was written).

Earlier list:

- YWeb: `test_im_experiment_switches::test_the_update_action_writes_server_and_client_files`; 4 dating, 2 IM, 2 chunk-05 tests; 3 HPC fault-injection.
- plugin-registry: `test_validate_registry::test_published_builtin_is_valid` (14 vs 13).
- YServer 3, YServerReddit 1, YClientReddit 3, YPhotoSharing 1 plus 8 collection errors.

## Notes for reviewers

- No existing tables, signatures or tests were modified; migrations are additive.
- plugin-registry tracks `__pycache__` files (pyc noise, not committed).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01DWbEUGGfGygHDZvdNDEM5G
