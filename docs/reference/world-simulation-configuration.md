# World Simulation: configuration reference

The advanced parameters of a World Simulation are a JSON object with five optional blocks. Unknown blocks are
refused when the World Simulation is created or saved; unknown keys inside a block are refused when the coordinator
starts. Values shown are the defaults.

## `attention`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | share each agent's daily attention among its platforms |
| `temperature` | `1.0` | softmax temperature (> 0): higher spreads the attention more evenly |
| `inertia` | `0.3` | weight of the previous day (0 to 1) |
| `min_multiplier`, `max_multiplier` | `0.1`, `3.0` | bounds of the session multiplier each client applies |
| `normalization` | `"raw"` | `raw`: stress and reward as each platform reports them; `zscore`: standardised per platform and day |

## `crosspost`

| Key | Default | Meaning |
|---|---|---|
| `mode` | `"coordinator_rule"` | `coordinator_rule` or `agent_action` |
| `probability` | `{}` | `{"<source>-><target>": p}` with member names or platform types, each p in [0, 1]; a pair that is not listed has probability 0; used by `coordinator_rule` only |
| `propensity` | not set | how often an agent tries to cross-post (client side); written into the `federation` section of the members |

## `topics`

| Key | Default | Meaning |
|---|---|---|
| `migration` | `true` | content that crosses platforms brings its topics and a topic missing on the destination is created; `false` switches it off where a runtime has a switch (forum `topic_migration`, YSimulator `create_topics`). Only the opt-out is stored. |

## `discovery`

`enabled` (`false`), `decision` (`"logit"` or `"threshold"`), `decay` (0.1), `w_view` (1.0), `w_view_tie` (2.0),
`w_interact` (3.0), `window_days` (7), `aware_threshold` (3.0), `base_rate` (0.0), `max_active_platforms` (5),
`rejoin_cooldown_days` (14), `social_cap` (5), `threshold_probability` (0.5) and `beta`, the weights of the logit with the
keys `0`, `A`, `S`, `I`, `N`, `F` (defaults -3.0, 1.0, 0.5, 1.5, 0.5, 0.5).

## `leave`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | agents may leave a platform |
| `weight_threshold` | `0.1` | attention weight below which a platform counts as unused |
| `consecutive_days` | `3` | days in a row below the threshold before leaving; at least one platform always stays |

## `membership`

`initial`: which accounts are active at the start: `"all"` (default, every eligible agent on every platform), `"one_random"` (each agent on one randomly chosen platform, from the seed) or a map `{"<member>": p}` with the probability of starting on each member.

## The `federation` section of a member

YSocial writes it into the server and client configuration of every member when the World Simulation starts and removes
it when it stops. Without it, or with `enabled: false`, a runtime does not change.

| Key | Meaning |
|---|---|
| `enabled`, `member`, `federation_id`, `exp_id` | identity of the member |
| `coordinator_file`, `token_file`, `protocol` | where to find the coordinator, its token and the protocol version (`1.0`) |
| `exposures` | send what each agent was shown, for discovery |
| `crosspost_mode` | `coordinator_rule` or `agent_action` |
| `crosspost_propensity`, `seed` | written only when `crosspost.propensity` is set |
| `topic_migration` | forum member only: `topics.migration` (default true) |
| `create_topics` | microblogging member on HPC (YSimulator) only: `topics.migration` (default true) |
