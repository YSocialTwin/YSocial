"""``experiment_page_widget`` hook: a plugin can add HTML to the pages of an experiment, for participants only."""

import sys

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_manifest_keys import _make_plugin

HOOKS = """
CALLS = []

def widget(account_id, exp_id):
    CALLS.append((account_id, exp_id))
    return '<div id="fake-widget">%s-%s</div>' % (account_id, exp_id)

def nothing(account_id, exp_id):
    return None

def raising(account_id, exp_id):
    raise RuntimeError("hook crashed")
"""


def _install(tmp_path, monkeypatch, name="widget"):
    repo = _make_plugin(
        tmp_path,
        monkeypatch,
        {"hooks": {"experiment_page_widget": f"pkg.hooks:{name}"}},
    )
    (repo / "pkg" / "hooks.py").write_text(HOOKS)


def _render(app, exp_id, account=None):
    from flask import render_template_string

    with app.test_request_context("/"):
        from flask import session

        if account is not None:
            session["platform_account_id"] = account
        return render_template_string(
            "[{{ plugin_experiment_widgets(exp_id) }}]", exp_id=exp_id
        )


def test_a_participant_page_gets_the_html_of_the_hook(core_app, tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch)
    assert _render(core_app, 7, account=42) == '[<div id="fake-widget">42-7</div>]'
    assert (
        _render(core_app, "7", account=42) == '[<div id="fake-widget">42-7</div>]'
    )  # the URL value may be text


def test_nobody_but_a_participant_gets_anything(core_app, tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch)
    assert (
        _render(core_app, 7) == "[]"
    )  # an admin or anonymous session has no platform account
    assert _render(core_app, None, account=42) == "[]"


def test_a_hook_that_raises_changes_nothing(core_app, tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "raising")
    assert _render(core_app, 7, account=42) == "[]"


def test_a_hook_that_returns_nothing_changes_nothing(core_app, tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "nothing")
    assert _render(core_app, 7, account=42) == "[]"


def test_without_any_hook_pages_are_unchanged(core_app):
    assert _render(core_app, 7, account=42) == "[]"


def test_the_microblogging_header_calls_it():
    from pathlib import Path

    header = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "microblogging"
        / "header.html"
    ).read_text()
    assert header.rstrip().endswith("{{ plugin_experiment_widgets(exp_id) }}")
