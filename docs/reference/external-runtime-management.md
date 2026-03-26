# External Runtime Repositories Management From `/admin`

## Goal

Evaluate the feasibility of adding a dedicated `/admin` panel that can:

- detect which external runtime repositories are installed under `/Users/rossetti/PycharmProjects/YWeb/external`
- clone missing repositories from GitHub
- update installed repositories by pulling the latest remote changes
- install or refresh their Python dependencies
- expose status, logs, and validation results to an administrator

This document focuses on the project-level mechanism, not on the specific business behavior of any one runtime.

## Executive Summary

This is feasible, but it should **not** be implemented as a thin wrapper around arbitrary shell access.

The correct shape is:

- a dedicated admin page and backend service
- a whitelist of supported repositories and branches
- controlled clone / fetch / pull / dependency-install actions
- persistent action logs and validation results
- explicit safety gates around authentication, concurrency, and local modifications

A first version is practical. A robust version requires some structural normalization first.

## Current State

The current codebase already has the basic assumptions needed for such a panel.

### Existing runtime structure

The application loads external runtimes from fixed paths under:

- `/Users/rossetti/PycharmProjects/YWeb/external/YClient`
- `/Users/rossetti/PycharmProjects/YWeb/external/YServer`
- `/Users/rossetti/PycharmProjects/YWeb/external/YClientReddit`
- `/Users/rossetti/PycharmProjects/YWeb/external/YServerReddit`
- `/Users/rossetti/PycharmProjects/YWeb/external/YSimulator`

The runtime loader already resolves platform-specific package locations in:

- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/process_runner.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/server.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/hpc/client.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/hpc/server.py`

### Existing admin-side detection

The admin interface already checks whether certain repositories are present in:

- `/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py`

Specifically, `_external_repo_availability()` already maps installed repositories to platform availability.

That means the project already has:

- a concept of repository presence
- a UI-level dependency on those runtime repositories
- a natural place to surface repository management status

### Existing installation assumption

Current source installation documentation still assumes Git submodule workflow:

- `/Users/rossetti/PycharmProjects/YWeb/docs/installation.md`
- `/Users/rossetti/PycharmProjects/YWeb/.gitmodules`

However, the current `.gitmodules` only declares:

- `external/YServer`
- `external/YClient`

This is already inconsistent with the runtime code, which also expects `YSimulator`, `YClientReddit`, and `YServerReddit`.

That inconsistency should be addressed before calling the feature "complete."

## Feasibility Assessment

## Feasible Scope

A dedicated admin panel can reliably support:

- presence detection for known repositories
- clone of missing repositories into fixed paths
- fetch / pull on already-installed repositories
- dependency installation using known install recipes
- post-action validation checks
- UI feedback on current version, branch, and dirty state

This is a normal backend automation problem.

## Non-Feasible or High-Risk Scope

The panel should **not** support:

- arbitrary repository URLs entered by the user
- arbitrary shell commands from the browser
- branch switching without policy controls
- destructive reset of dirty repositories without explicit confirmation
- mixed local edits and auto-pull without safeguards

That would turn the admin panel into a remote shell and make the deployment model brittle.

## Main Constraints

### 1. Authentication to private repositories

This is the most important operational constraint.

If repositories are private, the server running YSocial must already have one of the following configured:

- SSH access with a deploy key or user key
- HTTPS token-based credentials with read access

Without that, a clone/pull button in `/admin` will fail even if the current desktop user can access the repositories elsewhere.

### 2. Dependency installation is not standardized

At the moment, installation metadata is inconsistent across external repositories.

Observed from the current workspace:

- `/Users/rossetti/PycharmProjects/YWeb/external/YClient/requirements_client.txt`
- `/Users/rossetti/PycharmProjects/YWeb/external/YServer/requirements_server.txt`
- `YClientReddit`, `YServerReddit`, and `YSimulator` do not currently expose a uniform root-level install file in the same way

This means the admin backend would need either:

- a per-repository install recipe registry, or
- a repository-side standardization effort first

### 3. Dirty working trees

These repositories are frequently modified locally during development.

A safe updater must detect and report:

- dirty worktree
- current branch
- upstream tracking branch
- ahead / behind state

A blind `git pull` is not acceptable if there are local changes.

### 4. Runtime process coordination

Pulling or reinstalling runtime repositories while a related experiment is running is unsafe.

The admin feature must block update actions when a dependent process is active, or explicitly require stopping the relevant experiment/server/client first.

## Recommended Product Shape

## Proposed Panel

Add a dedicated admin page such as:

- `/admin/external_runtimes`

The page should list each supported runtime repository with columns like:

- logical role
- local path
- installed or missing
- current branch
- current commit
- upstream tracking status
- dirty or clean
- dependency status
- last validation result
- available actions

## Supported Actions

Per repository:

- `Clone`
- `Fetch`
- `Update`
- `Install Dependencies`
- `Validate`
- `View Logs`

Optional bulk actions:

- `Install Missing`
- `Validate All`
- `Update All Safe Repositories`

## Backend Design

Do not execute git or pip commands directly from route handlers.

Instead:

1. route receives a validated action request
2. request is translated into a job for a controlled service layer
3. job executes with structured logging and timeout handling
4. result is persisted and shown back in the panel

A reasonable internal split would be:

- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/external_runtime/registry.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/external_runtime/git_ops.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/external_runtime/install_ops.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/external_runtime/validation.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/external_runtimes.py`

## Registry Model

Use a hardcoded or config-driven whitelist like:

```python
SUPPORTED_EXTERNAL_REPOS = {
    "microblogging_client": {
        "path": "external/YClient",
        "repo_url": "git@github.com:ORG/YClient.git",
        "default_branch": "main",
        "install": ["pip", "install", "-r", "requirements_client.txt"],
        "validate": ["python", "-c", "import y_client"],
    },
    ...
}
```

This is better than trying to infer behavior dynamically.

## Security Model

This feature should be admin-only and stricter than the rest of the admin UI.

Recommended constraints:

- only `admin` users can clone/update/install
- repository URL cannot be edited from the browser in the first version
- commands are executed only from a server-side whitelist
- all stdout/stderr is captured and persisted
- every operation records:
  - actor
  - timestamp
  - repository
  - action
  - command result
- no secrets are displayed back in the UI

## Required Normalization Before or During Implementation

### A. Standardize all external repositories in one ownership model

Choose one:

- all as submodules
- all as plain managed clones
- all as manually provisioned dependencies with validation only

For an admin-managed panel, the cleanest model is usually:

- plain managed clones under `/Users/rossetti/PycharmProjects/YWeb/external`
- not submodules

Reason:
- browser-driven clone/update semantics align better with normal git repositories than with submodule lifecycle management

### B. Define one install recipe per repository

Because dependency files are inconsistent, create a registry entry for each supported repository.

This avoids unreliable heuristics such as:

- "if `requirements.txt` exists, install that"

That is too fragile.

### C. Define validation probes

Each repository should have a minimal post-install validation rule.

Examples:

- import sanity check
- required entrypoint file exists
- optional smoke command with `--help`

The panel should report validation success independently from clone/pull success.

## Suggested Implementation Phases

## Phase 1: Read-Only Visibility

Deliver first:

- repository presence detection
- branch / commit / dirty status
- dependency file detection
- validation summary

No clone/pull/install yet.

Why:
- low risk
- immediately useful
- establishes the UX and backend model

## Phase 2: Controlled Install of Missing Repositories

Add:

- `Clone`
- `Install Dependencies`
- `Validate`

Only for missing repositories and only from a whitelist.

## Phase 3: Controlled Update

Add:

- `Fetch`
- `Update`

Rules:

- refuse update on dirty worktree
- refuse update while dependent experiment/runtime is active
- require explicit confirmation if local branch is not default branch

## Phase 4: Bulk Operations

Add optional bulk actions with clear safety filters.

Only operate on repositories that are:

- installed
- clean
- on approved branch
- not currently in use

## Operational Steps For a First Implementation

1. Create a registry of supported external repositories and install recipes.
2. Add a read-only admin page listing repository state.
3. Add a backend service layer for git inspection and validation.
4. Persist operation logs in the admin database or a dedicated log file.
5. Add install actions for missing repositories.
6. Add update actions with dirty-state and running-process guards.
7. Add dependency validation and import smoke tests.
8. Add UI feedback for success, failure, and remediation steps.

## Success Evaluation

The feature should be considered successful only if all of the following hold.

### Functional success

- a missing supported repository can be cloned into the correct `external/` path
- dependencies can be installed using the defined recipe
- the panel reports installed status correctly after completion
- an installed repository can be updated when clean and idle
- update is refused when the repository is dirty or actively in use

### Safety success

- non-admin users cannot trigger repository actions
- arbitrary repository URLs cannot be injected from the UI
- command execution is limited to the server-side whitelist
- failures are logged and visible without exposing credentials

### Runtime success

After clone/update/install, the existing runtime checks should pass.

Examples:

- experiment creation page reflects repository presence correctly
- process runner can import the expected runtime package
- supported experiments can start without manual path repair

### UX success

The admin can answer these questions from the panel without using the shell:

- Is the repository installed?
- Is it on the expected branch?
- Is it behind upstream?
- Are there local modifications?
- Are dependencies installed?
- Can I safely update it right now?
- If not, why not?

## Recommended Acceptance Checks

For each supported repository type:

1. remove the local repository from `external/`
2. open the admin panel and verify it shows `Missing`
3. trigger `Clone`
4. trigger `Install Dependencies`
5. trigger `Validate`
6. verify the panel shows commit, branch, and clean state
7. trigger a relevant experiment creation flow and verify availability becomes enabled
8. stop all related runtime processes
9. trigger `Update`
10. verify the commit changes or the panel correctly reports `Already up to date`

Negative-path checks:

1. create an uncommitted local change and verify `Update` is blocked
2. start a dependent experiment and verify `Update` is blocked
3. remove credentials and verify `Clone` fails with a clear operational error

## Recommendation

This feature makes sense and fits the project.

The recommended path is:

- implement it as a dedicated admin operations panel
- treat repositories as a controlled whitelist
- standardize install recipes per repository
- ship read-only visibility first
- add clone/update/install only after validation and process-locking are in place

The part that needs the most discipline is not the UI. It is the operational contract around:

- credentials
- dirty repositories
- dependency recipe normalization
- protection against updating active runtimes

Without those controls, the feature would create more deployment fragility than value.
