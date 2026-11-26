# YSocial 4.1.0: release report (pre-merge hardening)

Prepared on 26 November 2026 on the branches listed below. Nothing was merged or pushed, and no `main` was touched.
The date of the release and its changelog heading are set on the day of the merge (see "Merge window").

## What the release contains

* `PLATFORM_API` 1.5 (`y_web.sdk`): fixed-order recommenders (1.4) and `viewer_user` (1.5); contract recorded in
  `y_web/tests/data/sdk_api.json`.
* `EXTENSION_API` 1.0 (`y_web.sdk.extensions`) with a contract test; `min_core_version` and `extension_api` checked when an
  extension loads; `min_ysocial_version` in the built-in plugin list.
* Scenario Design 1.2.0 with platform-provided drivers (driver contract 1.3); the Standard and HPC adapters live in
  YServer and YSimulator.
* Training Modules 1.34.0, Frontend Adds-on 0.3.0, Reactive Agents 0.12.0.
* A decoupling gate in the core tests and `scripts/metrics/decoupling.py`.
* `scripts/dev/fresh_install_check.sh`, the clean-install check used below.

## Decoupling, before and after

| Measure | Start | Now |
| --- | --- | --- |
| Platform imports outside `y_web.sdk` (YForum, YPhotoSharing, YServerReddit) | 2, 2, 3 | 0, 0, 0 |
| Extension imports outside `y_web.sdk.extensions` (all four) | 274 | 2 (Scenario Design: `y_web.src.im.scenario`, leaves with Scenario Design 2.0) |
| Mentions of a platform by name in the core | 464 | 464 (the ceiling is kept; they are historical migrations, data and assets) |
| Collected tests in the core | 3880 | 3968 |

## Versions and branches

| Repository | Branch to merge | Commit | Commits over `main` |
| --- | --- | --- | --- |
| YFederation | `platform-decoupling` | 6ec9f85 | 1 |
| YServer | `pre-merge-phase4` | 561668c | 32 |
| YServerReddit | `pre-merge-phase4` | f6edcfd | 30 |
| YSimulator | `pre-merge-phase4` | 433b9a5 | 38 |
| YForum | `pre-merge-phase4` | 2c42634 | 42 |
| YPhotoSharing | `pre-merge-phase3` | c42d003 | 31 |
| YInstantMessaging | `pre-merge-phase3` | 15bd79e | 24 |
| YDating | `pre-merge-hardening` | 2b6aad9 | 27 |
| ScenarioDesign | `pre-merge-phase5` | 8efddb4 | 53 |
| TrainingModules | `pre-merge-phase5` | 522cb63 | 72 |
| frontend_adds-on | `pre-merge-phase5` | 5186cc3 | 7 |
| reactive_agents | `pre-merge-phase5` | ce181e8 | 6 |
| YSocial (core) | `pre-merge-phase5` | see `git rev-parse pre-merge-phase5` | 156+ |
| YCreator | `pre-merge-phase7` (enters the window only if Giulio confirms; see the phase 7 section of the plan log) | 103462a | 134 |

Every branch above contains the current `main` of its repository (a fast-forward merge is possible). The commits made
during this hardening are listed per phase in `PLAN_LOG.md` and in the live status document.

## Tests

* Core: 3968 collected; on Python 3.12 and on Python 3.11, 3812 passed, 156 skipped, 0 failed, with the same test
  identifiers on both. Run in chunks on a virtual machine; the GitHub CI on 3.11 and 3.12 (point 1 of the plan) still has to
  run on the branch before the merge.
* Training Modules 1243, Scenario Design 394, Reactive Agents 149, Frontend Adds-on 54: all passed.
* Platform suites: YServer 53 (6 skipped), YServerReddit 93, YForum green; YPhotoSharing, YInstantMessaging and YFederation
  were measured earlier in the phase 2 residuals.
* Clean install (`scripts/dev/fresh_install_check.sh`, new clone of every repository, new data folder): the application
  starts, the administrator signs in, seven administration pages open, seven experiments are created (one per platform and
  runtime) and their detail pages open; the contract suites and the suites of the four extensions pass on that
  installation.

## What the clean-install check does not cover

* A simulation is not run: no client or server process is started, so a study module is not taken through to its final
  questionnaire and nothing is published to a running experiment. Export and re-import of a Training Modules bundle is
  covered by that plugin's suite (`test_bundle.py`, `test_runs.py`) on the clean installation, with a stand-in
  experiment, not on a real one.
* The HPC publication adapter of Scenario Design has no end-to-end test (it needs a YSimulator database). Publish a
  scenario on an HPC experiment by hand before the release.
* YCreator was checked separately in phase 7 (clean install on the top core, 146 tests, real human-gateway run); it is not in the table of the fresh install above unless `WITH_YCREATOR=1` is set.

## Findings worth a decision

1. **Visibility of private repositories.** On a clean installation without the development flag, a platform whose
   repository is still classified private is hidden until GitHub reports it public. The check found that Photo Sharing,
   Instant Messaging and Dating could not be used for experiments in that state (they could with `--development` or
   once the visibility probe reported them public), and that this depends on a probe that runs after startup. See
   `Claude outputs/pre-merge/repo-visibility-report.md` for the three options.
2. **Silent empty experiment menu.** A new core with old platform repositories starts normally and registers no
   platform, with no message. A line in the log or on the dashboard saying that a platform repository has no
   `ysocial_platform` package would help; it is not part of this release.
3. The Git objects of the core checkout hold a few hundred leftover `tmp_obj_*` files (interrupted writes); they are
   harmless and `git gc --prune=now` removes them.

## Debts declared

* Feed administration (about 85 mentions) stays in the core: shared by microblogging, forum and photo sharing, and moving
  it needs an admin-page hook (`docs/platform-repositories.md`).
* The Scenario Design adapters exist twice (plugin and platform) until Scenario Design 2.0 (point 3b, after 4.1.0); a
  core test compares them.
* Forum, Photo Sharing and Instant Messaging still use the adapters of the plugin.
* Two imports of `y_web.src.im.scenario` in Scenario Design.

## Decisions that remain with Giulio

* Visibility of the four extensions and of the private platform repositories (finding 1).
* Whether YCreator enters the window (phase 7): the platform is ready; what remains is the catalogue choice (merge in the same window, or point the catalogue entry to `creator-v1`), its first version (proposed 0.1.0) and whether the internal reports `docs/g1-report.md` ... `g10-report.md` are public.
* The date of 4.1.0 and the heading of the changelog.

## Merge window (to be run by hand, in this order)

Check first that the GitHub CI is green on the branch of the core and that nothing changed on any `main` (`git fetch`
and `git rev-list --count <branch>..origin/main` must be 0 in every repository).

1. Tags to return to the starting point, in every repository, before anything else:

   ```bash
   git fetch origin
   git tag pre-4.1-main origin/main && git push origin pre-4.1-main
   ```

2. Candidate tags on the branch to merge (after the CI is green): `git tag 4.1.0-rc1 <branch> && git push origin 4.1.0-rc1`.
3. Fast-forward, in this order (`git checkout main && git merge --ff-only <branch> && git push origin main`):

   | Order | Repositories | Branch |
   | --- | --- | --- |
   | 1 | YFederation | `platform-decoupling` |
   | 2 | YServer, YServerReddit, YSimulator, YForum | `pre-merge-phase4` |
   | 2 | YPhotoSharing, YInstantMessaging | `pre-merge-phase3` |
   | 2 | YDating | `pre-merge-hardening` |
   | 3 | ScenarioDesign, TrainingModules, frontend_adds-on, reactive_agents | `pre-merge-phase5` |
   | 4 | YSocial (core) | `pre-merge-phase5`; then set the date in `CHANGELOG.md` (heading `[4.1.0] - <date>`), and tag `4.1.0` |
   | 2 (conditional) | YCreator | `pre-merge-phase7`; tag `pre-4.1-main` on its `main` before the fast-forward; if it does not enter, it stays on `creator-v1` |

4. After the merge: regenerate `external/plugin_registry_cache.json` once the visibility decision is made, repeat
   `RESUME=0 scripts/dev/fresh_install_check.sh` starting from the `main` branches (`BRANCHES=main`), and delete the
   intermediate branches (`platform-decoupling`, `fixed-recsys`, `sd-agnostic`, `routing-allocation`, `frontend_v2`, the
   `pre-merge-*` ones) after a week without regressions reported.
5. The built-in plugin list (`builtin.json`, `plugin-registry` branch `pre-merge-hardening`, commit 9f521ea) is merged in its
   own repository, then synchronised in the core with `scripts/packaging/sync_builtin_plugins.py`.

A reset of a `main` is for Giulio to decide, never an agent: `git reset --hard pre-4.1-main` restores it from the tag.
