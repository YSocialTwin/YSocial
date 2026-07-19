# Overview

## Purpose

This package describes an opt-in extension to YSocial that allows a single experiment to coordinate multiple social platforms at once.

Current supported environments are:

- microblogging (`flask`/`ray`)
- forum (`flask`)
- photo sharing (`ray`)

The proposal does not replace the current single-platform model. It adds a multi-platform mode that is:

- disabled by default
- backward compatible with existing solo simulations
- explicitly configured by the admin
- suitable for studying migration, deplatforming, platform switching, and attention reallocation

## What Multi-Platform Mode Must Enable

The feature must support:

1. cross-post and cross-share content from one platform to another
2. discover a new platform through shared posts from contacts
3. join a new platform by copying the agent profile and allocating attention dynamically
4. churn from a platform by setting its attention to zero and moving attention elsewhere

It must also support:

- partial adoption, where not every agent joins every platform
- dormant memberships, where churn does not delete history
- experiments that model bans, heavy moderation, or cyberbullying as migration pressure

## Transfer Mode Decision Matrix

Use this as the default implementation guide:

| Mode | Direction | Best fit | Visibility required | Recommendation |
|---|---|---|---|---|
| Push | current platform -> sibling platform | cross-post, cross-share, repost-like actions | source may export, destination may accept inbound content | default choice |
| Pull | sibling platform -> current platform | import, remote retrieval, feed aggregation | current platform may read from sibling, sibling exposes a visible feed | optional extension |
| Hybrid | both directions | research prototypes, explicit federation experiments | both export and import permissions must be enabled | only when the experiment needs it |

Practical guidance:

- start with push only
- add pull only if the study requires remote import semantics
- use hybrid only when you want to measure interaction between export and import policies
- never expose pull globally by default because it increases the risk of accidental data leakage across sibling experiments

## Compatibility Invariants

These are the non-negotiable constraints:

- solo simulations remain available
- the default remains single-platform
- platform-specific runtimes remain native
- no multi-platform table or column is required when the feature is disabled
- the admin must explicitly declare discoverable sibling instances

## Terminology

### Sibling simulation instance

A sibling simulation instance is any platform instance that belongs to the same multi-platform experiment graph and can be discovered by agents.

Sibling instances may be:

- homogeneous: same platform type, different instance
- heterogeneous: different platform type, same multi-platform experiment

### Persona

A persona is the stable simulated person that can be copied into multiple platform instances.

### Membership

Membership is the local representation of a persona inside one platform instance, with local attention and local history.

### Provenance

Provenance is the origin and transformation metadata attached to a content item that was shared, reposted, quoted, or copied across platforms.

## Reading Order

Start here, then continue with:

1. [Architecture](02-architecture.md)
2. [Persistence and Actions](03-persistence-and-actions.md)
3. [Admin UI](04-admin-ui.md)
4. [Implementation Plan](05-implementation-plan.md)
5. [Verification](06-verification.md)
6. [Engine Migration Checklist](07-engine-migration-checklist.md)
7. [Synchronous Progression](08-synchronous-progression.md)
