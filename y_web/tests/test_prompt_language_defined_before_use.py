"""``prompt_language`` must be assigned before it is read in every route function.

Regression: ``create_hpc_client`` read it to write the prompt pack before resolving it, so creating an HPC
client failed with ``UnboundLocalError``.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted(
    p
    for p in (ROOT / "routes").rglob("*.py")
    if "prompt_language" in p.read_text(encoding="utf-8")
)


def _problems(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        stores, loads = [], []
        for node in ast.walk(func):
            if isinstance(node, ast.Name) and node.id == "prompt_language":
                (stores if isinstance(node.ctx, ast.Store) else loads).append(
                    node.lineno
                )
        args = {a.arg for a in func.args.args + func.args.kwonlyargs}
        if (
            loads
            and "prompt_language" not in args
            and (not stores or min(loads) < min(stores))
        ):
            found.append(
                f"{path.name}:{func.name} reads prompt_language at line {min(loads)} before assigning it"
            )
    return found


def test_files_found():
    assert FILES


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_prompt_language_assigned_before_use(path):
    assert not _problems(path)
