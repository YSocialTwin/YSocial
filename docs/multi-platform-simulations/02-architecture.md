# Architecture

## Design Principle

Multi-platform simulation should be implemented as a coordination layer above the existing platform runtimes, not as a rewrite of them.

That means:

- each platform instance remains native
- the admin explicitly defines sibling instances
- the agent runtime maintains a portfolio of joined platforms
- cross-platform discovery and sharing use an interoperability layer

## Server Side

The server remains the authoritative layer for:

- state persistence
- content creation
- provenance recording
- sibling instance resolution
- platform-specific runtime orchestration

The server must add:

### 1. Multi-platform orchestration

The orchestration layer must know:

- whether multi-platform mode is enabled
- which siblings belong to the experiment
- which siblings are discoverable
- which siblings are homogeneous or heterogeneous

### 2. Sibling registry lookups

The runtime must be able to resolve:

- what sibling platforms are available
- what their types are
- whether discovery is allowed
- whether cross-posting is allowed
- how a sibling instance is addressed

### 3. Provenance normalization

Every cross-platform content event must carry canonical provenance metadata so downstream analysis can reconstruct:

- origin platform
- origin experiment
- destination platform
- destination experiment
- transformation type

### 4. Solo-path preservation

When multi-platform mode is disabled, the server must behave exactly as it does today.

No new mandatory tables, links, or startup requirements should be introduced for solo runs.

## Client Side

The client is where the behavior changes happen.

The client must support:

- platform portfolio state
- join and churn decisions
- attention allocation across joined platforms
- cross-platform content selection
- dormant memberships that can later be reactivated

The client must keep these layers separate:

- persona state
- platform-local state
- content provenance state

## Frontend

The admin UI should not be overloaded inside the existing solo workflow.

Instead, the multi-platform controls should live in a dedicated admin section placed alongside the current `admin/experiments` route.

The UI should expose:

- sibling instance configuration
- discoverability controls
- membership and attention summaries
- provenance-aware monitoring

## Behavioral Model

The expected agent loop is:

1. discover a sibling platform through contacts' shared content
2. decide whether to join
3. copy profile state into the new platform
4. allocate attention across joined platforms
5. cross-post or cross-share when useful
6. churn from a platform when stress outweighs reward
7. optionally reactivate a dormant platform later

## Transfer Direction

From an implementation perspective, the default and most natural path is to **push** content from the current platform to another platform.

Why push first:

- the agent already has the content and context locally
- provenance can be attached at creation time
- the destination receives a clearly authored inbound event
- there is no need to scan or materialize remote content before acting

The opposite direction, **pulling** content from another platform into the current one, can also make sense, but it is best treated as a secondary capability.

Pulling is useful when the simulation wants to model:

- explicit import from a sibling platform feed
- search or retrieval across sibling platforms
- content resurfacing from a remote platform into the current one

However, pull is less natural as a first implementation because it introduces a read path into a remote sibling's content surface and requires stricter filtering and provenance rules.

### Recommendation

- implement push-based `cross_post` and `cross_share` first
- keep pull-based import as an optional future extension
- expose both only if the admin explicitly enables the relevant sibling visibility

## Visibility Requirements

Both push and pull require the sibling platform to be visible, but not in the same way.

### Push visibility

For a push from platform A to platform B:

- platform B must be declared as a discoverable sibling of A
- platform B must allow inbound content from A
- platform A must be allowed to export content to B
- the source content must be marked as shareable across the sibling graph

This is the natural case for cross-post and cross-share.

### Pull visibility

For a pull from platform B into platform A:

- platform A must be allowed to read from platform B
- platform B must expose the target content to the sibling graph
- the source content must be discoverable by A through an explicit sibling-visible feed, not through a global query
- the operator should be able to restrict pull visibility to avoid accidental data leakage across unrelated experiments

Pull should therefore require stricter visibility than push because it exposes a remote content surface to a local retriever.

### Practical rule

The admin should think in terms of two permissions:

- `can_export_to_sibling`
- `can_be_imported_from_sibling`

Push requires the first one.
Pull requires the second one.

The default implementation should keep pull disabled unless the operator explicitly wants a sibling-import behavior.

## Platform Neutrality

The bridge layer should not force all content into one universal schema.

Instead:

- microblogging and forum continue to use post-based content
- photo sharing continues to use photo-native content
- cross-platform transport uses a neutral provenance envelope
