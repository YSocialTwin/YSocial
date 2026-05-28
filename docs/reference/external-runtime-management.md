# External Runtime Plugins

## Overview

YSocial can manage external runtime repositories directly from the admin interface at:

- `/admin/external_runtimes`

This panel manages the runtime repositories installed under:

- `/Users/rossetti/PycharmProjects/YWeb/external`

The panel is intentionally limited to a fixed whitelist of supported plugins. It does not expose arbitrary shell access or arbitrary repository URLs.

Installed plugins expose metadata through:

- `external/<plugin>/meta/info.json`
- `external/<plugin>/meta/registry.json`
- aggregated index: `external/plugins.json`

## Supported Plugin Categories

Plugins are organized into two top-level categories:

- `Simulation Runtimes`
  - `Microblogging`
    - `YClient`
    - `YServer`
  - `Forum`
    - `YClientReddit`
    - `YServerReddit`
  - `HPC`
    - `YSimulator`
- `Agent Plugins`
  - `y_agents_plugins`

The experiment creation flow already uses these plugin states to determine which experiment types are available.

## Acquisition Model

Each plugin card exposes an `Installation source` selector.

### Standard source: GitHub Release

This is the default path when releases are available.

Behavior:

- downloads the selected GitHub release archive
- extracts it under the fixed `external/...` target path
- does not require `git` on the host machine

This is the preferred installation path for user-facing deployments.

### Advanced source: Git checkout

This path is available when you explicitly need branch-aware development workflows.

Behavior:

- clones the repository into the fixed `external/...` target path
- allows later `Fetch` and `Update`
- requires `git` to be available on the host machine

## Post-Install Actions

After a plugin is present locally, the panel allows:

- `Install Dependencies`
- `Validate`
- `Delete`
- `View Logs`

For git-managed checkouts, the `Advanced maintenance` panel also allows:

- `Fetch`
- `Update`

Release-installed plugins do not support `Fetch` or `Update`. If you need branch-based maintenance, delete the release install and reinstall using `Git checkout`.

## GitHub Authentication

The panel supports an optional session-scoped GitHub token.

Purpose:

- avoid anonymous GitHub API rate limiting
- access private release metadata or release assets when the current admin is allowed to see those plugins

Characteristics:

- configured from the `GitHub session` box in `/admin/external_runtimes`
- stored only in the current Flask session
- used for release discovery and release archive download
- not required for public repositories when anonymous API access is sufficient

This is not OAuth. It is a pragmatic token-based session login for release operations.

## Visibility Model

Plugin visibility is filtered before rendering the panel.

Rules:

- public plugins are visible to all admin users with access to the panel
- private plugins are visible only to users allowed by the runtime registry
- visibility can also be overridden through environment configuration

Current implementation uses:

- runtime metadata in:
  - `/Users/rossetti/PycharmProjects/YWeb/y_web/src/external_runtime/registry.py`
- optional environment override:
  - `YSOCIAL_PLUGIN_VISIBILITY`

This visibility model is independent from GitHub account identity. It controls what the admin UI shows, not what GitHub itself authorizes.

## Operational Safety

Mutating actions are blocked while experiments depending on the same runtime group are active.

This applies to:

- install from release
- clone
- fetch
- update
- dependency installation
- delete

This avoids updating runtime code while active experiment processes may still be importing or executing it.

`Agent Plugins` are shown as shared repositories rather than platform-specific runtime stacks, so they do not report a single experiment-family lock in the same way the simulation runtimes do.

## Dependency Installation

Dependency installation always uses the same Python interpreter currently running YSocial.

This is visible in the panel and enforced server-side.

Effect:

- plugin dependencies are installed into the same environment used by:
  - `y_social.py`

This avoids subtle mismatches where the plugin dependencies end up installed in a different interpreter than the one serving the application.

## Runtime Status Indicators

Each plugin card shows compact status badges such as:

- `Installed`
- `Not installed`
- `Git`
- `Release`
- `Private`
- `Public`
- `Dirty`
- `Symlink`

Cards are folded by default so the page stays scannable. The panel is split by category and group. For plugin repositories, category, group, description, authors, and repository URL are taken from `external/plugins.json`, which is rebuilt from installed plugin `meta/info.json` files.

## Logs and Output Inspection

The panel stores structured plugin operation logs and surfaces them in two places:

- a right-side `Operation Output` panel with collapsible entries
- a dedicated per-plugin `View Logs` page

The output includes terminal logs for:

- dependency installation
- validation
- git operations
- release download/install failures

## Embedded vLLM Availability in HPC Client Creation

The HPC client creation page also adapts to the current Python environment.

Specifically:

- `Embedded vLLM` is disabled in `/admin/clients_hpc` when the current interpreter does not provide a supported embedded runtime

Detected packages:

- `vllm`
- `vllm_mlx`
- `vllm_metal`

This prevents selecting an embedded backend that the current environment cannot actually run.

## Success Criteria

The plugin panel is working correctly when:

1. the page loads without blocking on remote git/network calls
2. public/private plugin visibility matches the configured policy
3. a missing plugin can be installed from a GitHub release without requiring `git`
4. dependency installation logs appear in the right-side output panel
5. git-managed plugins can still be fetched/updated on selected branches
6. actions are blocked while dependent experiments are active
7. validation confirms required files/imports after installation

## Limitations

- release installs are archive-based, so they do not preserve git history
- private plugin visibility in the UI does not automatically prove GitHub authorization
- authenticated GitHub access currently uses a session token, not a delegated OAuth flow
- branch selection is meaningful only for git-managed checkouts

## Relevant Source Files

- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/external_runtime/registry.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/src/external_runtime/manager.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_external_runtimes.py`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/external_runtimes.html`
- `/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/external_runtime_logs.html`
