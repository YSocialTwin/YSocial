"""Non-regression guard for the decoupling of the simulation platforms (plan, phase F0).

The snapshots in ``y_web/tests/data/platform_baseline`` were taken before any platform code moved out of the
core (see ``y_web/tests/_platform_baseline.py``). Whatever they recorded must still be there after every step;
anything new is allowed.
"""

from pathlib import Path

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
        baseline.without_moved(name, baseline.load_snapshot(name)),
        baseline.collect(name, booted_app),
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
    names = baseline.without_moved("templates", baseline.load_snapshot("templates"))
    for spec in baseline.load_moved()["templates"].values():
        if baseline.repository_templates(
            spec
        ).is_dir():  # moved: it compiles in its repository
            names.append(spec["to"])
    for name in names:
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


@pytest.mark.parametrize("name", sorted(baseline.BUDGETS))
def test_platform_mentions_do_not_grow(name):
    """New code asks the platform registry instead of naming a platform."""
    excess = baseline.budget_excess(
        baseline.load_budget(name), baseline.BUDGETS[name]()
    )
    assert not excess, "\n".join(excess)


def test_budget_flags_only_growth():
    assert baseline.budget_excess({"a.py": 2}, {"a.py": 1}) == []
    assert baseline.budget_excess({"a.py": 2}, {"a.py": 3, "b.py": 1}) == [
        "a.py: 3 mentions, budget 2",
        "b.py: 1 mentions, budget 0",
    ]


def test_renamed_templates_are_in_the_core():
    """A template that stayed in the core under a neutral name (it is shared by several platforms)."""
    core = Path(__file__).resolve().parents[1] / "templates"
    missing = [
        new
        for new in baseline.load_moved().get("renamed_templates", {}).values()
        if not (core / new).is_file()
    ]
    assert not missing, missing


def test_moved_templates_are_in_their_repository():
    """What left the core is where the record says, for every repository that is installed."""
    missing, installed = [], False
    for old, spec in baseline.load_moved()["templates"].items():
        where = baseline.moved_template_in_repository(spec)
        if not baseline.repository_templates(spec).is_dir():
            continue  # this repository is not installed
        installed = True
        if not where.exists():
            missing.append(f"{old} -> {spec['to']}")
    if not installed:
        pytest.skip("the repositories of the platforms are not installed")
    assert not missing, "moved templates not found in their repository:\n" + "\n".join(
        missing
    )
