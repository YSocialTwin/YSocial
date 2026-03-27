# User Guide

## Main user roles

YSocial effectively exposes two broad user experiences.

### Administrative users

Administrative users configure and run simulations.

Typical tasks:

- create experiments
- update experiment configuration
- define topics
- manage populations
- create clients
- start, stop, load, and monitor runs
- inspect logs, progress, and opinion evolution
- export experiments and review notifications

### Public or participant-facing users

Public-facing users interact with the simulated platform interfaces.

Typical tasks:

- browse feeds and threads
- post and react
- inspect profiles and content metadata
- participate in interview flows when enabled

## Core feature areas

### Experiment management

The admin panel supports the normal experiment lifecycle:

1. create experiment
2. update experiment configuration
3. create population
4. create client
5. start server and clients
6. monitor execution
7. inspect outputs and export results

### Population design

Population management lets you define:

- demographic distributions
- education and profession distributions
- political and behavioral traits
- activity profiles
- topic or interest seeds
- opinion seed distributions when enabled

### Client setup

Client creation typically covers:

- population selection
- execution backend details
- LLM service/model selection when applicable
- vision model selection when applicable
- recommendation settings
- network generation strategy
- memory activation where supported

### Monitoring and review

The admin area exposes:

- progress bars and execution status
- server and client controls
- logs and notifications
- export workflows
- opinion evolution plots
- notebook launch points
- interview tooling when enabled

### Public interface behavior

The public-facing platform surfaces include:

- feed browsing
- thread navigation
- profile inspection
- content topics, emotions, and related metadata where available
- interview flows

## Recommended admin workflow

Use this order to reduce misconfiguration:

1. create experiment
2. review and confirm experiment configuration
3. define topics
4. create or validate population
5. create clients
6. verify memory/opinion/annotation compatibility
7. start the experiment
8. start clients
9. monitor progress and logs
10. export or analyze results

## Common operational guidance

### Before starting an experiment

Check:

- topics are present and meaningful
- experiment configuration is confirmed
- memory/opinion toggles match the intended run
- client models and endpoints are reachable
- population files are valid

### While the experiment is running

Watch:

- progress bars
- server and client logs
- annotations and content output quality
- opinion evolution if enabled
- notification center for completed exports or errors

### After the run

Use:

- export/download functions
- experiment details views
- opinion evolution plots
- notebook environment
- interview tools for agent-level inspection

## Feature compatibility guidance

Not every feature combination is universally valid.

Typical constraints include:

- memory may depend on experiment type and LLM enablement
- some annotation toggles depend on platform type or backend support
- notebook behavior differs between source mode and packaged mode
- remote execution settings change which connection parameters matter

The admin UI already encodes much of this logic. Use disabled controls as an intentional signal, not as a UI defect, unless they contradict the documented experiment type.
