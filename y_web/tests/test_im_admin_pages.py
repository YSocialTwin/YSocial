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
