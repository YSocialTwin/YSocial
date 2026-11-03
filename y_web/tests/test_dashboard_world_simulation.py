"""World Simulation box of the admin home page: the first block of the page, one card per World Simulation, live through a polling
endpoint; the member experiments are not in the standard experiment boxes; nothing of it without the YFederation plugin.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import availability  # noqa: E402
from y_web.src.federation import coordinator_process as cp  # noqa: E402
from y_web.src.federation import frontends
from y_web.src.federation import member_health as mh  # noqa: E402
from y_web.src.federation import service
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_ui import (  # noqa: E402,F401  (fixtures and helper)
    _post,
    login,
    site,
)

Y_WEB = Path(__file__).resolve().parents[1]
TEMPLATE = (Y_WEB / "templates/admin/dashboard.html").read_text(encoding="utf-8")
CARD = (Y_WEB / "templates/admin/world_simulation/_dashboard_card.html").read_text(
    encoding="utf-8"
)
JS = (Y_WEB / "static/assets/js/admin-dashboard-world-simulation.js").read_text(
    encoding="utf-8"
)
BOX_MARKERS = (
    "section-world-simulation",
    "box-world-simulations",
    "ws-dash-card",
    "admin-dashboard-world-simulation.js",
)


@pytest.fixture
def dash(site, monkeypatch):  # noqa: F811
    """The test site plus the dashboard blueprint (its slow collaborators replaced) and a standalone experiment."""
    from y_web import db
    from y_web.routes.admin import dashboard as dash_mod
    from y_web.src.models.admin import Exps

    app, exps, tmp = site
    if "admin" not in app.blueprints:
        app.register_blueprint(dash_mod.admin)
    monkeypatch.setattr(
        dash_mod, "llm_backend_status", lambda: {"backend": None, "status": False}
    )
    monkeypatch.setattr(dash_mod, "get_llm_models", lambda *a, **k: [])
    monkeypatch.setattr(dash_mod, "check_connection", lambda: True)
    monkeypatch.setattr(dash_mod, "get_db_type", lambda: "sqlite")
    monkeypatch.setattr(dash_mod, "get_db_port", lambda: "")
    monkeypatch.setattr(dash_mod, "get_db_server", lambda: "")
    monkeypatch.setattr(dash_mod, "_dashboard_news", lambda limit=4: [])
    monkeypatch.setattr(
        dash_mod, "get_jupyter_instances", lambda *a, **k: [], raising=False
    )
    monkeypatch.setattr(availability, "sdk_available", lambda refresh=False: True)
    names = {"microblogging": "Alpha net", "forum": "Beta board"}
    for platform, eid in exps.items():
        db.session.get(Exps, eid).exp_name = names[platform]
    solo = Exps(
        platform_type="microblogging",
        exp_name="Solo exp",
        db_name="experiments/solo/db.db",
        owner="admin",
        exp_descr="",
        status=0,
        running=0,
        port=5001,
        simulator_type="Standard",
        exp_status="stopped",
    )
    db.session.add(solo)
    db.session.commit()
    return app, exps, solo.idexp


def home(app, name="admin"):
    return login(app, name).get("/admin/dashboard")


def html_of(app, name="admin"):
    r = home(app, name)
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def make_world(exps, name="Big world", owner="admin"):
    return service.create_federation(name, list(exps.values()), owner=owner)


def standard_area(html):
    """The part of the page with the standard experiment boxes (after the World Simulation box)."""
    return html[
        html.index('id="section-simulations"') : html.index("end Simulations section")
    ]


# ------------------------------------------------------------------------------------------------- rendering
def test_no_world_simulation_renders_nothing(dash):
    app, exps, solo = dash
    html = html_of(app)
    assert not any(m in html for m in BOX_MARKERS)
    assert (
        "Solo exp" in html and "Alpha net" in html
    )  # without a World Simulation every experiment is where it was


def test_one_world_simulation_card_with_name_status_and_members(dash):
    app, exps, solo = dash
    fed = make_world(exps)
    html = html_of(app)
    assert html.count('class="box-content ws-dash-card') == 1
    assert f'id="ws-dash-card-{fed.id}"' in html and "Big world" in html
    assert (
        'data-state="stopped"' in html
        and "ws-state-stopped" in html
        and ">Stopped<" in html
    )
    card = html[
        html.index('id="ws-dash-card-') : html.index("end World Simulation section")
    ]
    # the members are named after their experiment (not their platform type) with the platform icon
    assert "Alpha net" in card and "Beta board" in card
    assert "mdi-message-text-outline" in card and "mdi-forum-outline" in card
    assert f'href="/admin/world_simulation/{fed.id}"' in card  # Details


def test_two_world_simulations_two_cards_active_first(dash):
    from y_web import db
    from y_web.src.models.admin import Exps

    app, exps, solo = dash
    first = make_world(exps, "Zeta world")
    extra = []
    for n in (1, 2):
        e = Exps(
            platform_type="microblogging",
            exp_name=f"X{n}",
            db_name=f"experiments/x{n}/db.db",
            owner="admin",
            exp_descr="",
            status=0,
            running=0,
            port=5100 + n,
            simulator_type="Standard",
            exp_status="stopped",
        )
        db.session.add(e)
        db.session.flush()
        extra.append(e.idexp)
    db.session.commit()
    # a second World Simulation needs members of its own: reuse the rows directly (the box does not validate)
    from y_web.src.models.admin import Federation, FederationMember

    second = Federation(
        name="Alpha world",
        owner="admin",
        status="running",
        folder="",
        config_json="{}",
        federation_id="x",
        seed=1,
        granularity="slot",
    )
    db.session.add(second)
    db.session.flush()
    db.session.add(
        FederationMember(
            federation_pk=second.id,
            exp_id=extra[0],
            member="m1",
            platform_type="microblogging",
            position=0,
        )
    )
    db.session.commit()
    html = html_of(app)
    assert html.count('class="box-content ws-dash-card') == 2
    assert html.index("Alpha world") < html.index(
        "Zeta world"
    )  # the one in progress comes first
    assert first.id != second.id


def test_the_box_is_the_first_block_before_the_experiment_boxes(dash):
    app, exps, solo = dash
    make_world(exps)
    html = html_of(app)
    assert (
        html.index('id="section-world-simulation"')
        < html.index('id="section-simulations"')
        < html.index('id="box-stopped-experiments"')
    )
    # and in the source of the template, inside the main column
    assert (
        TEMPLATE.index("section-world-simulation")
        < TEMPLATE.index("section-simulations")
        < TEMPLATE.index("box-running-experiments")
    )
    assert TEMPLATE.index('<div class="column is-8">') < TEMPLATE.index(
        "section-world-simulation"
    )


# ------------------------------------------------------------------------------------------------- plugin missing
def test_without_the_plugin_the_page_is_that_of_a_site_without_world_simulations(
    dash, monkeypatch
):
    from y_web.src.models.admin import Federation

    app, exps, solo = dash
    fed = make_world(exps)
    monkeypatch.setattr(availability, "sdk_available", lambda refresh=False: False)
    off = html_of(app)
    assert not any(m in off for m in BOX_MARKERS)
    assert (
        "Alpha net" in off and "Beta board" in off
    )  # nothing is hidden: the page is the classic one
    # the same page, byte for byte, as when the experiments belong to no World Simulation
    monkeypatch.setattr(availability, "sdk_available", lambda refresh=False: True)
    service.delete_federation(fed)
    assert Federation.query.count() == 0
    assert html_of(app) == off


def test_polling_endpoint_without_the_plugin_is_empty(dash, monkeypatch):
    app, exps, solo = dash
    make_world(exps)
    monkeypatch.setattr(availability, "sdk_available", lambda refresh=False: False)
    body = login(app, "admin").get("/admin/dashboard/world_simulations").get_json()
    assert body == {"available": False, "cards": []}


# ------------------------------------------------------------------------------------------------- members out of the standard boxes
@pytest.mark.parametrize(
    "fed_state", ["stopped", "running", "paused", "failed", "completed"]
)
def test_member_experiments_are_never_in_the_standard_boxes(dash, fed_state):
    from y_web import db
    from y_web.src.models.admin import Exps

    app, exps, solo = dash
    fed = make_world(exps)
    fed.status = fed_state
    for (
        eid
    ) in (
        exps.values()
    ):  # a member running or completed on its own state is hidden as well
        db.session.get(Exps, eid).exp_status = (
            "active" if fed_state == "running" else "stopped"
        )
        db.session.get(Exps, eid).running = 1 if fed_state == "running" else 0
    db.session.commit()
    html = html_of(app)
    area = standard_area(html)
    assert "Solo exp" in area
    assert "Alpha net" not in area and "Beta board" not in area
    assert "Alpha net" in html  # ... but it is in the card
    assert (
        "box-running-experiments" not in area
    )  # nothing else is running: no empty box
    assert "totalStopped: 1" in html and "totalRunning: 0" in html


def test_counters_and_json_lists_leave_the_members_out(dash):
    app, exps, solo = dash
    make_world(exps)
    client = login(app, "admin")
    body = client.get("/admin/dashboard/experiments/stopped").get_json()
    assert [e["exp_name"] for e in body["experiments"]] == ["Solo exp"] and body[
        "total"
    ] == 1
    assert client.get("/admin/dashboard/experiments/running").get_json()["total"] == 0
    assert client.get("/admin/dashboard/status").get_json() == {
        "running": 0,
        "completed": 0,
        "stopped": 1,
    }


def test_when_every_experiment_is_a_member_the_standard_area_still_renders(dash):
    from y_web import db
    from y_web.src.models.admin import Exps

    app, exps, solo = dash
    db.session.delete(db.session.get(Exps, solo))
    db.session.commit()
    make_world(exps)
    html = html_of(app)
    assert (
        "ws-dash-card" in html
        and "box-stopped-experiments" not in html
        and 'id="section-simulations"' in html
    )


# ------------------------------------------------------------------------------------------------- actions
def card_html(app, **state):
    body = login(app, "admin").get("/admin/dashboard/world_simulations").get_json()
    return body["cards"][0]["html"]


@pytest.mark.parametrize(
    "state,expected,absent",
    [
        (
            "stopped",
            ("command_start",),
            ("command_pause", "command_resume", "command_stop"),
        ),
        ("failed", ("command_start",), ("command_pause", "command_stop")),
        (
            "running",
            ("command_pause", "command_stop"),
            ("command_start", "command_resume"),
        ),
        (
            "paused",
            ("command_resume", "command_stop"),
            ("command_start", "command_pause"),
        ),
        (
            "starting",
            ("command_stop",),
            ("command_start", "command_pause", "command_resume"),
        ),
    ],
)
def test_the_buttons_follow_the_state_and_point_at_the_existing_routes(
    dash, state, expected, absent
):
    app, exps, solo = dash
    fed = make_world(exps)
    fed.status = state
    from y_web import db

    db.session.commit()
    html = card_html(app)
    base = f"/admin/world_simulation/{fed.id}"
    for name in expected:
        assert f'action="{base}/{name.split("_")[1]}"' in html, name
    for name in absent:
        assert f'action="{base}/{name.split("_")[1]}"' not in html, name
    # the frontends buttons and the link to the detail page are always there
    assert (
        f'action="{base}/frontends/activate"' in html
        and f'action="{base}/frontends/deactivate"' in html
    )
    assert f'href="{base}"' in html
    assert html.count('method="post"') == len(expected) + 2
    assert 'name="next" value="dashboard"' in html


def test_stop_asks_for_confirmation_in_a_data_attribute(dash):
    from y_web import db

    app, exps, solo = dash
    fed = make_world(exps)
    fed.status = "running"
    db.session.commit()
    html = card_html(app)
    stop = re.search(r'<form method="post" action="[^"]*/stop"([^>]*)>', html)
    assert (
        stop
        and 'data-confirm="Stop this World Simulation? Every member experiment stops with it."'
        in stop.group(1)
    )
    assert (
        "onsubmit" not in html
    )  # no inline script: the text is escaped as an attribute and handled by the page script
    assert "data-confirm" in JS and "window.confirm" in JS


def test_commands_from_the_box_come_back_to_the_dashboard(dash, monkeypatch):
    from y_web.src.simulation import execution_backend as eb

    app, exps, solo = dash
    fed = make_world(exps)
    monkeypatch.setattr(
        eb, "start_federation", lambda fed, **kw: setattr(fed, "status", "running")
    )
    monkeypatch.setattr(frontends, "activate_frontends", lambda fed, user: [])
    monkeypatch.setattr(frontends, "deactivate_frontends", lambda fed, user: [])
    client = login(app, "admin")
    base = f"/admin/world_simulation/{fed.id}"
    assert (
        _post(client, base + "/start", next="dashboard")
        .headers["Location"]
        .endswith("/admin/dashboard")
    )
    assert (
        _post(client, base + "/frontends/activate", next="dashboard")
        .headers["Location"]
        .endswith("/admin/dashboard")
    )
    assert (
        _post(client, base + "/frontends/deactivate", next="dashboard")
        .headers["Location"]
        .endswith("/admin/dashboard")
    )
    # without it (the detail page) or with anything else, they go where they always went
    assert (
        _post(client, base + "/frontends/activate")
        .headers["Location"]
        .endswith(f"{base}#execution")
    )
    assert (
        _post(client, base + "/frontends/activate", next="https://evil.example/")
        .headers["Location"]
        .endswith(f"{base}#execution")
    )
    assert (
        _post(client, base + "/pause", next="//evil.example")
        .headers["Location"]
        .endswith(base)
    )


# ------------------------------------------------------------------------------------------------- permissions
def test_researchers_see_only_their_own_world_simulations(dash):
    app, exps, solo = dash
    make_world(exps, "Admin world", owner="admin")
    assert "ws-dash-card" not in html_of(app, "researcher")
    assert (
        login(app, "researcher")
        .get("/admin/dashboard/world_simulations")
        .get_json()["cards"]
        == []
    )
    assert (
        len(
            login(app, "admin")
            .get("/admin/dashboard/world_simulations")
            .get_json()["cards"]
        )
        == 1
    )


def test_a_researcher_sees_the_simulation_they_own(dash):
    from y_web import db

    app, exps, solo = dash
    fed = make_world(exps, "Mine", owner="researcher")
    db.session.commit()
    body = login(app, "researcher").get("/admin/dashboard/world_simulations").get_json()
    assert [c["data"]["name"] for c in body["cards"]] == ["Mine"]
    assert 'class="box-content ws-dash-card' in html_of(
        app, "admin"
    )  # admins see every one
    assert fed.owner == "researcher"


def test_ordinary_users_and_visitors_are_turned_away_from_the_polling_endpoint(dash):
    app, exps, solo = dash
    make_world(exps)
    assert (
        login(app, "teacher").get("/admin/dashboard/world_simulations").status_code
        == 403
    )
    assert app.test_client().get("/admin/dashboard/world_simulations").status_code in (
        302,
        401,
        403,
    )


# ------------------------------------------------------------------------------------------------- live data
def running_world(dash, monkeypatch, tick=49, total=100):
    from y_web import db

    app, exps, solo = dash
    fed = make_world(exps)
    fed.status = "running"
    db.session.commit()
    a, b = [m.member for m, _e in service.members_of(fed)]
    slow = {m.member: e.exp_name for m, e in service.members_of(fed)}[
        b
    ]  # the name of the experiment of the stalled member
    monkeypatch.setattr(
        cp,
        "coordinator_status",
        lambda fed, timeout=3.0: {
            "global_tick": tick,
            "members": {
                a: {"status": "running", "last_ready_tick": tick},
                b: {"status": "running", "last_ready_tick": tick - 3},
            },
        },
    )
    health = {
        "members": {
            a: {"code": "waiting", "problem": False, "waiting_for": [b]},
            b: {
                "code": "stalled",
                "problem": True,
                "waiting_for": [],
                "since": 400,
                "cause": {"kind": "port"},
                "log": "/x/server_stderr.log",
            },
        },
        "problems": [b],
        "progress": mh.progress(tick, total, 12.0),
        "silent": {},
        "stall_after": 120,
        "hello_timeout": 60,
    }
    monkeypatch.setattr(mh, "collect", lambda fed, coordinator, **kw: health)
    return app, fed, a, b, slow


def test_polling_payload_has_progress_problems_and_members(dash, monkeypatch):
    app, fed, a, b, slow = running_world(dash, monkeypatch)
    body = login(app, "admin").get("/admin/dashboard/world_simulations").get_json()
    assert body["available"] is True and len(body["cards"]) == 1
    entry = body["cards"][0]
    data = entry["data"]
    assert (
        entry["id"] == fed.id
        and entry["state"] == "running"
        and entry["active"] is True
    )
    assert data["tick"] == 49 and data["day"] == 2 and data["slot"] == 1
    assert (
        data["progress"]["done"] == 50
        and data["progress"]["total"] == 100
        and data["progress"]["percent"] == 50
    )
    assert (
        data["progress"]["seconds_per_tick"] == 12.0
        and data["progress"]["eta_seconds"] == 600
    )
    assert (
        "Tick 50/100" in data["progress"]["text"] and "ETA" in data["progress"]["text"]
    )
    assert data["coordinator_down"] is False
    assert (
        data["problems_total"] == 1
        and data["problems"][0]["label"] == slow
        and "port" in data["problems"][0]["cause"]
    )
    by_member = {m["member"]: m for m in data["members"]}
    assert (
        by_member[b]["badge"]["code"] == "stalled"
        and by_member[b]["badge"]["problem"] is True
        and by_member[b]["badge"]["class"] == "ws-state-paused"
    )
    assert (
        by_member[a]["badge"]["code"] == "waiting"
        and slow in by_member[a]["badge"]["text"]
    )
    html = entry["html"]
    assert (
        'style="width: 50%;"' in html
        and "Tick 50/100" in html
        and "Day / slot: 2 / 1" in html
    )
    assert (
        "Some members need attention" in html
        and f"/admin/world_simulation/{fed.id}#execution" in html
    )
    assert "ws-dash-banner" in html


def test_coordinator_down_is_a_banner(dash, monkeypatch):
    from y_web import db

    app, exps, solo = dash
    fed = make_world(exps)
    fed.status = "running"
    db.session.commit()
    monkeypatch.setattr(cp, "coordinator_status", lambda fed, timeout=3.0: None)
    monkeypatch.setattr(mh, "collect", lambda fed, coordinator, **kw: {})
    entry = (
        login(app, "admin")
        .get("/admin/dashboard/world_simulations")
        .get_json()["cards"][0]
    )
    assert (
        entry["data"]["coordinator_down"] is True
        and "The coordinator does not answer" in entry["html"]
    )


def test_frontend_state_and_open_link_per_member(dash, monkeypatch):
    from y_web import db
    from y_web.src.models.admin import Exps

    app, exps, solo = dash
    make_world(exps)
    alpha = db.session.get(Exps, exps["microblogging"])
    alpha.status = 1  # the web interface of one member is active
    db.session.commit()
    entry = (
        login(app, "admin")
        .get("/admin/dashboard/world_simulations")
        .get_json()["cards"][0]
    )
    by_name = {m["name"]: m for m in entry["data"]["members"]}
    assert (
        by_name["Alpha net"]["frontend_active"] is True
        and by_name["Alpha net"]["url"] == f"/admin/join_experiment/{alpha.idexp}"
    )
    assert (
        by_name["Beta board"]["frontend_active"] is False
        and by_name["Beta board"]["url"] is None
    )
    assert (
        entry["html"].count("ws-dash-open") == 1
        and f'href="/admin/join_experiment/{alpha.idexp}"' in entry["html"]
    )


def test_a_card_lists_at_most_eight_members_and_counts_the_rest(dash, monkeypatch):
    from y_web.routes.admin.sub.world_simulation import (
        DASHBOARD_MAX_MEMBERS,
        dashboard_card,
    )

    app, exps, solo = dash
    fed = make_world(exps)
    pairs = [
        (
            SimpleNamespace(member=f"m{i}", platform_type="forum"),
            SimpleNamespace(
                exp_name=f"Exp {i}", idexp=1000 + i, status=0, owner="admin"
            ),
        )
        for i in range(11)
    ]
    monkeypatch.setattr(service, "members_of", lambda f: pairs)
    from y_web.src.models import Admin_users

    admin = Admin_users.query.filter_by(username="admin").one()
    with app.test_request_context("/"):
        card = dashboard_card(fed, admin)
    assert (
        DASHBOARD_MAX_MEMBERS == 8
        and len(card["members"]) == 8
        and card["members_more"] == 3
    )
    from flask import render_template

    with app.test_request_context("/"):
        html = render_template("admin/world_simulation/_dashboard_card.html", c=card)
    assert html.count('class="ws-dash-member"') == 8 and "3 more members" in html


def test_queries_for_the_cards_are_bounded(dash, monkeypatch):
    """One query lists the World Simulations: the number of listings does not grow with the polls or with the experiments."""
    from sqlalchemy import event

    from y_web import db

    app, exps, solo = dash
    make_world(exps)
    statements = []
    for engine in db.engines.values():  # the federation tables are in the admin bind
        event.listen(
            engine,
            "before_cursor_execute",
            lambda conn, cur, stmt, *a: statements.append(stmt),
        )
    login(app, "admin").get("/admin/dashboard/world_simulations")
    assert (
        sum(1 for s in statements if re.search(r"FROM federation\b", s, re.I)) == 1
    )  # one listing of the World Simulations


# ------------------------------------------------------------------------------------------------- script and texts
def test_the_script_polls_politely():
    assert (
        "document.hidden" in JS and "visibilitychange" in JS
    )  # nothing requested while the tab is hidden
    assert "busy" in JS  # never two requests at once
    assert re.search(r"activeMs\s*=\s*parseInt\(box\.dataset\.pollActiveMs", JS)
    assert (
        'data-poll-active-ms="5000"' in TEMPLATE
        and 'data-poll-idle-ms="30000"' in TEMPLATE
    )  # 5 s in progress, 30 s otherwise
    assert (
        "fetch(url" in JS and JS.count("fetch(") == 1
    )  # one request for all the cards


def test_the_template_additions_are_all_conditional_on_the_cards():
    # every addition is inside {% if world_simulation_cards %}: without it the page is the one of before
    stripped = re.sub(
        r"\{% if world_simulation_cards %\}.*?\{% endif %\}", "", TEMPLATE, flags=re.S
    )
    assert "world_simulation" not in stripped and "ws-dash" not in stripped


def test_italian_texts():
    import gettext as pygettext

    cat = pygettext.GNUTranslations(
        open(Y_WEB / "translations/it/LC_MESSAGES/messages.mo", "rb")
    )
    for msgid, text in (
        ("Stopping", "In arresto"),
        ("See the details", "Vedi i dettagli"),
        ("%(n)s more members", "altri %(n)s membri"),
        (
            "Experiments that run together on one shared clock. They are listed here and not among the experiments below.",
            "Esperimenti che girano insieme su un unico orologio condiviso. Sono elencati qui e non tra gli esperimenti qui sotto.",
        ),
    ):
        assert cat.gettext(msgid) == text, msgid
    for msgid in re.findall(r"_\('([^']+)'", CARD):
        assert cat.gettext(msgid) != msgid or msgid in (
            "Start",
            "Pause",
            "Open",
            "Details",
        ), msgid  # every text of the card is translated
