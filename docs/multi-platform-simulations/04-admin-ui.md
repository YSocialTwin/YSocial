# Admin UI

## Layout Decision

To keep the interface simple, the multi-platform controls should live in a dedicated admin section placed alongside the current `admin/experiments` route.

This section should be the primary operator surface for multi-platform simulations.

The existing solo workflow must remain available and unchanged.

## Dedicated Section Responsibilities

The new admin area should support:

- creating multi-platform simulations
- editing sibling instance graphs
- inspecting discoverability and platform type relationships
- reviewing memberships, discovery, churn, and provenance
- launching and monitoring multi-platform runs

## Pages To Expose

### Landing page

The landing page should summarize:

- enabled/disabled state
- number of sibling instances
- platform types involved
- discoverability status
- recent join and churn events

### Experiment creation page

The dedicated creation page should expose:

- a multi-platform toggle, default off
- explicit sibling instance selection
- homogeneous versus heterogeneous sibling labels
- discovery permissions
- cross-post and cross-share permissions

### Experiment details page

The details page should show:

- current sibling graph
- membership and attention state
- provenance-aware activity
- whether the experiment is still safe to run as solo if multi-platform is disabled

### Client creation page

The client page should show:

- whether the client begins on one or many platforms
- whether profile copying is enabled
- whether attention is dynamic
- whether churn is allowed

### Monitoring page

The monitoring surface should show:

- platform-specific attention weights
- join and churn events
- cross-post and cross-share events
- provenance badges on content
- moderation or ban-driven changes

## Operator Workflow

Recommended flow:

1. create or select the multi-platform section
2. define sibling instances
3. configure discoverability
4. create or validate the population
5. create clients
6. verify provenance and action settings
7. run the experiment
8. monitor joins, churns, and cross-platform transfers

## UI Compatibility Rule

The solo `admin/experiments` path must remain untouched in behavior and layout.

The multi-platform section should be additive, not invasive.

