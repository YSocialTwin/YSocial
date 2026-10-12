"""C5 - generic ``experiment_access_guard`` hook in ``setup_experiment_context`` (E4).
Exercised with a fake plugin."""

from flask import jsonify

from y_web.tests.test_training_modules_baseline_auth import (  # noqa: F401
    _make_admin_user,
    _make_experiment,
    core_app,
)
from y_web.tests.test_training_modules_manifest_keys import _make_plugin

HOOKS = """
CALLS = []

def guard(account_id, exp_id):
    CALLS.append((account_id, exp_id))
    return "/training/blocked" if exp_id == 999 else None

def external_guard(account_id, exp_id):
    return "https://evil.example/x"

def raising_guard(account_id, exp_id):
    raise RuntimeError("guard crashed")
"""


def _install_guard(tmp_path, monkeypatch, name="guard"):
    repo = _make_plugin(
        tmp_path,
        monkeypatch,
        {"hooks": {"experiment_access_guard": f"pkg.hooks:{name}"}},
    )
    (repo / "pkg" / "hooks.py").write_text(HOOKS)


def _app_with_probe(core_app):
    @core_app.get("/<int:exp_id>/_tm_probe")
    def _probe(exp_id):
        return jsonify(exp_id=exp_id, ok=True)

    @core_app.get("/_tm_noexp")
    def _noexp():
        return jsonify(ok=True)

    return core_app


def _participant_client(app, account_id=5):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["platform_account_id"] = account_id
    return client


def test_guard_can_redirect_participant_sessions(core_app, tmp_path, monkeypatch):
    app = _app_with_probe(core_app)
    _install_guard(tmp_path, monkeypatch)
    client = _participant_client(app)
    denied = client.get("/999/_tm_probe")
    assert denied.status_code == 302 and denied.headers["Location"].endswith(
        "/training/blocked"
    )
    allowed = client.get("/7/_tm_probe")
    assert allowed.status_code == 200 and allowed.get_json()["exp_id"] == 7


def test_guard_receives_account_and_experiment_ids(core_app, tmp_path, monkeypatch):
    import sys

    app = _app_with_probe(core_app)
    _install_guard(tmp_path, monkeypatch)
    _participant_client(app, 42).get("/3/_tm_probe")
    hooks = [
        m
        for n, m in sys.modules.items()
        if n.endswith("pkg.hooks") and "fake_suite" in n
    ]
    assert (42, 3) in hooks[-1].CALLS


def test_guard_ignores_sessions_without_platform_account_id(
    core_app, tmp_path, monkeypatch
):
    app = _app_with_probe(core_app)
    _install_guard(tmp_path, monkeypatch)
    resp = app.test_client().get("/999/_tm_probe")  # anonymous / staff-like session
    assert resp.status_code == 200


def test_guard_ignores_requests_without_exp_id(core_app, tmp_path, monkeypatch):
    app = _app_with_probe(core_app)
    _install_guard(tmp_path, monkeypatch)
    assert _participant_client(app).get("/_tm_noexp").status_code == 200


def test_raising_or_non_local_guard_does_not_block(core_app, tmp_path, monkeypatch):
    app = _app_with_probe(core_app)
    for name in ("raising_guard", "external_guard"):
        (tmp_path / name).mkdir()
        _install_guard(tmp_path / name, monkeypatch, name)
        assert _participant_client(app).get("/999/_tm_probe").status_code == 200


def test_no_guard_registered_leaves_requests_unchanged(core_app):
    app = _app_with_probe(core_app)
    assert _participant_client(app).get("/999/_tm_probe").status_code == 200


def test_guard_runs_after_db_binding_is_set(core_app, tmp_path, monkeypatch):
    """The guard is invoked with the experiment bound (g.current_exp_id set)."""
    app = _app_with_probe(core_app)
    seen = {}
    from flask import g

    import y_web.src.external_runtime.plugin_hooks as ph

    def fake_call(name, account_id, exp_id):
        seen["exp"] = getattr(g, "current_exp_id", None)
        return None

    monkeypatch.setattr(ph, "call_first_non_null", fake_call)
    _participant_client(app).get("/12/_tm_probe")
    assert seen["exp"] == 12
