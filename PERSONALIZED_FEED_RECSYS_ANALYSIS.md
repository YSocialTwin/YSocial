# Personalized Feed recommender: failure analysis and remediation plan

Date: 2026-09-16  
Scope: microblogging edit-profile selection and feed ranking, using experiment `1`, user `8` as the concrete test bed  
Status: analysis only; this document is intentionally untracked and must not be added to Git

## Executive summary

The edit-profile save path is not the primary failure in the reported case. The selected content recommender is persisted correctly: experiment `1`, user `8` currently has `user_mgmt.recsys_type = 'FilterBubble'`.

The feed nevertheless looks reverse chronological because the Personalized Feed scorer assumes integer post and round identifiers. Experiment `1` is an HPC experiment whose post IDs, round IDs, author IDs, topic IDs, and opinion IDs are UUID strings. The scorer fails while converting an HPC round UUID to `int`, catches the exception, returns an empty score dictionary, and `get_suggested_posts()` deliberately and silently falls back to reverse chronological order. This exactly matches the observed symptom.

There are additional defects that would still prevent a correct and reliably testable implementation after fixing the first conversion:

1. post UUIDs are interpolated into an SQL `IN` expression without parameters or quotes;
2. ranked post UUIDs are converted to `int`;
3. opinion history treats a round identifier as an ordered integer instead of joining through `rounds.day/hour`;
4. all scorer/data errors are hidden and made indistinguishable from a legitimate cold start;
5. unscored posts are ordered by UUID rather than simulation time;
6. the configured `filter_bubble_sort` and `filter_bubble_lr` values are not honored end to end;
7. the current linked data can prove interest-based ranking but cannot prove opinion-similarity ranking, because none of the authors of the candidate posts has an opinion row;
8. there is no automated Personalized Feed coverage.

The repair should make identifiers opaque strings, derive chronology from the `rounds` table, parameterize every SQL query, distinguish “no personalization data” from “ranking failed,” add deterministic tie-breaking, and cover both integer-ID Standard databases and UUID-ID HPC databases.

## Concrete evidence from the linked experiment

The source-mode SQLite dashboard is `y_web/db/dashboard.db`. It maps experiment `1` to:

```text
y_web/experiments/e436722f_632d_4e35_9389_1ecacd63fede/database_server.db
```

Experiment metadata:

```text
idexp = 1
name = microblogging
platform = microblogging
simulator_type = HPC
status = active
```

The relevant user row is:

```text
id = 8
username = us1
user_type = user
is_page = 0
recsys_type = FilterBubble
frecsys_type = FollowRecSys
```

This proves that the POST handled by `update_profile_data()` successfully persisted the selection. The feed reads the same `user.recsys_type` value before calling `get_suggested_posts()`, so there is no stale browser cache or separate feed preference involved.

User `8` has the following actual personalization data:

| Topic | Experiment topic ID | Interest | Opinion |
|---|---|---:|---:|
| Climate Change | `d0f183ca-7a16-46fc-9493-553fa45a25ba` | 1.0 | 0.9 |
| FIFA 2026 | `9cd76d3a-71be-455c-b3e8-5f89cbd0ca75` | 0.0 | 0.5 |

There are 22 posts and 24 post-topic associations. Among the eligible root posts, three are about Climate Change and eight are about FIFA 2026. With the current settings (`alpha=2`, `beta=0`, `gamma=0`, `sort=score`), the three Climate Change posts should precede FIFA posts because Climate Change has interest `1.0` while FIFA has interest `0.0`.

The expected top set for the current data is:

```text
539388cf-44a7-47ec-829a-2eb761d5ee17
7973189c-1592-4fe3-8777-1bee9eb0aef3
dd1d3eca-7240-4358-807a-b25aebb4b5b2
```

The order within this set should use an explicit deterministic tie-breaker. With score first and reverse simulation time second, the order shown above is correct.

A direct call of the current implementation was made against the linked experiment database:

```python
_filter_bubble_score(8, create_engine("sqlite:///.../database_server.db"), {})
```

It returned `{}` even though the preference and topic data shown above exists. No web server was listening on port 8080 during this analysis, so endpoint-level reproduction was not possible; the database state and direct scorer invocation are sufficient to locate the backend defect.

## End-to-end request flow

### Selection and persistence

1. `GET /1/edit_profile/8` loads user `8` from the experiment bind.
2. `edit_profile.html` renders `<select name="recsys_type">` using the dashboard `content_recsys` catalog.
3. The option label “Personalized Feed” posts its canonical value `FilterBubble`.
4. `POST /1/update_profile_data/8` assigns `request.form['recsys_type']` to `user.recsys_type` and commits.
5. The linked database confirms the committed value is `FilterBubble`.

### Feed resolution

1. `GET /1/feed/8/feed/rf/1` loads user `8`.
2. It reads `user.recsys_type`, not the `rf` URL segment, as the ranking algorithm.
3. `FilterBubble` is recognized and the experiment engine plus `filter_bubble_*` settings are passed to `get_suggested_posts()`.
4. `_filter_bubble_score()` attempts to build the personalized score map.
5. The score map is empty after an internally swallowed UUID conversion error.
6. The `FilterBubble` branch treats an empty map as cold start and returns reverse-chronological results.
7. Infinite scrolling calls the parallel `/1/api/feed/8/feed/rf/<page>` route, which uses the same failing scorer and fallback.

The `/feed/all/...` route intentionally bypasses per-user recommendation. It must not be used to verify this fix; the test URL must retain user `8`.

## Root causes

### P0: the scorer is incompatible with HPC UUID identifiers

`_filter_bubble_score()` reads `post.round` and executes the equivalent of:

```python
"round_id": int(round_id)
```

In experiment `1`, a round ID looks like `205c70bb-cc9e-4647-8c82-96450674bc5f`. Converting it to `int` raises `ValueError`. The broad outer `except Exception` returns `{}` and the caller falls back to reverse chronology.

Two more UUID failures are waiting behind this one:

- `scores[int(post_id_str)] = ...` cannot convert a post UUID to an integer;
- `WHERE id_post IN (` plus comma-joined raw UUIDs produces invalid SQL and is silently ignored.

The scorer therefore cannot produce a personalized ranking for this HPC experiment in its current form.

### P0: failure and cold start have the same return value

The scorer returns `{}` for all of these materially different conditions:

- the user has no preferences;
- there are no tagged candidate posts;
- the query/schema is incompatible;
- ID conversion fails;
- the experiment engine is wrong or unavailable.

The caller then silently substitutes reverse chronology. This turns a production defect into plausible-looking output and is why the issue is hard to detect.

### P1: opinion chronology is modeled using identifier ordering

The code assumes `agent_opinion.tid` and `post.round` are comparable integer round numbers, uses a numeric 36-round window, and uses `bisect` over converted `tid` values. That is not valid for the HPC schema, where round primary keys are UUIDs.

Chronology must come from a join to `rounds`, using `(day, hour)` and a deterministic secondary key. An identifier must never be used as elapsed time or sequence merely because Standard databases happen to use increasing integer IDs.

### P1: current data does not exercise opinion similarity

User `8` has opinions, but the authors of all candidate Climate Change and FIFA posts have no `agent_opinion` records. The scorer consequently uses its neutral-author fallback for every candidate. The linked data can validate interest gating—Climate Change before FIFA—but cannot validate whether a post author close to user opinion `0.9` outranks an opposing author.

This is a test-data limitation, not a reason to skip opinion verification. The automated test should copy the linked database and add two controlled, otherwise equivalent Climate Change candidates with author opinions `0.9` and `0.1`.

### P1: unscored ordering is not chronological

After ranked posts, the implementation appends unscored posts using `ORDER BY post.id DESC`. For UUID IDs this is lexicographic and unrelated to simulation time. This makes the remainder of the “Personalized Feed” appear random.

Use score descending, then `rounds.day DESC`, `rounds.hour DESC`, and finally a stable string form of post ID. Apply the same simulation-time ordering to unscored fill content.

### P1: configuration is only partially wired

- `filter_bubble_sort` is exposed and persisted but never changes ranking behavior.
- `filter_bubble_lr` is exposed and persisted, but interaction updates hard-code `0.05`.
- the interaction hook updates only when the stored mode is exactly `FilterBubble`, while feed selection accepts aliases.
- errors in adaptive-interest updates are also silently swallowed.

These do not cause the initial fallback, but they violate the advertised configuration contract and will make later behavior difficult to explain and test.

### P1: no regression tests cover Personalized Feed

No test currently mentions `FilterBubble`, `Personalized Feed`, or `filter_bubble`. Existing recommender tests therefore cannot detect the broken HPC path, the fallback, persistence/catalog mismatches, or drift between the initial HTML route and infinite-scroll API.

### P2: catalog/migration and visibility risks

The runtime dashboard currently has the correct catalog row:

```text
name=FilterBubble, value=Personalized Feed,
category=Personalization, enabled=HumanOnly
```

The seed database under `data_schema/` did not contain it at inspection time; startup migration adds it to the writable runtime database. Deployment tests should verify both fresh bootstrap and upgrade paths so the edit form never drops the current value and implicitly selects the first option.

Also, `_load_recsys_options()` currently includes every enabled algorithm for any HPC experiment before applying the `HumanOnly` condition. Thus `FilterBubble` can be exposed to agent/bot profiles in HPC despite its declared scope. The filtering logic should explicitly exclude `HumanOnly` unless `include_human_only=True`.

### P2: global experiment-bind mutation is concurrency-sensitive

Experiment routing replaces `db.engines['db_exp']` globally. A context manager does not make that mutation thread-local, so overlapping requests for different experiments can observe another experiment's engine. This was not needed to reproduce the present bug, but it is a systemic risk for all recommendation and profile paths. A longer-term correction should use explicit experiment-scoped sessions/engines instead of mutating a shared engine registry.

## Recommended implementation

### 1. Separate data loading, scoring, and pagination

Introduce a small service with explicit inputs and outputs, for example:

```python
rank_personalized_posts(
    *, user_id: str, engine: Engine, settings: PersonalizedFeedSettings
) -> RankingResult
```

`RankingResult` should include ranked post IDs as strings, scores, and a status such as `ranked`, `cold_start`, or `error`. Operational errors should be logged with experiment/user context and should not be represented as a cold start.

### 2. Treat every identifier as opaque

Normalize user, post, round, author, and topic IDs with `str(value)` at boundaries. Do not convert them to integers. ORM queries accept the actual post ID strings used by the HPC database; Standard SQLite comparisons can be handled by a small schema adapter or by retaining native values alongside their string keys.

Parameterize ID lists using SQLAlchemy expanding bind parameters, or avoid raw SQL and use SQLAlchemy expressions. Never construct an `IN` clause by joining identifiers.

### 3. Resolve simulation chronology explicitly

Load post metadata by joining `post.round = rounds.id`. Represent chronology as `(day, hour)` plus a stable tie-breaker. If historical opinions reference round IDs, join those IDs to `rounds` before comparing them. Baseline opinions with sentinel `tid = '0'` should be handled separately and must not be interpreted as a real round primary key.

If the experiment has only baseline author opinions, use those. If no author opinion exists, apply the documented neutral weight. Make this provenance visible in diagnostic output so tests can distinguish matched, baseline, and neutral scores.

### 4. Make ranking deterministic

For `filter_bubble_sort = score`, use:

```text
personalization score DESC,
round day DESC,
round hour DESC,
post ID ASC (stable final tie-breaker)
```

Define and implement the other advertised sort modes or remove them from the UI until supported. Unscored posts should follow scored posts in reverse simulation chronology, not UUID order.

Pagination must be applied only after the complete deterministic order is established. The initial feed and API feed must call the same service.

### 5. Replace silent fallback with an observable policy

A genuine cold start may fall back to reverse chronology, but it should produce a structured reason and a log/metric such as:

```text
personalized_feed_fallback_total{reason="no_preferences"}
```

Ranking failures should log an exception and return a controlled error in tests. In production, a fallback may preserve availability, but it must be observable and must use a distinct reason such as `ranking_error`. The API can include a debug-only `ranking_mode` field, or the response may emit a diagnostic header in non-production/test mode.

### 6. Validate profile input against the catalog

On profile POST:

1. load the allowed catalog for the experiment and profile type;
2. normalize the submitted name to the canonical mode;
3. reject an unknown or disallowed mode instead of persisting it;
4. commit and redirect to a canonical URL;
5. optionally include the saved canonical mode in JSON responses.

Fix catalog filtering so `HumanOnly` entries are available only to human, non-page profiles, including in HPC experiments.

### 7. Wire adaptive configuration consistently

Pass `exp_id` to the interaction hook, load `filter_bubble_lr`, normalize the current mode using the same normalizer as feed ranking, and cover like/dislike/share/comment paths consistently. Do not leave an imported settings loader unused while hard-coding its value.

## Automated verification plan

### A. Pure unit tests

Add tests for:

1. every accepted alias normalizing to `FilterBubble`;
2. score calculation with integer IDs;
3. score calculation with UUID IDs;
4. parameterized post-ID loading;
5. baseline and historical author-opinion selection;
6. deterministic ties;
7. cold-start result versus operational-error result;
8. all advertised sort modes, or rejection of unsupported modes;
9. adaptive interest updates using the configured learning rate.

These tests should fail if any `int(post_id)`, `int(round_id)`, identifier interpolation, or ID-based chronology is reintroduced.

### B. Linked-experiment regression test on a disposable copy

Never mutate the user's live experiment database. Copy both `y_web/db/dashboard.db` and the experiment database into `tmp_path`, point the test application at those copies, and keep the whole test isolated.

Using the copied experiment `1`, user `8`, assert:

```python
assert user.recsys_type == "FilterBubble"
assert preferences[CLIMATE_TOPIC].interest == 1.0
assert preferences[FIFA_TOPIC].interest == 0.0

result = rank_personalized_posts(user_id="8", ...)
assert result.status == "ranked"
assert result.post_ids[:3] == [
    "539388cf-44a7-47ec-829a-2eb761d5ee17",
    "7973189c-1592-4fe3-8777-1bee9eb0aef3",
    "dd1d3eca-7240-4358-807a-b25aebb4b5b2",
]
assert all(CLIMATE_TOPIC in topics(pid) for pid in result.post_ids[:3])
assert result.post_ids[:5] != reverse_chrono_ids[:5]
```

This is the central regression: the current implementation returns an empty score map and fails it.

### C. Opinion-similarity extension of the copied test bed

The linked database lacks opinions for candidate authors, so add controlled rows only to the disposable copy:

1. create or select two non-user authors;
2. give both an otherwise equivalent Climate Change root post at the same simulation time;
3. record author A's Climate Change baseline opinion as `0.9`;
4. record author B's as `0.1`;
5. retain user `8`'s Climate Change opinion `0.9` and interest `1.0`;
6. assert author A's post outranks author B's post;
7. swap user `8`'s copied opinion to `0.1` and assert the order reverses.

This proves that the opinion term, not recency or engagement, controls the order.

### D. Profile-save integration test

With an authenticated Flask test client against the copied databases:

1. POST a different valid content recommender to `/1/update_profile_data/8`;
2. assert the copied `user_mgmt.recsys_type` changed;
3. POST `FilterBubble`;
4. assert the canonical stored value is `FilterBubble`;
5. GET `/1/edit_profile/8` and assert “Personalized Feed” is selected;
6. submit an unknown mode and assert HTTP 400 (or a form validation response) with no database change.

This locks down the persistence path independently of ranking.

### E. Initial-feed and infinite-scroll parity

Authenticate as the experiment user and request both:

```text
GET /1/feed/8/feed/rf/1
GET /1/api/feed/8/feed/rf/1
```

Extract post IDs from each response. Assert that both have the same first-page order and that the three Climate Change IDs lead the ranking. Then request API page 2 and assert there is no overlap with page 1 and that concatenated pages preserve the service's full order.

Also assert that `/1/feed/all/feed/rf/1` is not used as the personalized endpoint.

### F. Failure-observability test

Force a scorer database error. Assert that:

- the result/status is `error`, not `cold_start`;
- the fallback reason is `ranking_error` if production fallback is enabled;
- a structured log or metric is emitted;
- the same condition cannot silently look like a successful Personalized Feed.

### G. Fresh-install and upgrade checks

Create a fresh dashboard database and upgrade an older dashboard database. In both cases assert exactly one catalog row exists with:

```text
FilterBubble | Personalized Feed | Personalization | HumanOnly
```

Verify that a human user sees it, an agent/bot does not, and a stored current selection remains represented in the form.

## Acceptance criteria

The issue is resolved only when all of the following are true:

1. Saving Personalized Feed stores the canonical `FilterBubble` value.
2. Experiment `1`, user `8` produces a non-empty personalized score map.
3. The three Climate Change posts lead the current linked test data under score mode.
4. The result differs from reverse chronology and random ordering in a deterministic assertion.
5. UUID HPC and integer Standard database tests both pass.
6. Initial HTML and infinite-scroll API return the same ranking.
7. Opinion similarity is verified with controlled rows in a disposable copy.
8. Cold start and internal error are distinguishable and observable.
9. `filter_bubble_sort` and `filter_bubble_lr` are either implemented end to end or removed from the configuration UI.
10. No test writes to the live linked experiment database.

## Suggested implementation order

1. Add the failing copied-database regression test and UUID unit fixture.
2. Refactor the scorer to opaque IDs and parameterized queries.
3. Replace ID chronology with joined simulation chronology.
4. Add deterministic ordering and structured outcomes.
5. Make both feed endpoints consume the same ranking service.
6. Validate profile POST values and correct HumanOnly filtering.
7. Wire learning-rate/sort configuration or remove unsupported controls.
8. Add endpoint, opinion, migration, and observability tests.
9. Run the complete recommender and social-route test suites.

## Files implicated

- `y_web/routes/social/common.py`: edit-profile options and persistence; topic/opinion persistence
- `y_web/templates/microblogging/edit_profile.html`: canonical option value and selection
- `y_web/routes/social/microblogging.py`: HTML/API feed dispatch and fallback inputs
- `y_web/src/recsys/content_recsys.py`: normalization, scoring, ordering, pagination, and adaptive updates
- `y_web/routes/interactions/common.py`: adaptive interest updates and configuration propagation
- `y_web/routes/admin/sub/experiments/_frontend_settings.py`: catalog filtering and Personalized Feed settings
- `y_web/routes/social/helpers.py`: runtime settings loading
- `y_web/migrations/add_filter_bubble_recsys.py` and Alembic revision `0003`: catalog upgrade path
- `data_schema/postgre_dashboard.sql` and the SQLite seed: fresh-install catalog state
- recommender/social route tests: currently missing Personalized Feed coverage

## Final diagnosis

The selected recommender does reach the feed and is saved correctly. The apparent failure to update is caused by the ranking implementation collapsing on HPC UUID identifiers and intentionally hiding that collapse behind a reverse-chronological fallback. Fixing only the edit-profile form or forcing another reload will not solve it. The scorer's identifier, chronology, error, and deterministic-order contracts must be corrected and protected by the linked-experiment regression described above.
