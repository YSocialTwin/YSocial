"""The platform API is a contract (plan, phase F3, gate G3).

Two guards:

* ``data/sdk_api.json`` records what ``y_web.sdk`` offers for ``PLATFORM_API``: its names, the signatures of the
  functions and of the provider hooks. Anything recorded must still be there unchanged; a new name or a new
  hook is a minor version and must be recorded (``UPDATE_SDK_API=1 pytest y_web/tests/test_sdk_contract.py``).
* a provider reaches the core through the SDK only: the modules that hold the built-in providers may import
  from ``y_web`` the SDK, the platform package and translations, plus the platform-specific modules listed in
  ``data/sdk_provider_imports.json``. That list can only shrink: each platform leaves it when its code moves
  to its own repository.
"""

import ast
import inspect
import json
import os
from pathlib import Path

import pytest

import y_web.sdk as sdk
from y_web.platforms.base import PlatformProvider

DATA = Path(__file__).parent / "data"
PROVIDER_MODULES = ("platforms/base.py", "platforms/builtin.py")
ALWAYS_ALLOWED = ("y_web.i18n", "y_web.platforms", "y_web.sdk")


def _signature(obj) -> str:
    return str(inspect.signature(obj))


def current_api() -> dict:
    names = {}
    for name in sdk.__all__:
        value = getattr(sdk, name)
        if inspect.ismodule(value):
            names[name] = {
                "kind": "module",
                "members": {
                    member: _signature(getattr(value, member))
                    for member in sorted(dir(value))
                    if not member.startswith("_")
                    and inspect.isfunction(getattr(value, member))
                    and getattr(value, member).__module__ == value.__name__
                },
            }
        elif inspect.isclass(value):
            names[name] = {"kind": "class"}
        elif callable(value):
            names[name] = {"kind": "function", "signature": _signature(value)}
        else:
            names[name] = {"kind": "value"}
    hooks = {
        name: _signature(member)
        for name, member in inspect.getmembers(PlatformProvider, inspect.isfunction)
        if not name.startswith("_")
    }
    return {"platform_api": sdk.PLATFORM_API, "names": names, "provider_hooks": hooks}


def test_the_sdk_surface_matches_the_record():
    path = DATA / "sdk_api.json"
    current = current_api()
    if os.environ.get("UPDATE_SDK_API"):
        path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    recorded = json.loads(path.read_text("utf-8"))
    assert current == recorded, (
        "the platform API changed: a removed or altered name breaks providers (major version), "
        "a new one is a minor version; update PLATFORM_API and record it with UPDATE_SDK_API=1"
    )


def _y_web_imports(source: str):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "y_web" or node.module.startswith("y_web."):
                yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "y_web" or alias.name.startswith("y_web."):
                    yield alias.name


def _used_imports() -> dict:
    root = Path(sdk.__file__).parent.parent
    used = {}
    for relative in PROVIDER_MODULES:
        for module in _y_web_imports((root / relative).read_text("utf-8")):
            if module == "y_web" or any(
                module == ok or module.startswith(ok + ".") for ok in ALWAYS_ALLOWED
            ):
                continue
            used.setdefault(module, set()).add(relative)
    return used


def test_providers_reach_the_core_through_the_sdk_only():
    allowed = set(json.loads((DATA / "sdk_provider_imports.json").read_text("utf-8")))
    outside = sorted(set(_used_imports()) - allowed)
    assert not outside, (
        "provider code imports core internals directly: "
        f"{outside}. Use y_web.sdk.services (or add a service there)."
    )


def test_the_list_of_platform_specific_imports_only_shrinks():
    recorded = set(json.loads((DATA / "sdk_provider_imports.json").read_text("utf-8")))
    unused = sorted(recorded - set(_used_imports()))
    assert (
        not unused
    ), f"no longer imported, remove from sdk_provider_imports.json: {unused}"
