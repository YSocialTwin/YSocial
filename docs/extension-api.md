# Extension API

`y_web.sdk.extensions` is the contract between YSocial and its extensions (Scenario Design, Training Modules, frontend
add-ons, reactive agents). An extension imports from there and from nothing else in `y_web`:

```python
from y_web.sdk.extensions.models import Exps, User_mgmt
from y_web.sdk.extensions.db import db
from y_web.sdk.extensions.i18n import plugin_gettext
```

Every name is a re-export of, or a forwarder to, code that already exists in the core. Nothing here has logic of its
own, and the old import paths keep working, so an extension can migrate one file at a time.

## Groups

`access`, `agents`, `content`, `db`, `experiments`, `federation`, `i18n`, `interview`, `models`, `paths`, `platforms`,
`runtime`, `settings`, `signup`. A group is loaded when first used, and importing it has no side effect (no
application, no file in the data folder).

## Versions

`EXTENSION_API` is `MAJOR.MINOR`, separate from the platform API (`PLATFORM_API`).

* A **minor** version only adds names.
* A **major** version may remove or change one. A name is deprecated for one minor version before it goes.
* `y_web/tests/data/sdk_extensions_api.json` records the surface (names, signatures and, for a forwarder, the core
  function it reaches and that function's signature). `y_web/tests/test_sdk_extensions_contract.py` fails when the
  record and the code differ: update `EXTENSION_API` and record the change with
  `UPDATE_SDK_EXTENSIONS_API=1 pytest y_web/tests/test_sdk_extensions_contract.py`.
* A forwarder looks its target up when called, so the core can move its internals as long as the function keeps its
  meaning; the record catches a signature that changes.

## Declaring what an extension needs

In `meta/info.json`:

```json
{ "min_core_version": "4.1.0", "extension_api": "^1.0" }
```

At load time the core compares them with its own version and with `EXTENSION_API`. An extension that needs more than
the core offers is not loaded, and the administration shows its name, the version it needs and the version found. An
extension without the two fields still loads, with a warning in the log. `max_core_version` is optional and only for a
known limit.

A core older than the extension needs is protected in two ways. The suite in `meta/registry.json` carries
`min_app_version`, which every core since 4.0.0 checks: the plugin is not loaded and the error names both versions. The
catalogue of the public plugin registry carries `min_ysocial_version`, and a core that is too old skips the entry. The
list of built-in plugins is generated from the `plugin-registry` repository (`builtin.json`); an entry there may carry
`min_ysocial_version` too, and the installer of a 4.1.0 core then refuses before downloading anything.

## Migrating an extension

1. List its imports: `grep -rnE "^\s*(from|import) y_web" <repo>`.
2. Replace each with the group in `docs/extension-api-inventory.md`. A name that is missing is a request for the core,
   not a reason to import an internal.
3. Add a test that scans the sources and fails on `from y_web.src` or `from y_web import`, with a short list of
   documented exceptions (see the inventory).
