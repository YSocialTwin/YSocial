# Persistence and Actions

## What Must Be Persisted

Cross-platform simulation needs three persistence layers:

1. native content rows on each platform
2. canonical provenance records
3. platform membership and action history

## Native Content Tables To Update

| Platform | Tables to update | Notes |
|---|---|---|
| Microblogging | `post` | keep `shared_from`; add cross-platform provenance fields |
| Forum | `post` | keep `shared_from`; add cross-platform provenance fields |
| Photo sharing | the native photo table(s) in the photo engine, plus `image_posts` where it is used as shared image support | add the same provenance fields used by `post` |

### Required provenance on native content rows

Every cross-platform-capable content row should include:

- `content_provenance_id`
- `origin_platform_type`
- `origin_experiment_id`
- `origin_content_table`
- `origin_content_id`
- `origin_user_id`
- `share_kind`
- `is_cross_platform`
- `source_client_action_id`
- `source_round`

The existing `post.shared_from` field is still useful for same-platform shares, but it is insufficient for cross-platform provenance because it does not identify the source platform or experiment.

## Canonical Shared Tables

These tables should exist in every simulation database:

### `content_provenance`

Purpose: canonical audit trail for every share, repost, cross-post, or quote.

Recommended columns:

- `id`
- `origin_platform_type`
- `origin_experiment_id`
- `origin_content_table`
- `origin_content_id`
- `origin_user_id`
- `destination_platform_type`
- `destination_experiment_id`
- `destination_content_table`
- `destination_content_id`
- `share_kind`
- `transfer_direction`
- `visibility_scope`
- `parent_provenance_id`
- `created_at`
- `meta_json`

### `platform_memberships`

Purpose: track current and historical membership state for each persona on each platform.

Recommended columns:

- `id`
- `persona_uuid`
- `local_user_id`
- `experiment_id`
- `platform_type`
- `membership_state`
- `attention_weight`
- `joined_round`
- `left_round`
- `join_reason`
- `churn_reason`
- `copied_from_persona_uuid`
- `copied_from_experiment_id`
- `last_reward`
- `last_stress`

### `platform_action_events`

Purpose: normalized event log for discovery, join, churn, share, and cross-share decisions.

Recommended columns:

- `id`
- `persona_uuid`
- `local_user_id`
- `experiment_id`
- `platform_type`
- `action_type`
- `source_provenance_id`
- `target_provenance_id`
- `round_id`
- `payload_json`
- `created_at`

## Shared Columns Required Across Engines

These columns should be present everywhere to avoid platform-specific dead ends:

| Table | Column | Why |
|---|---|---|
| `user_mgmt` | `persona_uuid` | stable identity across sibling instances |
| `post` / photo-native content tables / `image_posts` | `content_provenance_id` | fast provenance lookup |
| `post` / photo-native content tables / `image_posts` | `origin_platform_type`, `origin_experiment_id`, `origin_content_id` | analytics and rendering without extra joins |
| `stress_reward` | `platform_type` or `platform_instance_key` | stress/reward must be attributable to a specific platform |
| `stress_reward` | `content_provenance_id` | trace stress/reward back to the content that caused it |
| `agent_opinion` | `platform_type` or `platform_instance_key` | optional but strongly recommended for platform-specific opinions |
| `reactions` and `follow` | `persona_uuid` | useful for cross-engine analysis of the same simulated person |

The most important addition is `persona_uuid` on `user_mgmt`.
Without it, profile copying becomes ambiguous across sibling platforms.

## New Agent Actions

The runtime should support:

| Action | Meaning | Persistence effect |
|---|---|---|
| `discover_platform` | notice a sibling platform through contacts' shared content | write `platform_action_events` |
| `join_platform` | join a discovered sibling platform and copy the profile there | create or activate `platform_memberships` |
| `update_attention` | change attention allocation for a joined platform | update `platform_memberships.attention_weight` |
| `cross_post` | republish content natively on another platform | create new native content plus `content_provenance` |
| `cross_share` | forward, quote, or share remote content | create new native content plus `content_provenance` |
| `churn_platform` | set a platform's attention to zero and leave it dormant | update membership state and `left_round` |
| `reactivate_platform` | restore attention after a dormant period | update membership state and `attention_weight` |

`cross_post` and `cross_share` are naturally modeled as push actions.
If a future pull/import action is added, it should be recorded as a distinct action type rather than overloading `cross_share`.

## Why These Tables Matter

These tables and columns make the core dynamics possible without creating issues:

- profile copying keeps identity stable
- dormant memberships remain visible after churn
- provenance stays attached to content and not only to the latest platform row
- cross-platform analytics can work without schema-specific hacks
- homogeneous and heterogeneous siblings can be treated uniformly
- push and pull semantics can be distinguished in provenance records
