"""The extension API is a contract (plan, phase 2).

* ``data/sdk_extensions_api.json`` records what ``y_web.sdk.extensions`` offers for ``EXTENSION_API``: the names of
  every group, the signature of each function and, for a forwarder, the core function it reaches and that function's
  signature. A change is refused until it is recorded (``UPDATE_SDK_EXTENSIONS_API=1 pytest
  y_web/tests/test_sdk_extensions_contract.py``); removing or altering a name is a major version, adding one a minor.
* importing a group has no side effect: no application, no file in the data folder.
"""

import importlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import y_web.sdk.extensions as extensions

DATA = Path(__file__).parent / "data"
RECORD = DATA / "sdk_extensions_api.json"


def _signature(obj) -> str:
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return "?"


def _describe(value) -> dict:
    if inspect.ismodule(value):
        return {"kind": "module"}
    if inspect.isclass(value):
        return {"kind": "class"}
    if callable(value):
        forwarded = getattr(value, "__forward__", None)
        if forwarded:
            module, attr = forwarded
            target = getattr(importlib.import_module(module), attr)
            return {
                "kind": "forwarder",
                "target": f"{module}.{attr}",
                "target_signature": _signature(target),
            }
        return {"kind": "function", "signature": _signature(value)}
    return {"kind": "value"}


def current_api() -> dict:
    groups = {}
    for group in extensions.MODULES:
        module = importlib.import_module(f"y_web.sdk.extensions.{group}")
        groups[group] = {
            name: _describe(getattr(module, name)) for name in sorted(module.__all__)
        }
    return {"extension_api": extensions.EXTENSION_API, "groups": groups}


def test_the_extension_surface_matches_the_record():
    current = current_api()
    if os.environ.get("UPDATE_SDK_EXTENSIONS_API"):
        RECORD.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    recorded = json.loads(RECORD.read_text("utf-8"))
    assert current == recorded, (
        "the extension API changed: a removed or altered name breaks extensions (major version), a new one is a "
        "minor version; update EXTENSION_API and record it with UPDATE_SDK_EXTENSIONS_API=1"
    )


def test_the_version_is_a_major_dot_minor_string():
    major, minor = extensions.EXTENSION_API.split(".")
    assert major.isdigit() and minor.isdigit()


def test_every_group_is_listed_and_every_listed_name_exists():
    package = Path(extensions.__file__).parent
    on_disk = {p.stem for p in package.glob("*.py") if not p.stem.startswith("_")}
    assert on_disk - {"__init__"} == set(extensions.MODULES)
    for group in extensions.MODULES:
        module = importlib.import_module(f"y_web.sdk.extensions.{group}")
        for name in module.__all__:
            assert hasattr(module, name), f"{group}.{name}"


def test_the_extension_api_is_not_part_of_the_platform_surface():
    import y_web.sdk as sdk

    assert "extensions" not in sdk.__all__


@pytest.mark.parametrize("group", extensions.MODULES)
def test_importing_a_group_has_no_side_effect(group, tmp_path):
    env = dict(os.environ, YSOCIAL_HOME=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-c", f"import y_web.sdk.extensions.{group}"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-800:]
    assert list(tmp_path.iterdir()) == [], "the import wrote into the data folder"
