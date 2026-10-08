# Non-Personalized Content Recommenders: Analysis and Remediation Plan

## Scope

This document analyzes the recommender choices other than **Personalized Feed** in experiment 1, using user 8 and the linked microblogging experiment as the test bed. It is intentionally a design document; it is not part of the implementation change and should remain untracked.

## Executive diagnosis

The feed endpoint is dispatching per-user recommendations correctly: for `/1/feed/8/...`, the selected value is `user.recsys_type`, and both the HTML and API routes call the same `get_suggested_posts()` service. The problem is downstream of dispatch and has two different forms:

1. **Genuinely random results.** `ContentBasedVector` and `HybridLinearRanker` are present in the recommender catalog and can be stored on a user, but there is no corresponding ranking branch. They reach the final “random/unrecognised mode” query. `ContentRecSys`, `default`, unknown values, and the `random` alias also intentionally use that branch.
2. **Reverse-chronological results.** Several implemented algorithms require interests, follows, reactions, or similar-user data. When those prerequisites are absent, they silently call the reverse-chrono fallback. In the linked experiment, user 8 has declared topic preferences, but no rows in the legacy `user_interest` table, no reactions, and no follows. Consequently, interest-based and collaborative choices appear to be reverse chrono even though a recommender was selected.

These cases must not be fixed with one global fallback change: random is a valid baseline, while unsupported modes need implementation or removal, and cold-start modes need an explicit data contract and observable fallback policy.

## Evidence from the linked experiment

Database: `y_web/experiments/e436722f_632d_4e35_9389_1ecacd63fede/database_server.db` (experiment 1).

User 8 (`us1`) is configured as `FilterBubble` and has two `user_topic_interest` rows (Climate Change = 1.0, FIFA 2026 = 0.0). However:

| prerequisite | rows for user 8 |
|---|---:|
| legacy `user_interest` | 0 |
| reactions | 0 |
| follows | 0 |

Direct calls to the recommender service for the same user and page show the current behavior:

| selected mode | observed behavior | immediate reason |
|---|---|---|
| `ReverseChrono`, `ReverseChronoPopularity`, `ReverseChronoComments` | expected baseline ordering | these are baseline modes |
| `ReverseChronoFollowers`, `ReverseChronoFollowersPopularity` | empty primary portion plus reverse-chrono additions | no follows |
| `CommonInterests`, `CommonUserInterests`, `ContentBasedFeatures` | reverse-chrono results | query `user_interest`; user 8 has no legacy rows |
| `SimilarUsersReactions` | empty primary portion plus reverse-chrono additions | no usable similar users/reactions |
| `CollaborativeUserUser`, `CollaborativeItemItem` | reverse-chrono results | no reactions/likes |
| `SimilarUsersPosts` | underfilled/split result, with possible overlap with reverse additions | no reliable same-leaning population and no deduplicating merge |
| `ContentBasedVector` | random-looking results | no implementation branch; final random query |
| `HybridLinearRanker` | random-looking results | no implementation branch; final random query |
| `ContentRecSys` | random results | intentional default/baseline alias |
| `FilterBubble` | topic/opinion-ranked results | implemented personalized path |

The comparison is meaningful only for `/1/feed/8/...`; `/1/feed/all/...` intentionally bypasses per-user selection and requests reverse chronology.

## End-to-end causes

### 1. Catalog/code coverage is incomplete

The catalog advertises `ContentBasedVector` and `HybridLinearRanker`, and profile editing can persist either value, but `get_suggested_posts()` has no branches for them. They fall through to `order_by(func.random())`. The catalog, normalization aliases, and executable ranking branches therefore do not form one validated contract.

### 2. Declared preferences and behavioral interests are different stores

The profile/onboarding flow writes explicit choices to `user_topic_interest`. The interest-based recommenders currently read legacy `user_interest`, which is populated by interaction/exposure paths. A user can therefore have a valid profile configuration while still looking like a cold-start user to `CommonInterests`, `CommonUserInterests`, and `ContentBasedFeatures`. Treating an empty behavioral history as proof of “no interests” is the principal reason user 8 falls back to reverse chrono.

### 3. Cold-start fallback is silent

The service returns only posts, not the effective mode, ranking source, prerequisites, or fallback reason. The UI consequently cannot distinguish “the selected recommender ranked these posts” from “the recommender had no data and used reverse chrono.” Logs and metrics do not currently provide a stable per-request outcome contract either.

### 4. Defaults and unknown values converge on random

An empty experiment default becomes `default`; normalization maps `default`, `contentrecsys`, and `random` to the random baseline. Profile updates do not validate the submitted value against the catalog. A stale, misspelled, or unsupported value therefore looks like a successful selection but produces random output.

### 5. Split-feed fallbacks can be incomplete or duplicated

Follower/similarity modes allocate a primary and an additional portion. If the primary query is empty, the reverse-chrono addition can be short; `SimilarUsersPosts` can also overlap primary and fallback rows because the merge does not consistently exclude already selected post IDs. This makes a valid fallback look like a broken or unstable recommender.

### 6. The baseline is not time-safe for all data shapes

The reverse-chrono tie breaker uses `Post.id` after simulation time ordering. UUID IDs are lexicographic rather than temporal, so equal-time rows can appear arbitrary. This is secondary to the mode issue, but deterministic verification should use an explicit timestamp plus stable ID tie breaker.

## Remediation plan

### P0 — Establish a recommender contract

Create one canonical registry consumed by the catalog validation, normalization, profile update, dispatcher, and tests. Each entry should declare:

- canonical mode and aliases;
- implementation status (`implemented`, `baseline`, or `unsupported`);
- required data sources (declared interests, behavioral interests, follows, reactions, post features);
- cold-start policy;
- whether random output is permitted.

Reject or hide catalog entries marked unsupported. In particular, either implement `ContentBasedVector` and `HybridLinearRanker` or remove them from selectable options until they have deterministic ranking code. Keep `ContentRecSys`/`Random` explicitly labelled as the baseline rather than treating them as an accidental fallback.

### P0 — Define the preference data contract

For profile-oriented modes, read declared `user_topic_interest` first and map topic IDs to post features. Use legacy `user_interest` only as a documented behavioral signal or secondary fallback. For collaborative modes, require actual reactions; do not synthesize reactions from profile preferences. For user-similarity modes, define whether similarity is based on declared interests, behavior, or both, and require enough overlap before ranking.

Add migration/adapter tests so a user with explicit interests but no history is not incorrectly classified as having no profile signal.

### P1 — Make fallback observable and deterministic

Return or record a structured ranking outcome alongside posts, for example:

```text
requested_mode, effective_mode, source, fallback_reason, prerequisites, candidate_count
```

Use typed reasons such as `no_declared_interests`, `no_behavior_history`, `no_follow_graph`, `unsupported_mode`, and `unknown_mode`. Emit a metric/log event per fallback. Preserve a deterministic reverse-chrono fallback, but make it visible to the UI and test harness.

### P1 — Validate profile selection

Canonicalize aliases on write, validate against the registry, and reject unsupported/unknown values with a user-visible error. Validate experiment defaults at startup and when users join. Never silently turn a stale catalog value into random output.

### P1 — Implement or retire the missing algorithms

Implement `ContentBasedVector` with a defined feature/vector representation and deterministic similarity ordering. Implement `HybridLinearRanker` with explicit component scores and weights, including normalization and tie breaking. If either is not in scope, remove it from the catalog and return `unsupported_mode` rather than random results.

### P1 — Correct split-feed assembly

Merge primary and fallback candidates with a `NOT IN` set of already selected IDs, fill the requested page size when candidates exist, and preserve stable pagination. Apply this to follower and similar-user modes before changing ranking quality.

### P2 — Unify endpoint and baseline behavior

Keep HTML and API routes on the same service and expose the structured outcome to both. Add an explicit test that `/feed/all` is a global baseline while `/feed/8` uses the stored per-user mode. Use timestamp plus stable ID for deterministic reverse-chrono ordering.

## Automatic verification plan

Use a disposable copy of the linked experiment database; never mutate the experiment fixture in place.

1. **Registry coverage test:** every selectable catalog mode has exactly one canonical normalization entry and one executable branch; unsupported entries are absent or return `unsupported_mode`. Assert that only explicit `Random`/`ContentRecSys` requests issue a random query.
2. **Profile persistence test:** submit every catalog value through the edit-profile path; verify canonical storage, rejection of invalid values, and preservation after reload.
3. **User 8 smoke matrix:** for `/1/feed/8/feed/rf/1` and the matching API endpoint, select each mode and assert the returned outcome includes the requested/effective mode and a reason when fallback occurs. With the current fixture, interest/collaborative/follower modes should report their missing prerequisites rather than silently claiming a ranked result.
4. **Declared-interest cold-start test:** give user 8 only the existing Climate Change preference, select `CommonInterests` and `ContentBasedFeatures`, and assert topic-relevant posts are ranked without requiring a legacy `user_interest` row.
5. **Behavioral/collaborative fixtures:** add controlled follows, reactions, and similar users; assert each mode changes ranking, remains deterministic, fills the page, and contains no duplicate IDs.
6. **Missing-algorithm test:** select `ContentBasedVector` and `HybridLinearRanker`; assert either a deterministic ranked result from the new implementation or a clear `unsupported_mode` response—never an unlabelled random result.
7. **Pagination and parity test:** compare HTML/API page 1 and page 2 for the same user and mode; assert stable ordering, no overlap across pages, and identical effective-mode metadata.
8. **Regression suite:** run existing recommender, profile persistence, experiment configuration, and Personalized Feed tests. Include a test proving `FilterBubble` still uses declared interests/opinions and is not routed through the generic fallback.

## Acceptance criteria

The work is complete when every selectable mode has a documented implementation and prerequisite contract; user 8's declared preferences are usable by profile-based modes; unsupported/unknown selections cannot silently produce random output; cold-start fallbacks are explicit, deterministic, deduplicated, and page-filling; and the automated matrix verifies the same behavior through both feed endpoints without regressing Personalized Feed.
