"""The publication adapters of YServer (Standard) and YSimulator (HPC) are the plugin's adapters, unchanged.

Phase 3 of the 4.1.0 hardening moved the adapter code next to the platform it writes into. A moved copy must not change
what a publication writes, so this test compares the two sources statement by statement: everything except the import
lines (and the assignments that take the same names from the plugin's ``support`` instead) must be identical. When the
plugin's own copy is removed (Scenario Design 2.0) this test goes with it and the platform's copy is the only one.
"""

import ast
from pathlib import Path

import pytest

EXTERNAL = Path(__file__).resolve().parents[2] / "external"
BACKEND = EXTERNAL / "ScenarioDesign" / "modules" / "scenario_editor" / "backend"

PAIRS = [
    (
        "standard",
        BACKEND / "adapters" / "standard.py",
        EXTERNAL / "YServer" / "ysocial_platform" / "scenario_adapter.py",
    ),
    (
        "hpc",
        BACKEND / "adapters" / "hpc.py",
        EXTERNAL / "YSimulator" / "ysocial_platform" / "scenario_adapter.py",
    ),
]

BINDERS = {"S", "_m", "_h", "_scenario_design"}


def _leftmost(node):
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.value if not isinstance(node, ast.Call) else node.func
    return node.id if isinstance(node, ast.Name) else None


def _is_binding(statement):
    if isinstance(statement, (ast.Import, ast.ImportFrom)):
        return True
    return isinstance(statement, ast.Assign) and _leftmost(statement.value) in BINDERS


def _strip(node):
    for field in ("body", "orelse", "finalbody", "handlers"):
        children = getattr(node, field, None)
        if isinstance(children, list):
            kept = [child for child in children if not _is_binding(child)]
            if not kept and field == "body":
                kept = [ast.Pass()]
            setattr(node, field, kept)
            for child in kept:
                _strip(child)
    return node


def _normalised(path: Path) -> str:
    return ast.dump(
        _strip(ast.parse(path.read_text(encoding="utf-8"))), include_attributes=False
    )


@pytest.mark.parametrize(
    "name,plugin_copy,platform_copy", PAIRS, ids=[p[0] for p in PAIRS]
)
def test_the_platform_copy_has_the_body_of_the_plugin_adapter(
    name, plugin_copy, platform_copy
):
    if not (plugin_copy.exists() and platform_copy.exists()):
        pytest.skip("the plugin or the platform is not installed")
    assert _normalised(platform_copy) == _normalised(plugin_copy)
