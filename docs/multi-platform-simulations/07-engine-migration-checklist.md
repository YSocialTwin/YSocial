# Engine Migration Checklist

This is the ad hoc migration document for implementing the feature across each simulation engine.

## Shared Checklist

Before touching any engine:

- create the canonical provenance tables
- add `persona_uuid` to `user_mgmt`
- define the shared membership and action-event tables
- keep solo execution as the default
- verify that existing platform-specific flows still load

## Microblogging Checklist

### Data model

- update `post` with cross-platform provenance fields
- keep `shared_from` for same-platform behavior
- attach `content_provenance_id` to cross-posted and cross-shared rows

### Runtime

- allow agents to cross-post into another sibling instance
- allow agents to cross-share remote content
- allow attention to move away from a stressed microblogging platform

### UI

- show provenance badges on shared posts
- show membership and attention state in the multi-platform admin section

### Success criteria

- a microblogging post can be traced back to its origin platform and source experiment
- shared content still renders in the native feed

## Forum Checklist

### Data model

- update forum `post` rows with the same provenance fields used by microblogging
- preserve `shared_from` for same-platform shares
- record provenance for RSS-derived or copied content where applicable

### Runtime

- allow discovery through shared content in the contact graph
- allow forum-native cross-share and cross-post decisions
- allow churn when moderation or harassment increases stress

### UI

- surface provenance in feed and thread views
- show platform portfolio state in the multi-platform admin area

### Success criteria

- forum content keeps a stable origin trail across sibling instances
- forum-specific views remain native and readable

## Photo Sharing Checklist

### Data model

- update the photo engine's native photo content tables with provenance fields
- add equivalent provenance fields to `image_posts` where that table participates in shared image handling
- do not force photo content into the microblogging `post` schema

### Runtime

- allow photo content to be cross-posted or cross-shared into sibling platforms
- allow discovery from photo shares propagated through contacts
- allow churn and attention shifting under stress or low reward

### UI

- expose provenance badges in photo views
- surface cross-platform membership and attention in the multi-platform admin section

### Success criteria

- photo-native content remains photo-native
- cross-platform provenance is still traceable
- photo sharing does not regress into a post-only model

## Cross-Engine Checks

- verify that the same persona can exist in multiple engines
- verify that a join event produces a new local membership without losing history
- verify that a churn event only zeroes attention and marks the membership dormant
- verify that analytics can explain where a cross-platform item came from and where it went

