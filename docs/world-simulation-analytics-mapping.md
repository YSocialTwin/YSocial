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

### `shares`

Cross-posts that share the content of another agent (crosspost.v1 with `quoted`), one row per share and destination. Source: federation_message (crosspost.v1, quoted).

| Column | Type | Meaning |
|---|---|---|
| `day` | INTEGER | day the share was emitted |
| `tick` | INTEGER | tick the share was emitted |
| `sharer` | TEXT | global_agent_id of the agent that shares |
| `origin_member` | TEXT | platform where the sharer saw the content (quoted.member) |
| `destination` | TEXT | member the share was addressed to |
| `original_author` | TEXT | name of the author of the shared content |
| `original_author_id` | TEXT | global_agent_id of that author, '' when it is not a federation identity |
| `quoted_ref` | TEXT | reference of the shared content ('' for an author outside the federation) |
| `depth` | INTEGER | 1 for a share of local content, +1 for each earlier cross-post the content went through |

### `share_depth`

How many shares sit at each depth of a chain. Source: federation_message (crosspost.v1, quoted).

| Column | Type | Meaning |
|---|---|---|
| `depth` | INTEGER | depth in the chain (see shares.depth) |
| `shares` | INTEGER | shares at that depth |

### `bridge_agents`

Agents whose shares carry content from one platform to another, most active first. Source: federation_message (crosspost.v1, quoted).

| Column | Type | Meaning |
|---|---|---|
| `agent` | TEXT | global_agent_id of the sharer |
| `shares` | INTEGER | shares sent |
| `origins` | INTEGER | distinct platforms the shared content came from |
| `destinations` | INTEGER | distinct platforms the shares reached |

### `topics_carried`

Topics that travelled with cross-posted content, by platform pair. Coordinator data only: whether the destination had to create the topic is in the member databases (federation_topic), which this analysis does not open. Source: federation_message (crosspost.v1, topics).

| Column | Type | Meaning |
|---|---|---|
| `topic` | TEXT | topic name as sent |
| `source` | TEXT | member where the content was posted (from its source_ref) |
| `target` | TEXT | member the content was addressed to |
| `n` | INTEGER | cross-posts carrying the topic |
| `first_day` | INTEGER | day of the first one |

### `human_crossposts`

Cross-posts sent by people (identity `human:<id>`), one row per day, platform pair and kind. The identities of the agents never start with `human:` (INV-14), so this is exactly what the people did. Source: federation_message (crosspost.v1 whose global_agent_id starts with human:).

| Column | Type | Meaning |
|---|---|---|
| `day` | INTEGER | day the cross-post was emitted |
| `human` | TEXT | global_agent_id of the person (human:<id>) |
| `source` | TEXT | member the person posted on (source_member of the message) |
| `target` | TEXT | member the cross-post was addressed to |
| `shares` | INTEGER | of them, shares of another agent's content (with `quoted`) |
| `n` | INTEGER | cross-posts |

### `human_activity`

What each person did across the platforms, most active first. Source: federation_message (crosspost.v1 whose global_agent_id starts with human:).

| Column | Type | Meaning |
|---|---|---|
| `human` | TEXT | global_agent_id of the person (human:<id>) |
| `crossposts` | INTEGER | cross-posts sent |
| `shares` | INTEGER | of them, shares of another agent's content |
| `origins` | INTEGER | distinct platforms the person posted from |
| `destinations` | INTEGER | distinct platforms the cross-posts reached |
| `first_day` | INTEGER | day of the first cross-post |
| `last_day` | INTEGER | day of the last one |

