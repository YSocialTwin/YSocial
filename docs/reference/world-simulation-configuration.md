# World Simulation: configuration reference

The parameters of a World Simulation are set in the form sections of the New and Configuration pages and stored as a JSON object with five optional blocks (shown read-only by *Show the generated file*). Unknown blocks are
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
| `content` | `["all"]` (not stored) | which agent content may be cross-posted, in both modes. `["all"]`: all content, the agent's own and that of other agents (shares, replies, forwards). Otherwise a non-empty list of additive options `own_content` (the agent's original content of any kind; `own_posts` is the legacy alias), `news` (any content with a link: the article of the content or an `http(s)://` address in the text), `images` (any content with an image). Eligible = at least one selected option (OR); selecting more never reduces what is eligible; `all` cannot be mixed with the others. Lists of two or more entries from the first, AND, version now mean OR. Content that is eligible for none is dropped by the coordinator with a `crosspost_filtered` event (`not_eligible`); people are never filtered. Read at every start; also written as `crosspost_content` in the `federation` section of the members when it is not `all`. Set in the form (*Agent content that can be cross-posted*). |

## `topics`

| Key | Default | Meaning |
|---|---|---|
| `migration` | `true` | content that crosses platforms brings its topics and a topic missing on the destination is created; `false` switches it off where a runtime has a switch (forum `topic_migration`, YSimulator `create_topics`). Only the opt-out is stored. |

## `discovery`

`enabled` (`false`), `decision` (`"logit"` or `"threshold"`), `decay` (0.1), `w_view` (1.0), `w_view_tie` (2.0),
`w_interact` (3.0), `window_days` (7), `aware_threshold` (3.0), `base_rate` (0.0), `max_active_platforms` (5),
`rejoin_cooldown_days` (14), `social_cap` (5), `threshold_probability` (0.5) and `beta`, the weights of the logit with the
keys `0`, `A`, `S`, `I`, `N`, `F` (defaults -3.0, 1.0, 0.5, 1.5, 0.5, 0.5).

`quoted_weight` (0.0, between 0 and 1): when above 0, an exposure to a cross-post that quotes content from a third platform also adds awareness of that platform, at `quoted_weight` times the usual weight; 0 switches it off. It is a field of the Discovery section (`discovery.quoted_weight`).

## `provisioning`

Read by YSocial only (it is not written to `federation.json`): `{"members": ["microblogging"]}` lets the agents of the other members **discover** those platforms
and get an account there on the fly (needs `discovery.enabled`). Honoured only for runtimes that create accounts on request and whose client
adopts them (today microblogging on the Standard backend: YServer + YClient); asking for another member has no effect. The member entry in
`federation.json` then carries `provision: true`, and the `federation` section of that member `provision` and `adopt`. See `flexible-populations.md` in the YFederation docs.

## `pseudonyms`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | the authors named in a quoted cross-post reach the receiving platforms as `participant-<8 hex>`, stable during the simulation and different in another one; the stored data are unchanged. The seed of the simulation is the secret that derives them. |

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
| `topic_migration` | forum member, and microblogging member (YServer): written as `false` only when the admin opted out of `topics.migration`; absent means the runtime default (on) |
| `create_topics` | microblogging member on HPC (YSimulator) only: `topics.migration` (default true) |
| `bindings_file` | file where the runtime keeps who is who: it reports its accounts by username and the coordinator answers with the global id of the agent it expected under that name (`bindings_<member>.db` in the folder of the World Simulation) |
| `provision`, `adopt` | only with `provisioning.members`: the server creates the accounts the coordinator asks for and the client gives each an agent |

### People enrolled (`accounts`)

When people are enrolled, the `federation` section of a member also carries `accounts`: `{"human:<user id>": "<local account id>"}`
for the active people of that member. The runtimes use it to give a person their `human:` identity (never the local id, which could
be an agent's) and to keep people out of the agent rules. The microblogging gateway reads its token from `human_gateway.token` in the
server configuration; the forum and photo-sharing gateways are processes that YWeb starts with a per-run token in
`human_gateway.token` and an address in `human_gateway.json` of the experiment folder.
