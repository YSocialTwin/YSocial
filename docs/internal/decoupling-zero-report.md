# Decoupling to zero: final report (branch `decouple-zero`)

Goal: `y_web` (the core) names no platform; adding a platform, a recommender or a feature does not require editing the core.

## Result

| Measure | Before | After |
| --- | --- | --- |
| Platform names in the core, v1 (substring count) | 464 | ceiling unchanged (464), not the gate any more |
| Platform names in the core, v2 (whole words, minus declared exceptions) | 260 at the start of phase 1 | **0** (ceiling in `y_web/tests/data/decoupling_ceiling.json`) |
| Platform imports outside the SDK | 0 | 0 |

## Declared exceptions (`scripts/metrics/decoupling_allowlist.json`)

* D1: the physical names of the `forum_chat_*` and `forum_*_feed_resources` tables (no table rename; databases already created keep working).
* D2: Reddit and subreddit listings as a place feeds come from (a feed source, not a platform); may be externalized later.
* D3: legacy names read with a `DeprecationWarning` (`y_web/legacy_names.py`) and the deprecated SDK alias `process_reddit_post`; both go with the platform API 2.0.
* The glyph names `mdi-forum`/`mdi-reddit` of the vendored icon font.
* D7 (decided): the interview prompt shared by all platforms no longer says "Reddit-style" (now "like a real person online"); the English hash snapshot records this one intended change.

## What changed, by phase

0. Metric v2, allowlist, production-import check, characterization tests.
1. Neutral comments and docstrings.
2. Platform tours move to the platform repositories (`tutorial_scripts()`, SDK 1.6).
3. Runtime names declared by the providers; neutral process flag `Y_SOCIAL_SUBPROCESS`; `split_title_and_body`.
4. Platform prompts (internal prompts and packs) move to the platform repositories (`prompt_pack_roots()`); hashes unchanged.
5. Feed libraries, image-feed assignment and feed limits become a generic core service with neutral addresses; old forum addresses redirect (308) from the forum repositories; wording, tours and Italian catalogs without the platform name.
6. Remaining model/table names declared as exceptions; internal seq marker neutral.
7. Canary platform test, seeded-plugin list derived from the catalogue (with an independent count), discovery test aligned with API 1.6.
8. Extensions: out of scope for 4.1.0 (D5).

## Residual items to know about

* Environment variables `YSERVER_CONFIG`, `YSERVER_LOG_FILE`, `YCLIENT_LOG_FILE` are the protocol with the platform servers; the metric does not match them.
* Translation catalogs (`.po`) still contain some platform text of the platforms' own pages (excluded from the metric).
* `prompts_hpc.json` stays in the core: HPC is a shared mode.
* No end-to-end gateway test was added.
* Platforms written for an API older than 1.6 that register the feed addresses themselves must drop them (see `docs/upgrade-4.1.md`).
