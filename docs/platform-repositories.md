# Platform repositories

Every simulation platform (microblogging, forum, photo sharing, instant messaging, dating) lives in its own repository and
plugs into YSocial at start-up. YSocial itself has no platform built in: a platform that is not installed is simply not
offered, and installing its repository adds it at the next start (there is no hot install).

| Platform | Repository | Runtimes it declares |
| --- | --- | --- |
| Microblogging | `YSimulator` (plugin *YMicroblogging*) | Standard: `YServer`/`YClient`; HPC: `YSimulator` |
| Forum | `YForum` | Standard: `YServerReddit`/`YClientReddit`; HPC: `YForum` |
| Photo sharing | `YPhotoSharing` | HPC |
| Instant messaging | `YInstantMessaging` | HPC |
| Dating | `YDating` | HPC |

## What a repository contains

```
meta/registry.json            {"platform": {"key", "id" (optional), "api_version", "provider": "ysocial_platform.provider:Class"}}
ysocial_platform/
    provider.py               the PlatformProvider: what the core asks of the platform
    routes/                   views, registered on the blueprints of the core (main, user, experiments, clients, ...)
    templates/                pages, addressed as @<id>/<path>
    static/                   files, served at /platform-static/<id>/...
    <library>/                the platform's own code (optional; provider.library_package)
```

The repository talks to the application through `y_web.sdk` only (`models`, `web`, `runtime`, `social`, `content`,
`federation`, `agents`, `services`, `routes`, `commons`). `PLATFORM_API` is a semantic version: the surface is recorded in
`y_web/tests/data/sdk_api.json`; a removed or altered name needs a major version, a new one a minor version, and the record
is regenerated with `UPDATE_SDK_API=1`.

## How the core finds what a platform provides

* **Pages and actions.** `provider.attach_routes()` imports the `routes` package, whose modules decorate the core
  blueprints (`routes.blueprint("main")`) before they are registered; endpoint names do not change.
* **Templates and static files.** `render_template("@<id>/...")` and `url_for("platform_static_<id>", filename=...)`.
  `asset_v("@<id>/css/x.css")` versions a platform's own file. `<id>` is the identity of the repository
  (`PlatformProvider.provider_id`, declared as `platform.id`): the platform key unless the repository says otherwise. While
  one repository provides a key, the key is a namespace too.
* **Several repositories for one platform (PLATFORM_API 1.1).** A Standard and an HPC repository can provide the same
  `key` if they have different ids and serve different runtimes (`simulator_types`); each is an independent silo. The
  registry answers `variants(key)`, `by_id(id)`, `for_simulator(key, simulator_type)` and `for_experiment(experiment)`;
  `get(key)` and `providers()` still give one provider per key. An address (rule and methods) that one provider serves is
  registered as it wrote it; one that several serve is registered once with a dispatcher that runs the view of the
  provider of the experiment in the address (`exp_id`, `idexp` or `experiment_id`) and answers 404 when that provider does
  not have it (`y_web/platforms/dispatch.py`). An address that names no experiment (the legacy `/feed`) follows the
  `exp_id` of the query string or form, else the experiment the user last opened (kept in the session by every request
  whose address carries an experiment id), else the only active experiment, else the preferred repository (Standard) answers. Two addresses that claim one endpoint name keep the first and register the
  other as `<id>__<endpoint>`.
* **Client modes.** The core looks the views of a mode up by name on the `clients` blueprint: `create_<mode>_client`,
  `update_<mode>_recsys`, `update_<mode>_client_llm`, `update_<mode>_client_settings`, `clients_<mode>`,
  `set_<mode>_opinion_distributions`.
* **Shared pages.** The interview page is a core route that asks the provider (`has_interview`, `interview_redirect`,
  `render_interview`); the profile route asks it for `profile_template`; `registry.default()` is the platform marked
  `default_platform`, which the shared pages fall back on. The header, the profile editor and the chat panel are shared by
  every platform and stay in the core (`templates/social/`, `templates/shared/`).
* **Hooks.** Creation rules, simulator resolution, prompt packs, HPC server and client configuration, switches, run
  length, opinion dynamics, details page and context, analytics, uploads and downloads: see `y_web/platforms/base.py`.
  A platform whose hooks apply only to its HPC runtime sets `hpc_only_hooks`.

## Adding a platform

1. Create the repository with the layout above and a provider whose `key` is unique.
2. Move nothing into the core: use the SDK for everything generic; if something generic is missing, add a wrapper to the
   SDK (and bump `PLATFORM_API`) rather than importing a core module.
3. Add the repository to `external/plugins.json` so the administrator can install it.
4. In the tests, add the repository to `y_web/tests/_platform_alias.py` (`needs` lists the tests that cannot run without
   it) so that the suite runs with and without it.

## Several repositories for one platform

Microblogging and the forum each have two repositories, one per runtime: YServer / YServerReddit (the Standard
runtime, a Flask pair with YClient / YClientReddit) and YSimulator / YForum (the HPC runtime). Each carries the pages,
library and templates it needs, so any subset of them can be installed: the providers are variants of one platform
(`simulator_types` tells which runtime each serves), the addresses both serve go through the route dispatcher, and the
experiment decides which provider answers. A platform with no repository for the runtime of an experiment does not offer
that runtime.

The tests follow the same rule:

* a test that reads or imports one repository is skipped (single test: `requires_platform("YServer")`) or not collected
  (whole file: `needs` in `y_web/tests/_platform_alias.py`) where it is absent;
* a file that works with either repository of a platform is listed in `needs_any`;
* `y_web/tests/data/platform_baseline/moved.json` says which repository serves each route and template that left the
  core, so the baseline is checked only for the repositories that are installed.

`scripts/dev/run_install_matrix.sh` runs the suite with a repository subset at a time (`all`, `standard-only`,
`hpc-only`, `microblogging-only`, `forum-only`, one repository left out each, `none`) and puts the repositories back when
it ends. `MATRIX_SELECT='forum|platform'` limits it to the tests whose file name matches.

## What still names a platform in the core

The shared feed administration (`experiments/_feeds.py`, used by forum, instant messaging and photo sharing), the
`forum_*` tables and migrations, population and agent fields per platform, and the federation tables still mention
platforms by name. `y_web/tests/data/platform_baseline/platform_names.json` records how many mentions each module has; the
budget can only go down.
