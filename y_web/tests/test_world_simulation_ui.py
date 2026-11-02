"""World Simulation section of the admin interface (F5.4): sidebar group, routes, access, texts."""

import json
import re
from pathlib import Path

import pytest
from babel.messages.pofile import read_po
from jinja2 import FileSystemLoader

from y_web.tests.test_federation_service import world  # noqa: F401  (fixture)

Y_WEB = Path(__file__).resolve().parents[1]
TEMPLATES = Y_WEB / "templates"
SIDEBAR_LINKS = {
    "sidebar-world-simulations": "/admin/world_simulation",
    "sidebar-world-simulation-new": "/admin/world_simulation/new",
    "sidebar-world-simulation-analytics": "/admin/world_simulation/analytics",
    "sidebar-world-simulation-schedule": "/admin/world_simulation/schedule",
}


@pytest.fixture
def site(world, monkeypatch):  # noqa: F811
    """The minimal test app plus the World Simulation blueprint, the real templates and four kinds of user."""
    from flask import Blueprint
    from flask_login import current_user
    from werkzeug.security import generate_password_hash

    from y_web import db
    from y_web.routes.admin.sub.world_simulation import world_simulation
    from y_web.src.models import Admin_users, User_mgmt

    app, exps, tmp = world
    app.jinja_loader = FileSystemLoader(str(TEMPLATES))
    from y_web.i18n import init_i18n

    init_i18n(app)  # gettext, html_lang(), text_direction() as in production
    app.jinja_env.filters.setdefault("user_image_id", lambda v: v)
    from flask import url_for as flask_url_for
    from werkzeug.routing import BuildError

    def tolerant_url_for(endpoint, **values):  # the layout links to many pages this test app does not register
        try:
            return flask_url_for(endpoint, **values)
        except BuildError:
            return "/unregistered/" + endpoint

    app.jinja_env.globals["url_for"] = tolerant_url_for
    main = Blueprint("main", __name__)
    main.add_url_rule("/", "index", lambda: "home")
    auth = Blueprint("auth", __name__)
    auth.add_url_rule("/login", "login", lambda: "login")
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.config["WORLD_SIMULATION_MONITOR"] = False  # never start the queue monitor from a test app
    app.register_blueprint(world_simulation)

    @app.context_processor
    def inject():
        from y_web.src.models import Admin_users as A

        role = None
        if current_user.is_authenticated:
            row = db.session.query(A).filter_by(username=current_user.username).first()
            role = row.role if row else None
        return {"current_user_role": role, "extension_sidebar_groups": [], "active_experiments": []}

    for name, role in (("researcher", "researcher"), ("teacher", "teacher"), ("admin", "admin")):
        if not db.session.query(User_mgmt).filter_by(username=name).first():
            db.session.add(User_mgmt(username=name, email=f"{name}@t.com", password=generate_password_hash("x"), joined_on=1))
        if not db.session.query(Admin_users).filter_by(username=name).first():
            db.session.add(Admin_users(username=name, email=f"{name}@t.com", password=generate_password_hash("x"), role=role, last_seen="2026-01-01"))
    db.session.commit()
    return app, exps, tmp


def login(app, name):
    from y_web import db
    from y_web.src.models import User_mgmt

    from flask import g

    g.pop("_login_user", None)  # the test keeps one app context open, flask-login caches the user in it
    client = app.test_client()
    user = db.session.query(User_mgmt).filter_by(username=name).first()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True
    return client


def test_sidebar_group_is_there_for_admin_and_researcher_not_for_teacher(site):
    app, _, _ = site
    for name, expected in (("admin", True), ("researcher", True), ("teacher", False)):
        with app.test_request_context("/"):
            from flask import render_template

            html = render_template("admin/head.html", current_user_role=name)
        assert ('id="sidebar-group-world-simulation"' in html) is expected, name
        if expected:
            assert 'data-group="world-simulation"' in html
            assert 'aria-controls="sidebar-submenu-world-simulation"' in html
            assert 'data-feather="globe"' in html
            for link_id, href in SIDEBAR_LINKS.items():
                assert f'href="{href}"' in html and f'id="{link_id}"' in html


def test_sidebar_block_sits_between_experiments_and_the_plugin_groups():
    text = (TEMPLATES / "admin" / "head.html").read_text()
    experiments = text.index('id="sidebar-group-experiments"')
    world = text.index('id="sidebar-group-world-simulation"')
    plugins = text.index("{% for group in extension_sidebar_groups %}")
    assert experiments < world < plugins
    block = text[world : text.index("{% endif %}", world)]
    assert block.count('class="dashboard-aside-submenu"') == 1 and "federation" not in block.lower()


@pytest.mark.parametrize("path", list(SIDEBAR_LINKS.values()))
def test_every_entry_opens_for_admin_and_researcher(site, path):
    app, _, _ = site
    for name in ("admin", "researcher"):
        assert login(app, name).get(path).status_code == 200, (name, path)


@pytest.mark.parametrize("path", list(SIDEBAR_LINKS.values()) + ["/admin/world_simulation/1", "/admin/world_simulation/1/status.json"])
def test_ordinary_users_are_turned_away(site, path):
    app, _, _ = site
    assert app.test_client().get(path).status_code in (302, 401)  # not logged in
    for name in ("teacher", "testuser"):
        response = login(app, name).get(path)
        assert response.status_code in (302, 403), (name, path)
        assert response.status_code == 403 or "/admin/world_simulation" not in response.headers["Location"]


def _post(client, path, **data):
    return client.post(path, data=data, follow_redirects=False)


def test_create_start_pause_resume_stop_delete_through_the_interface(site, monkeypatch):
    from y_web.src.models.admin import Federation
    from y_web.src.simulation import execution_backend as eb

    app, exps, tmp = site
    calls = []
    for name in ("start", "pause", "resume"):
        monkeypatch.setattr(eb, f"{name}_federation", lambda fed, _n=name, **kw: calls.append(_n) or setattr(fed, "status", {"start": "running", "pause": "paused", "resume": "running"}[_n]))
    monkeypatch.setattr(eb, "stop_federation", lambda fed: calls.append("stop") or setattr(fed, "status", "stopped") or [])
    client = login(app, "admin")
    response = _post(client, "/admin/world_simulation/new", name="W1", experiments=[str(i) for i in exps.values()], seed="5",
                     granularity="slot", attention_enabled="on", opt__attention__temperature="2.0")
    assert response.status_code == 302
    fed = Federation.query.one()
    options = json.loads(fed.config_json)
    assert fed.seed == 5 and options["attention"] == {"enabled": True, "temperature": 2.0}
    assert fed.owner == "admin"
    detail = client.get(response.headers["Location"])
    assert detail.status_code == 200 and "W1" in detail.get_data(as_text=True)
    for action in ("start", "pause", "resume", "stop"):
        assert _post(client, f"/admin/world_simulation/{fed.id}/{action}").status_code == 302
    assert calls == ["start", "pause", "resume", "stop"]
    assert _post(client, f"/admin/world_simulation/{fed.id}/delete").status_code == 302
    assert Federation.query.count() == 0


def test_invalid_creation_shows_the_error_and_creates_nothing(site):
    from y_web.src.models.admin import Federation

    app, exps, tmp = site
    client = login(app, "admin")
    response = client.post("/admin/world_simulation/new", data={"name": "W", "experiments": [str(list(exps.values())[0])]})
    assert response.status_code == 200 and "2 to 5 experiments" in response.get_data(as_text=True)
    assert Federation.query.count() == 0
    bad = client.post("/admin/world_simulation/new", data={"name": "W", "experiments": [str(i) for i in exps.values()], "opt__attention__temperature": "nope"})
    assert "Temperature must be a number" in bad.get_data(as_text=True) and Federation.query.count() == 0


def test_a_researcher_sees_only_their_own_simulations(site):
    from y_web import db
    from y_web.src import federation  # noqa: F401
    from y_web.src.federation import service

    app, exps, tmp = site
    fed = service.create_federation("admin's", list(exps.values()), owner="admin")
    assert "admin&#39;s" in login(app, "admin").get("/admin/world_simulation").get_data(as_text=True)
    researcher = login(app, "researcher")
    assert "admin&#39;s" not in researcher.get("/admin/world_simulation").get_data(as_text=True)
    assert researcher.get(f"/admin/world_simulation/{fed.id}").status_code == 404
    assert researcher.get(f"/admin/world_simulation/{fed.id}/status.json").status_code == 404


def test_parameters_are_editable_only_when_stopped(site):
    from y_web.src.federation import service

    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin", seed=1)
    client = login(app, "admin")
    assert _post(client, f"/admin/world_simulation/{fed.id}/configuration", seed="9", granularity="day", attention_enabled="on", leave_enabled="on").status_code == 302
    assert fed.seed == 9 and fed.granularity == "day" and json.loads(fed.config_json)["leave"] == {"enabled": True} and json.loads(fed.config_json)["attention"] == {"enabled": True}
    assert json.loads(open(f"{fed.folder}/federation.json").read())["granularity"] == "day"
    fed.status = "running"
    _post(client, f"/admin/world_simulation/{fed.id}/configuration", seed="11")
    assert fed.seed == 9


def test_status_json_reports_members_and_bus(site):
    from y_web.src.federation import service

    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    data = login(app, "admin").get(f"/admin/world_simulation/{fed.id}/status.json").get_json()
    assert data["state"] == "stopped" and not data["coordinator_up"]
    assert {m["member"] for m in data["members"]} == {"microblogging", "forum"}
    assert {k: data["bus"][k] for k in ("messages", "deliveries", "events")} == {"messages": 0, "deliveries": 0, "events": []}
    assert data["crossposts"]["text"] is None and data["crossposts"]["hint"] is None  # no database of the run yet


def test_the_interface_never_says_federation(site):
    from y_web.src.federation import service

    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    client = login(app, "admin")
    for path in ("", "/new", f"/{fed.id}", "/analytics", "/schedule"):
        html = client.get("/admin/world_simulation" + path).get_data(as_text=True)
        visible = re.sub(r"<script.*?</script>|<style.*?</style>|<pre .*?</pre>", "", html, flags=re.S)  # <pre>: the generated file, read only
        visible = re.sub(r"(href|action|src|id|data-[a-z-]+)=\"[^\"]*\"", "", visible)
        assert "federation" not in visible.lower() and "federazione" not in visible.lower(), path
        assert "World Simulation" in html


def test_every_text_has_an_italian_entry_and_the_label_is_the_same():
    catalog = read_po(open(Y_WEB / "translations" / "it" / "LC_MESSAGES" / "messages.po", "rb"))
    italian = {m.id: m.string for m in catalog if m.id and m.string}
    assert italian["World Simulation"] == "World Simulation"  # D-10
    pattern = re.compile(r"""\b_\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""")
    missing = []
    for path in (TEMPLATES / "admin" / "world_simulation").glob("*.html"):
        for m in pattern.finditer(path.read_text()):
            text = (m.group(1) if m.group(1) is not None else m.group(2)).replace("\\'", "'")
            if text not in italian:
                missing.append(text)
    import ast

    for path in (Y_WEB / "routes" / "admin" / "sub" / "world_simulation.py", Y_WEB / "src" / "federation" / "options_schema.py"):
        for node in ast.walk(ast.parse(path.read_text())):  # implicit concatenations are joined by the parser
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("_", "N_") and node.args and isinstance(node.args[0], ast.Constant):
                if node.args[0].value not in italian:
                    missing.append(node.args[0].value)
    assert missing == []
