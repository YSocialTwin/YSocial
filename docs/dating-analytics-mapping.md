# Dating analytics: derived tables and their sources

Generated from `y_web/src/dating/analytics_etl.py` (`FIELD_MAP`); do not edit by hand.
`analytics_dating.db` is rebuilt in full from `database_server.db` (opened read-only) and replaced atomically.

## `rounds`

One row per round, numbered from 1.

Source: rounds

| Column | Type | Meaning |
| --- | --- | --- |
| `ordinal` | INTEGER | 1-based global round: (day - 1) * slots + hour |
| `day` | INTEGER | simulated day, from 1 |
| `hour` | INTEGER | slot of the day, from 1 |

## `agents`

One row per account with its public attributes, outcome and latent variables (admin only).

Source: user_mgmt, dating_profile, dating_latent

| Column | Type | Meaning |
| --- | --- | --- |
| `user_id` | TEXT | user_mgmt.id |
| `username` | TEXT | user_mgmt.username |
| `age` | INTEGER | user_mgmt.age |
| `gender` | TEXT | user_mgmt.gender |
| `city` | TEXT | dating_profile.city |
| `intent` | TEXT | dating_profile.intent |
| `status` | TEXT | user_mgmt.status (active, paused, left) |
| `left_reason` | TEXT | user_mgmt.left_reason (paired = success, churn = frustration, manual) |
| `joined_ordinal` | INTEGER | round of joining, as an ordinal |
| `left_ordinal` | INTEGER | round of leaving, as an ordinal (NULL while present) |
| `match_recsys` | TEXT | recommender of this agent (empty: experiment default) |
| `attractiveness` | REAL | dating_latent.attractiveness |
| `selectivity` | REAL | dating_latent.selectivity |
| `responsiveness` | REAL | dating_latent.responsiveness |
| `desirability_rating` | REAL | dating_latent.desirability_rating (Elo-style, at the end of the run) |

## `agent_stats`

Activity and outcomes of each account over the whole run.

Source: match_recommendations, swipes, matches, messages, blocks, reports

| Column | Type | Meaning |
| --- | --- | --- |
| `user_id` | TEXT | agents.user_id |
| `cards_seen` | INTEGER | recommendations served to the account |
| `times_shown` | INTEGER | recommendations in which the account was the candidate |
| `likes_given` | INTEGER | swipes LIKE or SUPERLIKE by the account (not undone) |
| `passes_given` | INTEGER | swipes PASS by the account (not undone) |
| `likes_received` | INTEGER | LIKE or SUPERLIKE swipes on the account (not undone) |
| `passes_received` | INTEGER | PASS swipes on the account (not undone) |
| `matches` | INTEGER | matches the account is part of |
| `messages_sent` | INTEGER | messages sent by the account |
| `messages_received` | INTEGER | messages sent to the account |
| `blocks_received` | INTEGER | blocks against the account |
| `reports_received` | INTEGER | reports against the account |

## `daily`

Run totals per simulated day.

Source: match_recommendations, swipes, matches, messages, blocks, reports, date_proposals, user_mgmt

| Column | Type | Meaning |
| --- | --- | --- |
| `day` | INTEGER | simulated day |
| `stacks` | INTEGER | (viewer, round) pairs that were served recommendations |
| `cards_shown` | INTEGER | recommendations served |
| `swipes` | INTEGER | swipes not undone |
| `likes` | INTEGER | LIKE or SUPERLIKE swipes |
| `matches` | INTEGER | matches created |
| `messages` | INTEGER | messages sent |
| `active_agents` | INTEGER | accounts that swiped or wrote |
| `blocks` | INTEGER | blocks |
| `reports` | INTEGER | reports |
| `date_proposals` | INTEGER | date proposals made |
| `exits` | INTEGER | accounts that left |

## `recommender_stats`

Exposure and outcome measures per recommender model (day NULL: whole run).

Source: match_recommendations, swipes, matches, messages

| Column | Type | Meaning |
| --- | --- | --- |
| `model` | TEXT | match_recommendations.model |
| `day` | INTEGER | simulated day; NULL for the whole run |
| `stacks` | INTEGER | (viewer, round) pairs served |
| `cards_shown` | INTEGER | recommendations served |
| `swipes` | INTEGER | swipes not undone on those recommendations |
| `like_rate` | REAL | likes per swipe |
| `gini_exposure` | REAL | Gini coefficient of the exposures over the profiles shown |
| `gini_likes_received` | REAL | Gini coefficient of the likes received over all accounts |
| `matches` | INTEGER | matches whose pair was served by the model |
| `match_rate_per_stack` | REAL | matches per stack served |
| `matches_with_message_share` | REAL | share of those matches with at least one message |

## `match_stats`

One row per match.

Source: matches, messages, date_proposals, match_recommendations

| Column | Type | Meaning |
| --- | --- | --- |
| `match_id` | TEXT | matches.id |
| `user_a` | TEXT | matches.user_a |
| `user_b` | TEXT | matches.user_b |
| `created_ordinal` | INTEGER | round of the match, as an ordinal |
| `status` | TEXT | matches.status |
| `ended_ordinal` | INTEGER | round the match ended (NULL while active) |
| `first_message_by` | TEXT | matches.first_message_by |
| `messages` | INTEGER | messages in the match |
| `deleted_messages` | INTEGER | messages deleted by their sender |
| `date_proposals` | INTEGER | date proposals in the match |
| `model` | TEXT | recommender that served the pair |

## `funnel`

Date proposals by status and by outcome.

Source: date_proposals

| Column | Type | Meaning |
| --- | --- | --- |
| `kind` | TEXT | status or outcome |
| `key` | TEXT | value of date_proposals.status or date_proposals.outcome |
| `n` | INTEGER | number of proposals |

## `exits`

Departures per day and cause (paired and churn are kept apart: success is not abandonment).

Source: user_mgmt

| Column | Type | Meaning |
| --- | --- | --- |
| `day` | INTEGER | simulated day of leaving |
| `reason` | TEXT | user_mgmt.left_reason |
| `n` | INTEGER | accounts |

## `summary`

Single-number measures of the run, the same as the runtime's lifecycle report.

Source: user_mgmt, matches, messages, date_proposals, profile_events

| Column | Type | Meaning |
| --- | --- | --- |
| `key` | TEXT | measure name |
| `value` | REAL | value |

## `etl_state`

What the build was made from; carries no clock, so equal sources give equal databases.

Source: (derived)

| Column | Type | Meaning |
| --- | --- | --- |
| `schema_version` | INTEGER | version of this layout |
| `source_signature` | TEXT | size and time of the source database and its write-ahead log |
| `last_round` | INTEGER | ordinal of the newest round |
| `day` | INTEGER | day of the newest round |
| `hour` | INTEGER | slot of the newest round |
