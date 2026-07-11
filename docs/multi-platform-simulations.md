# Multi-Platform Simulations

This is the entry point for the multi-platform simulation design package.

The detailed material has been split into focused documents so the feature can be implemented and reviewed in smaller pieces.

## Module Map

| Document | Purpose |
|---|---|
| [Overview](multi-platform-simulations/01-overview.md) | feature framing, terminology, compatibility goals, and non-goals |
| [Architecture](multi-platform-simulations/02-architecture.md) | server/client/frontend changes and runtime coordination model |
| [Persistence and Actions](multi-platform-simulations/03-persistence-and-actions.md) | provenance tables, shared columns, and the new agent action vocabulary |
| [Admin UI](multi-platform-simulations/04-admin-ui.md) | dedicated admin section, workflows, and operator-visible controls |
| [Implementation Plan](multi-platform-simulations/05-implementation-plan.md) | phased rollout with technical choices, risk, feasibility, and success criteria |
| [Verification](multi-platform-simulations/06-verification.md) | test strategy, regression gates, and acceptance criteria |
| [Engine Migration Checklist](multi-platform-simulations/07-engine-migration-checklist.md) | per-engine checklist for microblogging, forum, and photo sharing |

## Recommended Reading Order

1. [Overview](multi-platform-simulations/01-overview.md)
2. [Architecture](multi-platform-simulations/02-architecture.md)
3. [Persistence and Actions](multi-platform-simulations/03-persistence-and-actions.md)
4. [Admin UI](multi-platform-simulations/04-admin-ui.md)
5. [Implementation Plan](multi-platform-simulations/05-implementation-plan.md)
6. [Verification](multi-platform-simulations/06-verification.md)
7. [Engine Migration Checklist](multi-platform-simulations/07-engine-migration-checklist.md)

## How To Use This Package

- Use the overview to align on scope and invariants.
- Use the architecture doc to discuss runtime boundaries.
- Use the persistence doc to decide which tables and columns must change.
- Use the admin UI doc to plan the new operator workflow.
- Use the implementation plan to sequence the work.
- Use the verification doc to define exit criteria.
- Use the engine checklist to turn the design into a task list per simulation engine.

The solo simulation path remains the default and must remain unaffected unless multi-platform mode is explicitly enabled.
