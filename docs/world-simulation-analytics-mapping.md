# World Simulation analytics: derived tables

Generated from `y_web/src/federation/analytics_etl.py` (`render_field_map`); a test keeps this file equal to it. The
derived database `analytics_federation.db` is rebuilt from `federation.db` (opened read-only) in the folder of the
World Simulation; days are canonical days (`tick // 24`), numbered from 0.

### `daily_attention`

Attention of the agents on each platform, one row per day and member. Source: federation_attention.

| Column | Type | Meaning |
|---|---|---|
| `day` | INTEGER | canonical day, from 0 |
| `member` | TEXT | platform member |
| `agents` | INTEGER | agents with a weight on this member that day |
| `weight` | REAL | sum of the weights of those agents |
| `share` | REAL | weight / total weight of the day over all members (0 when nobody has attention) |

### `migration_flows`

Agents that became active on a member, by the member they had most recently left (or '(new)'). Source: federation_event (membership_change).

| Column | Type | Meaning |
|---|---|---|
| `day` | INTEGER | day of the join |
| `from_member` | TEXT | member left most recently by the agent, '(new)' when none |
| `to_member` | TEXT | member joined |
| `n` | INTEGER | agents |

### `crosspost_flows`

Cross-posts delivered between platforms, one row per day, origin and destination. Source: federation_message (crosspost.v1).

| Column | Type | Meaning |
|---|---|---|
| `day` | INTEGER | day the cross-post was emitted |
| `source` | TEXT | member where the content was posted (from its source_ref) |
| `target` | TEXT | member the cross-post was addressed to |
| `n` | INTEGER | cross-posts |

### `cascades`

How far each cross-posted content went: one row per original content. Source: federation_message (crosspost.v1).

| Column | Type | Meaning |
|---|---|---|
| `source_ref` | TEXT | ysocial:// reference of the original content |
| `origin` | TEXT | member of the original content |
| `day` | INTEGER | day of the first cross-post |
| `size` | INTEGER | cross-posts of this content |
| `targets` | INTEGER | distinct platforms reached |

### `survival`

Agents still present on each platform at the end of each day, and those who left that day. Source: federation_affective, federation_event (membership_change).

| Column | Type | Meaning |
|---|---|---|
| `day` | INTEGER | canonical day |
| `member` | TEXT | platform member |
| `active` | INTEGER | agents with an affective report for the day (active at its end) |
| `left` | INTEGER | agents whose membership ended that day |
| `survival` | REAL | active / active on the first day with data for the member |

