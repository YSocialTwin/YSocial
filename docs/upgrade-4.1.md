# Upgrading to YSocial 4.1.0

4.1.0 moves the platforms and the extensions onto two versioned contracts: `y_web.sdk` for the platforms
(`PLATFORM_API` 1.5, `docs/platform-repositories.md`) and `y_web.sdk.extensions` for Scenario Design, Training Modules,
the frontend add-ons and the reactive agents (`EXTENSION_API` 1.0, `docs/extension-api.md`). The core, the platform
repositories and the four extensions are released together: **update all of them in one step**. A half-updated
installation does not break, but it does not give you the new platforms or extensions either, as the checks below show.

## What to update

| Repository | 4.1.0 needs |
| --- | --- |
| YSocial (core) | 4.1.0 |
| YServer, YServerReddit, YSimulator, YForum | `api_version` 1.4 in `meta/registry.json` |
| YPhotoSharing | `api_version` 1.5 |
| YInstantMessaging, YDating | `api_version` 1.3 (still loads: a lower minor is accepted) |
| Scenario Design | 1.2.0 |
| Training Modules | 1.34.0 |
| Frontend Adds-on | 0.3.0 |
| Reactive Agents | 0.12.0 |

On a 4.0.0 core the previous releases stay valid: Scenario Design 1.1.0, Training Modules 1.33.0, Frontend Adds-on 0.2.0,
Reactive Agents 0.11.0. Do not mix them with a 4.1.0 core without updating the extension.

## Updating from the Plugins page

Update the core first, then use the *Plugins* page (or `git pull` in each folder of `external/`) for every repository
listed above. Restart YSocial once everything is in place. Repositories still marked private are only offered to an
administrator who may see them (`--development`, an allow-list, or once GitHub reports the repository public).

## What happens with a half-updated installation

These are the results of the cross-compatibility trial of 26 November 2026 (new checkout of every repository, in a
clean folder; `scripts/dev/fresh_install_check.sh` with `MIX=core-top` and `MIX=platforms-top`).

**New core, old repositories (`main` of the platforms and of the extensions).** The application starts and every
administration page opens (dashboard, experiments, frontend settings, Scenario Design, Training Modules, plugins). The
old platform repositories do not contain the `ysocial_platform/` package, so **no platform is registered**: you cannot
create an experiment, and the application says nothing about it. If the experiment menu is empty after an update, a
platform repository was not updated.

**Old core (4.0.0), new repositories.** The application starts as a 4.0.0 installation and ignores the new platform
packages (the 4.0.0 core carries its platforms inside). The four extensions are refused at load with a message that names
both versions, for example:

```
Backend settings suite 'scenario_design' is installed but failed validation:
['suite requires app version between 4.1.0 and ∞, current app version is 4.0.0']
```

Nothing is downloaded or changed: update the core and restart.

## For people who write a platform or an extension

* A platform declares the API it was written for in `meta/registry.json` (`api_version`); an older minor still loads, a
  newer minor or another major is refused with both numbers in the message. See the table of versions in
  `docs/platform-repositories.md`.
* The platform hook `viewer_user(experiment)` (1.5) answers who the logged-in person is inside the experiment's own
  database; extensions ask the provider instead of importing a platform's routes.
* An extension imports the core only from `y_web.sdk.extensions` and declares `min_core_version` and `extension_api` in
  `meta/info.json`. The migration guide is `docs/extension-api.md`; the old import paths keep working during 4.1.
* A platform that serves Scenario Design provides its own driver (`scenario_design_driver`, driver contract 1.3); the
  Standard and HPC publication adapters now live in YServer and YSimulator (`docs/adapters-move.md` in Scenario Design).

## Going back

Every repository has a tag `pre-4.1-main` on the commit of `main` before the merge. To return to 4.0.0, check that tag
out in each repository (core and repositories together) and restart. The core migrates its databases when it starts, and a migration is not undone by going back to an older core: keep a
copy of the data folder before you update.
