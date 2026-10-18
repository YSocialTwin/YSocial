"""Client modules must not use names they never import (pyflakes 'undefined name')."""

import ast
import pathlib

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.external_repo]

ROOT = pathlib.Path(__file__).resolve().parents[2] / "external"
MODULES = [
    "YClient/y_client/classes/page_agent.py",
    "YClient/y_client/classes/fake_page_agent.py",
    "YClientReddit/y_client/classes/base_agent.py",
]


@pytest.mark.parametrize("rel", MODULES)
def test_prompt_store_is_imported_when_used(rel):
    path = ROOT / rel
    if not path.exists():
        pytest.skip("external repo not present")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = any(
        isinstance(n, ast.Name) and n.id == "prompt_store" for n in ast.walk(tree)
    )
    imported = any(
        isinstance(n, ast.ImportFrom)
        and any(a.name == "prompt_store" for a in n.names)
        or isinstance(n, ast.Import)
        and any(a.name.endswith("prompt_store") for a in n.names)
        for n in ast.walk(tree)
    )
    assert not used or imported, f"{rel} uses prompt_store without importing it"
