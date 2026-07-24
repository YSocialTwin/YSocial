# Implementation Plan

## Phase 1: Configuration And Discovery Scaffolding

Technical choices:

- use an opt-in flag, default false
- place the multi-platform workflow in a separate admin section alongside `admin/experiments`
- store sibling references explicitly
- keep the current `platform_type` model unchanged for solo simulations

What to change:

- new multi-platform admin entry point
- multi-platform experiment creation and details views
- configuration persistence for sibling definitions
- validation for sibling references

Risk:

- low to medium

Success criteria:

- multi-platform config can be created and read
- solo experiments still save and load without new required fields
- invalid sibling definitions fail early

Feasibility:

- high

## Phase 2: Runtime Registry And Content Provenance

Technical choices:

- add a small orchestration layer
- preserve each platform's native runtime and database
- use a platform-neutral content provenance envelope

What to change:

- sibling instance resolution
- content serialization/deserialization
- provenance persistence
- platform adapters for native content creation

Risk:

- medium

Success criteria:

- content shared across platforms keeps traceable origin
- native platform views still work
- no platform is forced into another's schema

Feasibility:

- medium to high

## Phase 3: Agent Portfolio, Join, And Churn

Technical choices:

- model the agent as a stable persona with a platform portfolio
- separate global persona state from platform-local state
- treat join and churn as state transitions, not deletes

What to change:

- client-side decision logic
- attention allocator
- membership state
- stress/reward aggregation

Risk:

- medium to high

Success criteria:

- agents can join and churn without losing history
- attention shifts across joined platforms
- solo behavior remains unchanged when the feature is off

Feasibility:

- medium

## Phase 4: Discovery, Social Contagion, And Migration Dynamics

Technical choices:

- discover platforms through observed shared content
- use exposure, salience, stress, and reward as signals
- keep join thresholds configurable

What to change:

- discovery heuristics
- cross-platform exposure tracking
- stress and reward signals
- logging and metrics for join/churn reasons

Risk:

- medium

Success criteria:

- discovery is social and local
- migration can respond to bans, moderation, or harassment
- churn is measurable and explainable

Feasibility:

- medium

## Phase 5: Frontend Exposure And Verification

Technical choices:

- keep the solo pages unchanged
- expose multi-platform in the dedicated admin section
- surface provenance in monitoring views

What to change:

- dedicated admin landing page
- dedicated creation and details pages
- dedicated client pages
- monitoring dashboards and logs

Risk:

- low to medium

Success criteria:

- the admin can manage sibling graphs in the dedicated section
- solo layouts still behave as before
- provenance and attention are visible

Feasibility:

- high

## Phase 6: Controlled Rollout And Regression Hardening

Technical choices:

- keep the feature behind the default-off flag
- add targeted tests for each transition point
- compare solo and multi-platform runs under the same populations

What to change:

- tests
- scenario fixtures
- comparison tooling
- operator docs

Risk:

- low to medium

Success criteria:

- regressions are detected early
- disabling the feature restores the original behavior contract
- the system can be rolled out safely

Feasibility:

- high

