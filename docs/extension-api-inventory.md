# Extension API inventory

What the four extensions import from `y_web` today (measured on 26 November 2026 with `scripts/metrics/decoupling.py`,
test files excluded), and where each import goes in `y_web.sdk.extensions`. The surface was kept small: a symbol is
exposed when an extension needs it, and a symbol that exists in the platform SDK is re-exported, not copied.

| Extension | Imports | Mostly |
| --- | --- | --- |
| ScenarioDesign | 166 | `y_web.db` (92), models (57) |
| reactive_agents | 74 | `db` (13), models (22), experiment binding (13), interview helpers (14) |
| TrainingModules | 21 | platform registry, experiment helpers, plugin i18n, sign-up |
| frontend_adds-on | 13 | models (8), plugin runtime, i18n |

## Mapping

| Use | Old path | New path |
| --- | --- | --- |
| Database handle | `y_web.db` | `extensions.db.db` |
| Models | `y_web.src.models` (also `.config`, `.experiment`) | `extensions.models` |
| Access | `y_web.src.system.miscellanea.check_privileges`, `y_web.src.experiment.access.user_can_view_experiment` | `extensions.access` |
| Plugin i18n | `y_web.src.external_runtime.plugin_i18n` | `extensions.i18n` |
| Folders | `y_web.src.system.path_utils` | `extensions.paths` |
| Experiments | `y_web.src.experiment.context`, `.helpers`; `_crud`, `_notifications` of the admin routes | `extensions.experiments` |
| Plugin runtime | `y_web.src.external_runtime.{plugin_loader,frontend_plugins,backend_plugins,registry}` | `extensions.runtime` |
| Platforms | `y_web.platforms` (registry), `y_web.platforms.base` (`STANDARD`, `HPC`) | `extensions.platforms` |
| Text analysis | `y_web.src.llm.content_annotation`, `y_web.src.content.text_utils` | `extensions.content` |
| Agents | `y_web.src.agents.custom_features`, `y_web.src.simulation.adhoc_client` | `extensions.agents` |
| Interview | private helpers of `y_web.routes.api.interview` | `extensions.interview` |
| Frontend settings | `_frontend_settings` of the admin routes | `extensions.settings` |
| Sign-up | `y_web.src.signup` | `extensions.signup` |
| Federation | `y_web.src.federation.dynamic.population_added` | `extensions.federation` |

## Not exposed (documented exceptions)

* `y_web.routes.social.photo._photo_active_user` (frontend_adds-on): the module no longer exists in the core; the code
  is in YPhotoSharing and the call is inside a `try/except`, so on photo-sharing experiments the active user is always
  `None`. This is a latent defect to fix with a platform hook, not with an SDK function.
* `y_web.src.im.scenario` (ScenarioDesign): a hook of the instant-messaging platform, reached through an `ImportError`
  guard. It leaves with the adapters in phase 3.
