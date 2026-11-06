"""Creating a forum experiment on YForum (HPC) from the new-experiment form (plan F12)."""

import importlib
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

YFORUM = Path(__file__).resolve().parents[2] / "external" / "YForum"


def _crud():
    # the package attribute of the same name is the blueprint: take the module itself
    return importlib.import_module("y_web.routes.admin.sub.experiments._crud")


def _availability(monkeypatch, **flags):
    """Pin the repository availability (other test modules replace the function without restoring it)."""
    availability = {
        "microblogging": False,
        "hpc": False,
        "forum": False,
        "forum_hpc": False,
        "photo_sharing": False,
        "instant_messaging": False,
        "dating": False,
        **flags,
    }
    monkeypatch.setattr(_crud(), "_external_repo_availability", lambda: availability)


def _app_and_client(monkeypatch, tmp_path):
    from y_web import create_app, db
    from y_web.src.models import Admin_users

    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path)
    )
    app = create_app(db_type="sqlite")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        admin = Admin_users(
            username="admc",
            email=f"{uuid.uuid4().hex}@x.test",
            password="x",
            last_seen="2026-01-01",
            role="admin",
        )
        db.session.add(admin)
        db.session.commit()
        ident = (admin.id, admin.username, admin.email)
    user = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        is_anonymous=False,
        id=ident[0],
        username=ident[1],
        role="admin",
        telemetry_enabled=0,
        get_id=lambda: str(ident[0]),
        email=ident[2],
    )
    monkeypatch.setattr("flask_login.utils._get_user", lambda: user)
    monkeypatch.setattr(
        "y_web.src.system.miscellanea.check_privileges", lambda *a, **k: None
    )
    return app, app.test_client()


FORM = {
    "exp_name": "forum on yforum",
    "exp_descr": "d",
    "platform_type": "forum",
    "simulator_type": "HPC",
    "llm_agents_enabled": "true",
    "sentiment_annotation": "true",
    "emotion_annotation": "true",
    "opinion_annotation": "true",
    "tags": "politics,sport",
}


@pytest.mark.integration
def test_a_forum_hpc_experiment_is_created_on_yforum(monkeypatch, tmp_path):
    if not (YFORUM / "YForum" / "config_validation.py").exists():
        pytest.skip("external/YForum is not checked out")
    pytest.importorskip("jsonschema")
    from y_web import db
    from y_web.src.models import Exps

    sys.path.insert(0, str(YFORUM))
    try:
        from YForum.config_validation import validate
    finally:
        sys.path.remove(str(YFORUM))

    _availability(monkeypatch, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)

    response = http.post("/admin/create_experiment", data=FORM)
    assert response.status_code == 302 and "/admin/experiment_details/" in (
        response.headers["Location"]
    )

    with app.app_context():
        exp = db.session.query(Exps).filter_by(exp_name="forum on yforum").one()
        assert exp.platform_type == "forum" and exp.simulator_type == "HPC"
        assert exp.db_name.endswith(
            "database_server.db"
        )  # SQLite, created by YForum at the first start
        folder = tmp_path / "y_web" / "experiments" / exp.db_name.split("/")[1]
        for switch in ("sentiment", "emotion", "opinions"):
            assert switch in exp.annotations

    assert not (
        folder / "database_server.db"
    ).exists()  # no clean YSocial database copied
    assert not (
        folder / "config_server.json"
    ).exists()  # the Flask file name is not used
    config = validate(
        json.loads((folder / "server_config.json").read_text()), "config/server_config"
    )
    assert config["platform_type"] == "forum"
    assert config["sentiment_annotation"] and config["emotion_annotation"]
    assert config["opinion_dynamics_enabled"] is True
    assert config["topics"] == ["politics", "sport"]
    assert config["experiment_configuration_confirmed"] is False
    assert config["database"]["type"] == "sqlite"
    assert config["federation"]["enabled"] is False  # opt-in


@pytest.mark.integration
def test_a_forum_hpc_experiment_needs_yforum(monkeypatch, tmp_path):
    from y_web import db
    from y_web.src.models import Exps

    _availability(monkeypatch, forum_hpc=False)
    app, http = _app_and_client(monkeypatch, tmp_path)

    response = http.post("/admin/create_experiment", data=FORM)
    assert response.status_code == 302
    assert "/admin/experiment_details/" not in response.headers["Location"]
    with app.app_context():
        assert db.session.query(Exps).filter_by(exp_name="forum on yforum").count() == 0


@pytest.mark.integration
def test_the_standard_forum_is_not_changed(monkeypatch, tmp_path):
    """Without the HPC switch the forum still goes to the Flask pair (and keeps its forced-off switches)."""
    from y_web import db
    from y_web.src.models import Exps

    _availability(monkeypatch, forum=True, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)

    response = http.post(
        "/admin/create_experiment", data={**FORM, "simulator_type": "Standard"}
    )
    assert response.status_code == 302
    with app.app_context():
        exp = db.session.query(Exps).filter_by(exp_name="forum on yforum").one()
        assert exp.simulator_type == "Standard"
        assert "sentiment" not in (exp.annotations or "")
        folder = tmp_path / "y_web" / "experiments" / exp.db_name.split("/")[1]
    assert (folder / "config_server.json").exists()
    assert not (folder / "server_config.json").exists()


def test_yforum_is_installed_when_both_entry_points_exist(monkeypatch, tmp_path):
    from y_web.src.forum import forum_hpc_installed

    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_external_repo_dir", lambda name: str(tmp_path)
    )
    assert forum_hpc_installed() is False
    (tmp_path / "run_server.py").write_text("")
    assert forum_hpc_installed() is False
    (tmp_path / "run_client.py").write_text("")
    assert forum_hpc_installed() is True
