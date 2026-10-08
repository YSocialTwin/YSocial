"""Regression guard for a real production bug (reported by the user,
2026-10-03): ``POST .../scenarios`` raised

    ModuleNotFoundError: No module named 'YSimulator'

from ``hpc_fingerprint_counts`` (``hpc_session.py``), on the very first
HPC code path hit in a fresh server process.

Root cause: several functions in ``hpc_session.py`` and
``real_content.py`` did ``from YSimulator.YServer.classes.models import
...`` (or called ``_hpc_post_model()``, which does the same) *before*
entering ``with hpc_session(exp) as session:`` -- but it is
``hpc_session()``'s own ``__enter__`` that calls
``_ensure_ysimulator_on_path()`` (appends ``external/YSimulator`` to
``sys.path``; YWeb core never does this itself, see ``hpc_session.py``'s
module docstring). So the bare import executed *before* ``sys.path`` had
been extended, and failed outright on a cold process -- it only
"worked" once some earlier call had already imported
``YSimulator`` successfully (populating ``sys.modules``, which then
masks the ordering bug for the rest of that process's lifetime). This
is why it was never caught by the test suite here (which always runs
in a fresh process with no HPC fixture that reaches this code path) nor
by routine manual testing (one plugin visibility/HPC call earlier in
the same server process is enough to hide it).

Fix: move every ``from YSimulator...``/``import YSimulator...`` import,
and every ``_hpc_post_model()`` call, to *inside* the
``with hpc_session(exp) as session:`` block, so it always executes
after ``hpc_session()`` has already run the ``sys.path`` bootstrap.

This test enforces that structurally (via ``ast``, no real YSimulator
install needed -- keeps this suite's "Flask + requests only" dependency
footprint, see README.md "Requirements") so a future edit cannot
silently reintroduce the same ordering bug in either file.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "modules" / "scenario_editor" / "backend"


def _is_hpc_session_with(node: ast.With) -> bool:
    """True if *node* is ``with hpc_session(...) as ...:`` (any call
    named exactly ``hpc_session``, regardless of args)."""
    for item in node.items:
        call = item.context_expr
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            if call.func.id == "hpc_session":
                return True
    return False


def _hpc_session_with_ranges(tree: ast.Module) -> list[tuple[int, int]]:
    """Every ``with hpc_session(...) as session:`` block's
    (first_line, last_line) range, found anywhere in the module
    (nested in any function/if), inclusive of the ``with`` line
    itself -- an import on the ``with`` line's own line number would be
    a syntax error anyway, so this is only ever a body-line question in
    practice."""
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With) and _is_hpc_session_with(node):
            last_line = node.lineno
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    last_line = max(last_line, child.lineno)
            ranges.append((node.lineno, last_line))
    return ranges


def _line_in_any_range(lineno: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= lineno <= end for start, end in ranges)


def _assert_every_ysimulator_import_is_inside_an_hpc_session_block(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    with_ranges = _hpc_session_with_ranges(tree)

    offenders = []
    for node in ast.walk(tree):
        module_name = None
        if isinstance(node, ast.ImportFrom) and node.module:
            module_name = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "YSimulator":
                    module_name = alias.name
                    break
        if module_name and module_name.split(".")[0] == "YSimulator":
            if not _line_in_any_range(node.lineno, with_ranges):
                offenders.append(node.lineno)

    assert not offenders, (
        f"{path}: YSimulator import(s) on line(s) {offenders} sit outside any "
        "'with hpc_session(...) as session:' block -- this reintroduces the "
        "cold-sys.path ModuleNotFoundError bug (see this test's module "
        "docstring). Move the import inside the 'with' block."
    )


def test_hpc_session_py_never_imports_ysimulator_before_entering_hpc_session():
    _assert_every_ysimulator_import_is_inside_an_hpc_session_block(
        BACKEND_DIR / "hpc_session.py"
    )


def test_real_content_py_never_imports_ysimulator_before_entering_hpc_session():
    _assert_every_ysimulator_import_is_inside_an_hpc_session_block(
        BACKEND_DIR / "real_content.py"
    )


def test_hpc_post_model_helper_is_never_called_before_entering_hpc_session():
    """``real_content.py``'s ``_hpc_post_model()`` helper itself imports
    YSimulator -- so a call site has the exact same bug if it calls that
    helper *before* ``with hpc_session(...)``, even though the import
    statement itself is safely tucked inside the helper function (the
    AST-level checks above can't see that indirection, hence this
    separate, call-site-aware check)."""
    path = BACKEND_DIR / "real_content.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    with_ranges = _hpc_session_with_ranges(tree)

    offenders = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_hpc_post_model"
        ):
            if not _line_in_any_range(node.lineno, with_ranges):
                offenders.append(node.lineno)

    assert not offenders, (
        f"{path}: _hpc_post_model() called on line(s) {offenders} before "
        "entering 'with hpc_session(...) as session:' -- same cold-sys.path "
        "bug as a bare YSimulator import at that point."
    )
