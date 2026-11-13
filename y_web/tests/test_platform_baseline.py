"""Non-regression guard for the decoupling of the simulation platforms (plan, phase F0).

The snapshots in ``y_web/tests/data/platform_baseline`` were taken before any platform code moved out of the
core (see ``y_web/tests/_platform_baseline.py``). Whatever they recorded must still be there after every step;
anything new is allowed.
"""

import pytest

from y_web.tests import _platform_baseline as baseline


@pytest.fixture(scope="module")
def booted_app():
    from y_web import create_app

    return create_app(db_type="sqlite")


@pytest.mark.parametrize("name", baseline.SNAPSHOT_NAMES)
def test_the_snapshot_exists_and_is_not_empty(name):
    assert baseline.load_snapshot(name), f"{name}.json is empty"


@pytest.mark.parametrize("name", baseline.SNAPSHOT_NAMES)
def test_nothing_recorded_in_the_baseline_was_lost(name, booted_app):
    problems = baseline.lost_or_changed(
        baseline.load_snapshot(name), baseline.collect(name, booted_app)
    )
    shown = "\n".join(problems[:25])
    assert not problems, (
        f"{len(problems)} difference(s) from the {name} baseline:\n{shown}\n"
        "If the change is intended, regenerate with: "
        "python -m y_web.tests._platform_baseline --update"
    )


def test_every_core_template_still_compiles(booted_app):
    """A moved or renamed template, or a missing macro, breaks the page that includes it."""
    failures = []
    for name in baseline.load_snapshot("templates"):
        try:
            booted_app.jinja_env.get_template(name)
        except Exception as exc:  # TemplateNotFound, TemplateSyntaxError, ...
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, "\n".join(failures[:25])


def test_lost_or_changed_reports_removed_and_changed_entries():
    old = {"a": {"x": 1, "y": [1, 2]}, "b": 2}
    assert baseline.lost_or_changed(old, {"a": {"x": 1, "y": [2, 1, 3]}, "b": 2}) == []
    assert baseline.lost_or_changed(old, {"a": {"x": 5, "y": [1]}}) == [
        "/a/x: 1 -> 5",
        "/a/y: 2 removed",
        "/b: removed",
    ]


def test_platform_branches_do_not_grow():
    """New code asks the platform registry instead of comparing ``platform_type`` with a platform name."""
    excess = baseline.branch_budget_excess(
        baseline.json.loads(baseline.BRANCHES_FILE.read_text("utf-8")),
        baseline.collect_platform_branches(),
    )
    assert not excess, "\n".join(excess)


def test_branch_budget_flags_only_growth():
    assert baseline.branch_budget_excess({"a.py": 2}, {"a.py": 1}) == []
    assert baseline.branch_budget_excess({"a.py": 2}, {"a.py": 3, "b.py": 1}) == [
        "a.py: 3 platform branches, budget 2",
        "b.py: 1 platform branches, budget 0",
    ]
