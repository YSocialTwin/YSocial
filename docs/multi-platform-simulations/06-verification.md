# Verification

## Validation Strategy

The verification strategy should prove both correctness and non-regression.

## Configuration Validation

Verify that:

- the new flag defaults to disabled
- malformed sibling definitions are rejected
- homogeneous and heterogeneous sibling sets both parse correctly
- solo experiments still behave as before

## Unit Tests

Add tests for:

- sibling registry parsing
- provenance envelope creation
- attention allocation and rebalancing
- join decision thresholds
- churn decision thresholds
- dormant membership handling

## Integration Tests

Run scenarios such as:

- microblogging to microblogging sharing
- microblogging to forum discovery via contacts
- forum to photo sharing and join
- churn after stress escalation
- migration after moderation or ban events

## Regression Tests

Confirm that these still work when multi-platform is disabled:

- create experiment
- start server
- create client
- run a solo microblogging simulation
- run a solo forum simulation
- run a solo photo sharing simulation
- open existing admin pages

## UI Verification

Manually verify that:

- the new section is hidden or harmless when off
- sibling editing appears only when enabled
- solo forms remain unchanged
- current dashboards do not regress

## Behavioral Verification

Use controlled experiments to check that:

- attention shifts away from low-reward or high-stress platforms
- agents can discover a platform through contacts
- agents can join and later churn without losing historical identity
- cross-platform content keeps provenance intact

## Acceptance Criteria

The feature can be considered sound when:

- multi-platform mode is off by default
- solo simulations remain available and unchanged
- sibling instances are explicitly configured by the admin
- homogeneous and heterogeneous sibling sets are supported
- agents can cross-post, discover, join, allocate attention, and churn
- migration and deplatforming can be studied without forcing every agent onto every platform

