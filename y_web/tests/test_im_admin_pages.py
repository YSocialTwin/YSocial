"""The admin pages of an IM experiment render without errors in the real application (plan, Phase 6)."""

import uuid

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def im_app(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from y_web import create_app, db
    from y_web.src.models import Admin_users

    monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path))
    app = create_app(db_type="sqlite")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        admin = db.session.query(Admin_users).filter_by(role="admin").first()
        if admin is None:
            admin = Admin_users(
                username="adm", email=f"{uuid.uuid4().hex}@x.test", password="x",
                last_seen="2026-01-01", role="admin",
            )
            db.session.add(admin)
            db.session.commit()
        user = SimpleNamespace(
            is_authenticated=True, is_active=True, is_anonymous=False, id=admin.id,
            username=admin.username, role="admin", telemetry_enabled=0, get_id=lambda: str(admin.id),
            email=admin.email,
        )
    # the login loader reads a per-experiment table that the shipped dummy database lacks (pre-existing)
    monkeypatch.setattr("flask_login.utils._get_user", lambda: user)
    monkeypatch.setattr("y_web.src.system.miscellanea.check_privileges", lambda *a, **k: None)
    return app, app.test_client()


def _make_im_experiment(app):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        exp = Exps(
            exp_name="im pages", platform_type="instant_messaging", simulator_type="HPC",
            db_name=f"experiments/{uuid.uuid4().hex}/database_server.db", owner="adm",
            exp_descr="d", status=0, port=5099, server="127.0.0.1", prompt_language="en",
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/admin/dashboard", 200),
        ("/admin/experiments", 200),
        ("/admin/experiment_details/{id}", 200),
        ("/admin/clients_im/{id}", 200),
        ("/admin/clients/{id}", 302),
    ],
)
def test_pages_render_for_an_im_experiment(im_app, monkeypatch, path, expected):
    monkeypatch.setattr(
        "y_web.routes.admin.sub.clients._im._experiment_configuration_update_required",
        lambda exp: False,
    )
    app, client = im_app
    exp_id = _make_im_experiment(app)
    response = client.get(path.format(id=exp_id))
    assert response.status_code == expected, response.data[:800]
    if expected == 302:
        assert "clients_im" in response.headers["Location"]
    else:
        assert b"Traceback" not in response.data


def test_im_details_page_has_analytics_and_the_same_configuration_toggles(im_app):
    from y_web import db
    from y_web.src.models import Exps

    app, client = im_app
    im_id = _make_im_experiment(app)
    with app.app_context():
        other = Exps(
            exp_name="mb", platform_type="microblogging", simulator_type="HPC",
            db_name=f"experiments/{uuid.uuid4().hex}/database_server.db", owner="adm",
            exp_descr="d", status=0, port=5098, server="127.0.0.1", prompt_language="en",
        )
        db.session.add(other)
        db.session.commit()
        other_id = other.idexp
    im_page = client.get(f"/admin/experiment_details/{im_id}").data.decode()
    mb_page = client.get(f"/admin/experiment_details/{other_id}").data.decode()
    # the same configuration box as the other platforms, with the switches IM implements
    assert "update_experiment_config" in im_page
    for name in ("opinion_dynamics_enabled", "stress_reward_enabled", "toxicity_annotation", "sentiment_annotation"):
        assert f'name="{name}"' in im_page, name
    assert "analytics-pages-section" in im_page and "Refresh analytics data" in im_page
    assert "have not been built yet" in im_page  # no run yet
    assert "Instant Messaging" in im_page
    assert "analytics-pages-section" in mb_page and "update_experiment_config" in mb_page


def test_failed_client_shows_the_reason_from_its_execution_log(im_app, monkeypatch, tmp_path):
    import json

    from y_web import db
    from y_web.src.models import Client, Client_Execution, Exps

    for module in ("server", "client"):
        monkeypatch.setattr(f"y_web.src.hpc.{module}.get_writable_path", lambda *a: str(tmp_path))
    app, client = im_app
    exp_id = _make_im_experiment(app)
    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        folder = tmp_path / "y_web" / "experiments" / exp.db_name.split("/")[1]
        (folder / "logs").mkdir(parents=True)
        (folder / "logs" / "uid:cl_execution.log").write_text(
            json.dumps({"level": "ERROR", "error_type": "TooManyLLMFailuresError",
                        "error_message": "7 of 8 sessions failed", "exit_code": 5}) + "\n"
        )
        cl = Client(name="cl", descr="", id_exp=exp_id, population_id=1, days=1, status=0)
        db.session.add(cl)
        db.session.commit()
        db.session.add(Client_Execution(client_id=cl.id, terminal_state="failed", expected_duration_rounds=24))
        db.session.commit()
    page = client.get(f"/admin/experiment_details/{exp_id}").data.decode()
    assert "language-model sessions failed" in page and "7 of 8 sessions failed" in page


def test_export_panel_lists_files_serves_them_and_runs_the_export(im_app, monkeypatch, tmp_path):
    from y_web import db
    from y_web.routes.admin.sub.experiments import _im_exports
    from y_web.src.models import Exps

    app, client = im_app
    exp_id = _make_im_experiment(app)
    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        folder = tmp_path / "y_web" / "experiments" / exp.db_name.split("/")[1]
        (folder / "exports").mkdir(parents=True)
        (folder / "reports").mkdir()
        (folder / "exports" / "messages.csv").write_text("id\n1\n")
        (folder / "reports" / "activity_report.json").write_text("{}")
        (tmp_path / "secret.txt").write_text("no")

    page = client.get(f"/admin/experiment_details/{exp_id}").data.decode()
    assert "im-export-section" in page and "messages.csv" in page and "activity_report.json" in page

    ok = client.get(f"/admin/im_artifact/{exp_id}/exports/messages.csv")
    assert ok.status_code == 200 and ok.data == b"id\n1\n"
    for bad in ("exports/../../secret.txt", "other/messages.csv", "exports/missing.csv"):
        kind, _, name = bad.partition("/")
        assert client.get(f"/admin/im_artifact/{exp_id}/{kind}/{name}").status_code == 302

    calls = []

    def fake_export(folder, fmt="csv", no_text=False, snapshot=False, repo_dir=None):
        calls.append((fmt, no_text, snapshot))
        return True, {}

    monkeypatch.setattr(_im_exports, "run_export", fake_export)
    assert client.post(f"/admin/im_export/{exp_id}", data={"format": "csv", "no_text": "1"}).status_code == 302
    assert client.post(f"/admin/im_export/{exp_id}", data={"format": "xml"}).status_code == 302
    assert calls == [("csv", True, False)]


def test_run_export_reports_failures_and_resolve_artifact_stays_inside(tmp_path):
    from y_web.src.im.analysis import resolve_artifact, run_export

    ok, result = run_export(str(tmp_path), "xml")
    assert not ok and "unknown export format" in result["error"]
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "a.csv").write_text("x")
    assert resolve_artifact(str(tmp_path), "exports", "a.csv")
    assert resolve_artifact(str(tmp_path), "exports", "../a.csv") is None
    assert resolve_artifact(str(tmp_path), "db", "a.csv") is None


def test_analytics_pages_without_data_show_the_normal_unavailable_state(im_app):
    app, client = im_app
    im_id = _make_im_experiment(app)
    for path in ("topic_evolution", "network_analysis", "opinion_evolution", "toxicity_evolution", "recsys_evolution"):
        r = client.get(f"/admin/{path}/{im_id}")
        assert r.status_code == 302, path  # flash + redirect, never a 500
    for path in ("topic_evolution_data", "toxicity_evolution_data"):
        assert client.get(f"/admin/{path}/{im_id}").status_code in (400, 404)
    # the dashboard labels the platform
    assert "Instant Messaging" in client.get("/admin/dashboard").data.decode()
