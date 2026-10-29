"""Human participation in the dating frontend, against a real server core and a real gateway (S8 gate).

Nothing is mocked between the YWeb routes and the dating server: the participant pages read the run database
read-only, and every write travels through the gateway (HTTP, per-run token) to the server's own handlers.
The part that needs a person (playing a whole match scenario in a browser) stays a human gate.
"""

import json
import os
import re
import stat
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.tests.test_im_admin_pages import im_app  # noqa: F401

REPO = Path(__file__).resolve().parents[2] / "external" / "YDating"
TOKEN = "k" * 32

pytestmark = pytest.mark.integration
if not (REPO / "YDating").is_dir():
    pytest.skip("YDating is not installed", allow_module_level=True)

ACCOUNT_FORM = {
    "name_mode": "username",
    "age": "28",
    "gender": "a",
    "seeking": "a",
    "age_min": "18",
    "age_max": "60",
    "max_distance_km": "500",
    "intent": "serious",
    "bio": "I like the sea",
    "interests": "hiking",
    "photo_caption": "me on a boat",
}


class Stack:
    pass


def _user(db, role, name):
    from y_web.src.models import Admin_users

    u = Admin_users(
        username=name,
        email=f"{uuid.uuid4().hex}@x.test",
        password="x",
        last_seen="2026-01-01",
        role=role,
    )
    db.session.add(u)
    db.session.commit()
    return u


def _login(s, user):
    s.current = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        is_anonymous=False,
        id=user.id,
        username=user.username,
        role=user.role,
        telemetry_enabled=0,
        get_id=lambda: str(user.id),
        email="p@x.test",
    )


@pytest.fixture
def stack(im_app, tmp_path, monkeypatch):  # noqa: F811
    from y_web import db
    from y_web.src.models import Exps, User_Experiment

    sys.path.insert(0, str(REPO))
    from YDating.population import generate_population, load_population
    from YDating.utils.init_db import create_database_engine
    from YDating.YGateway import HumanGateway, serve
    from YDating.YServer.classes.models import Base
    from YDating.YServer.server import DatingServerCore

    app, client = im_app
    s = Stack()
    s.app, s.client = app, client
    with app.app_context():
        exp = Exps(
            exp_name="dating play",
            platform_type="dating",
            simulator_type="HPC",
            db_name=f"experiments/{uuid.uuid4().hex}/database_server.db",
            owner="adm",
            exp_descr="d",
            status=1,
            running=1,
            port=5097,
            server="127.0.0.1",
            prompt_language="en",
        )
        db.session.add(exp)
        db.session.commit()
        s.exp_id, s.uid = exp.idexp, exp.db_name.split("/")[1]
        user = _user(db, "user", "part1")
        stranger = _user(db, "user", "stranger")
        db.session.add(User_Experiment(user_id=user.id, exp_id=s.exp_id))
        db.session.commit()
        s.user_id = user.id
        s.user = SimpleNamespace(id=user.id, username=user.username, role=user.role)
        s.stranger = SimpleNamespace(
            id=stranger.id, username=stranger.username, role=stranger.role
        )
    s.folder = tmp_path / "y_web" / "experiments" / s.uid
    s.folder.mkdir(parents=True)
    (s.folder / "server_config.json").write_text(
        json.dumps({"human": {"enabled": True, "max_humans": 5}})
    )
    (s.folder / "ray_ready.temp").write_text("ns")  # the server is up: no offline entry
    db_cfg = {"type": "sqlite", "sqlite": {"filename": "database_server.db"}}
    Base.metadata.create_all(create_database_engine(db_cfg, s.folder))
    s.core = DatingServerCore(
        db_cfg,
        str(s.folder),
        1,
        "t",
        60,
        {
            "simulation": {"num_slots_per_day": 4},
            "matching": {"default_model": "random", "common": {"stack_size": 30}},
            "human": {"enabled": True, "max_humans": 5},
            "lifecycle": {"profile_updates_enabled": True, "pause_enabled": True},
            "logging": {"enable_actor_log": False, "enable_request_log": False},
        },
    )
    s.agents = load_population(
        generate_population(
            {
                "seed": 5,
                "n_agents": 8,
                "age": {"min": 25, "max": 30},
                "city_radius_km": 2,
                "genders": {"a": 1},
                "seeking": {"a": {"a": 1}},
            }
        )
    )
    s.core.register_agents(s.agents)
    s.core.register_client("c1", 0)
    for _ in range(2):  # a couple of rounds, so the run has history
        s.core.get_instruction("c1")
        s.core.submit_actions("c1", [])
    s.gateway = HumanGateway(
        lambda method, *a: getattr(s.core, method)(*a),
        {"burst": 1000, "requests_per_minute": 60000},
    )
    s.http = serve(s.gateway, TOKEN)
    (s.folder / "human_gateway.json").write_text(
        json.dumps(
            {"host": "127.0.0.1", "port": s.http.server_address[1], "pid": os.getpid()}
        )
    )
    (s.folder / "human_gateway.token").write_text(TOKEN)
    _login(s, s.user)
    monkeypatch.setattr("flask_login.utils._get_user", lambda: s.current)
    yield s
    s.http.shutdown()


def _csrf(html):
    return re.search(r'data-csrf="([^"]+)"', html).group(1)


def _form_csrf(html):
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _join(s, **over):
    html = s.client.get(f"/{s.exp_id}/dating/join").data.decode()
    form = {**ACCOUNT_FORM, **over, "csrf_token": _form_csrf(html)}
    return s.client.post(f"/{s.exp_id}/dating/join", data=form)


def _enter(s):
    assert _join(s).status_code == 302
    r = s.client.get(f"/{s.exp_id}/dating")
    assert r.status_code == 200, r.data[:300]
    return r.data.decode()


def _act(s, actions, token=None, **kw):
    token = token or _csrf(s.client.get(f"/{s.exp_id}/dating").data.decode())
    return s.client.post(
        f"/{s.exp_id}/dating/api/act",
        json={"actions": actions},
        headers={"X-CSRF-Token": token},
        **kw,
    )


def _set(s, **settings):
    from y_web import db
    from y_web.src.models import ExpFrontendSettings

    with s.app.app_context():
        row = db.session.get(ExpFrontendSettings, s.exp_id)
        if row is None:
            row = ExpFrontendSettings(exp_id=s.exp_id, settings_json="{}")
            db.session.add(row)
        data = json.loads(row.settings_json or "{}")
        data.update(settings)
        row.settings_json = json.dumps(data)
        db.session.commit()


def _account(s):
    from y_web.src.dating.human import human_account_id

    return human_account_id(s.uid, s.user_id)


def test_the_account_id_is_the_one_the_runtime_derives(stack):
    from YDating.YServer.human_service import human_id_for

    from y_web.src.dating.human import human_account_id, human_key

    s = stack
    assert human_account_id(s.uid, s.user_id) == human_id_for(
        human_key(s.uid, s.user_id)
    )


def test_a_person_without_an_account_is_sent_to_the_entry_form(stack):
    s = stack
    r = s.client.get(f"/{s.exp_id}/dating")
    assert r.status_code == 302 and r.headers["Location"].endswith(
        f"/{s.exp_id}/dating/join"
    )
    form = s.client.get(f"/{s.exp_id}/dating/join")
    assert form.status_code == 200 and b'name="csrf_token"' in form.data


def test_entry_validates_like_an_agent_and_checks_csrf(stack):
    s = stack
    assert (
        s.client.post(
            f"/{s.exp_id}/dating/join", data={**ACCOUNT_FORM, "csrf_token": "no"}
        ).status_code
        == 400
    )
    r = _join(s, age="15")  # under 18: the population schema refuses it
    assert r.status_code == 200 and b"check your profile" in r.data.lower()
    assert _account(s) not in s.core.world.humans
    assert _join(s).status_code == 302
    assert _account(s) in s.core.world.humans
    assert (
        s.client.get(f"/{s.exp_id}/dating/join").status_code == 302
    )  # a second visit goes to the app
    assert len(s.core.world.humans) == 1


def test_the_pseudonym_is_offered_instead_of_the_username(stack):
    s = stack
    assert _join(s, name_mode="pseudonym").status_code == 302
    assert s.core.world.agents[_account(s)].username == f"participant-{s.user_id}"


def test_the_participant_ui_is_fixed_to_the_own_account(stack):
    s = stack
    html = _enter(s)
    assert f"/{s.exp_id}/dating/api/act" in html and "dt-play" in html
    assert "Time travel" not in html and "Researcher overview" not in html
    other = s.client.get(
        f"/{s.exp_id}/dating?vp=overview&acc={s.agents[0].id}"
    ).data.decode()
    assert "You are playing as part1" in other and "Researcher overview" not in other


def test_actions_need_the_csrf_token_and_a_known_type(stack):
    s = stack
    _enter(s)
    assert _act(s, [{"type": "PASS", "payload": {}}], token="wrong").status_code == 400
    r = _act(s, [{"type": "LEAVE", "payload": {}}])
    assert r.status_code == 400
    assert _act(s, [{"type": "BROWSE"}]).status_code == 400
    assert _act(s, []).status_code == 400
    big = [{"type": "SEND_MESSAGE", "payload": {"text": "x" * 20000}}]
    assert _act(s, big).status_code == 400


def test_deck_and_swipe_go_through_the_gateway_for_the_session_account(stack):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from YDating.YServer.classes import models as m

    s = stack
    _enter(s)
    deck = s.client.get(f"/{s.exp_id}/dating/api/deck").get_json()
    assert deck["cards"] and all("hidden" not in c for c in deck["cards"])
    target = deck["cards"][0]["candidate_id"]
    other = s.agents[0].id
    r = _act(
        s,
        [
            {
                "type": "PASS",
                "agent_id": other,
                "payload": {"target_id": target, "agent_id": other},
            }
        ],
    )
    assert r.status_code == 200 and r.get_json()["outcomes"][0]["success"]
    with Session(s.core.engine) as session:
        swipe = session.scalars(select(m.Swipe)).one()
    assert (swipe.swiper_id, swipe.mode) == (_account(s), "human")


def test_a_match_with_an_agent_chat_messages_and_controls(stack):
    s = stack
    _enter(s)
    deck = s.client.get(f"/{s.exp_id}/dating/api/deck").get_json()
    target = deck["cards"][0]["candidate_id"]
    s.core.world.record_swipe(
        target, _account(s), "LIKE", 0
    )  # the agent liked the person
    out = _act(s, [{"type": "LIKE", "payload": {"target_id": target}}]).get_json()
    assert len(out["outcomes"][0]["new_ids"]) == 2
    match_id = out["outcomes"][0]["new_ids"][1]
    chat = s.client.get(f"/{s.exp_id}/dating/chat/{match_id}").data.decode()
    assert (
        "dt-chat-tools" in chat
        and 'data-act="SEND_MESSAGE"' in chat
        and 'data-act="REPORT"' in chat
    )
    sent = _act(
        s,
        [{"type": "SEND_MESSAGE", "payload": {"match_id": match_id, "text": "Ciao!"}}],
    )
    assert sent.get_json()["outcomes"][0]["success"]
    assert "Ciao!" in s.client.get(f"/{s.exp_id}/dating/chat/{match_id}").data.decode()
    profile = s.client.get(f"/{s.exp_id}/dating/profile/{target}").data.decode()
    assert 'data-act="BLOCK"' in profile and 'data-act="REPORT"' in profile
    blocked = _act(s, [{"type": "BLOCK", "payload": {"target_id": target}}])
    assert blocked.get_json()["outcomes"][0]["success"]


def test_a_chat_of_other_accounts_is_not_readable(stack):
    s = stack
    _enter(s)
    a, b = s.agents[0].id, s.agents[1].id
    s.core.world.record_swipe(a, b, "LIKE", 0)
    s.core.world.record_swipe(b, a, "LIKE", 0)
    from YDating.YClient.classes.ray_models import ActionDTO

    s.core.dating.browse([a, b], s.core.day, s.core.slot, s.core.current_round_id)
    res = s.core.apply_actions("c1", [ActionDTO(a, "LIKE", {"target_id": b})])
    mid = next(iter(s.core.world.conv), None)
    assert res["outcomes"] and (
        mid is None or s.client.get(f"/{s.exp_id}/dating/chat/{mid}").status_code == 404
    )


def test_server_switches_answer_403_whatever_the_page_does(stack):
    s = stack
    _enter(s)
    s.core.humans.interactions["messages"] = False
    r = _act(s, [{"type": "SEND_MESSAGE", "payload": {"match_id": "m", "text": "x"}}])
    assert r.status_code == 403
    s.core.humans.interactions["swipe"] = False
    assert s.client.get(f"/{s.exp_id}/dating/api/deck").status_code == 403


def test_the_server_refuses_a_text_over_the_limit(stack):
    s = stack
    _enter(s)
    s.core.humans.limits["max_text_chars"] = 10
    r = _act(s, [{"type": "UPDATE_PROFILE", "payload": {"bio": "y" * 11}}])
    assert r.status_code == 413


def test_someone_not_assigned_cannot_play_or_read_the_participant_api(stack):
    s = stack
    _login(s, s.stranger)
    assert s.client.get(f"/{s.exp_id}/dating/api/deck").status_code == 403
    assert s.client.get(f"/{s.exp_id}/dating/join").status_code == 403
    assert (
        s.client.post(f"/{s.exp_id}/dating/api/act", json={"actions": []}).status_code
        == 403
    )
    assert (
        s.client.get(f"/{s.exp_id}/dating").status_code == 200
    )  # the public observer view


def test_participant_mode_can_be_switched_off(stack):
    s = stack
    _set(s, dating_participant_mode_enabled=False)
    assert s.client.get(f"/{s.exp_id}/dating/api/deck").status_code == 403
    assert s.client.get(f"/{s.exp_id}/dating").status_code == 200  # observer only


def test_the_notice_is_shown_once_before_the_first_entry(stack):
    s = stack
    _enter(s)
    _set(s, dating_participant_notice="Please read this first.")
    r = s.client.get(f"/{s.exp_id}/dating")
    assert r.status_code == 302 and r.headers["Location"].endswith("/dating/notice")
    page = s.client.get(f"/{s.exp_id}/dating/notice").data.decode()
    assert "Please read this first." in page
    assert (
        s.client.post(
            f"/{s.exp_id}/dating/notice", data={"csrf_token": "no"}
        ).status_code
        == 400
    )
    ok = s.client.post(
        f"/{s.exp_id}/dating/notice", data={"csrf_token": _form_csrf(page)}
    )
    assert ok.status_code == 302
    assert s.client.get(f"/{s.exp_id}/dating").status_code == 200


def test_a_lost_gateway_is_a_503_not_an_error_page(stack):
    s = stack
    _enter(s)
    s.http.shutdown()
    s.http.server_close()
    r = s.client.get(f"/{s.exp_id}/dating/api/deck")
    assert r.status_code == 503 and "connection lost" in r.get_json()["error"]


def test_profile_pause_and_leave(stack):
    s = stack
    _enter(s)
    me = s.client.get(f"/{s.exp_id}/dating/me").data.decode()
    assert 'data-act="UPDATE_PROFILE"' in me and "I like the sea" in me
    assert _act(
        s, [{"type": "UPDATE_PROFILE", "payload": {"bio": "New bio"}}]
    ).get_json()["outcomes"][0]["success"]
    assert _act(s, [{"type": "PAUSE_PROFILE", "payload": {}}]).get_json()["outcomes"][
        0
    ]["success"]
    assert s.core.world.agents[_account(s)].status == "paused"
    token = _csrf(s.client.get(f"/{s.exp_id}/dating").data.decode())
    left = s.client.post(
        f"/{s.exp_id}/dating/api/leave", headers={"X-CSRF-Token": token}
    )
    assert left.status_code == 200 and s.core.world.agents[_account(s)].status == "left"


def test_the_admin_page_lists_the_participants_and_the_gateway(stack, monkeypatch):
    s = stack
    _enter(s)
    admin = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        is_anonymous=False,
        id=999,
        username="adm",
        role="admin",
        telemetry_enabled=0,
        get_id=lambda: "999",
        email="a@x.test",
    )
    monkeypatch.setattr("flask_login.utils._get_user", lambda: admin)
    monkeypatch.setattr(
        sys.modules["y_web.routes.admin.sub.experiments._dating_participants"],
        "check_privileges",
        lambda *_: None,
    )
    r = s.client.get(f"/admin/dating_participants/{s.exp_id}")
    assert r.status_code == 200
    html = r.data.decode()
    assert "part1" in html and "not reproducible" in html and "Running" in html


# ---------------------------------------------------------------------------------- process lifecycle
def _fake_runtime(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "run_gateway.py").write_text(
        "import json, os, sys\n"
        "folder = sys.argv[1]\n"
        "open(os.path.join(folder, 'seen_token'), 'w').write(os.environ.get('YDATING_GATEWAY_TOKEN', ''))\n"
        "json.dump({'host': '127.0.0.1', 'port': 1, 'pid': os.getpid()}, open(os.path.join(folder, 'human_gateway.json'), 'w'))\n"
        "import time; time.sleep(30)\n"
    )
    return str(repo)


def test_the_gateway_starts_with_a_private_token_and_stops(tmp_path):
    from y_web.src.dating import gateway as gw

    folder = tmp_path / "exp"
    folder.mkdir()
    repo = _fake_runtime(tmp_path)
    assert gw.start_gateway(str(folder), repo) is None  # participation is off
    (folder / "server_config.json").write_text(json.dumps({"human": {"enabled": True}}))
    pid = gw.start_gateway(str(folder), repo)
    try:
        assert pid and gw.is_running(str(folder))
        token_file = folder / gw.TOKEN_FILE
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        assert (folder / "seen_token").read_text() == token_file.read_text() and len(
            token_file.read_text()
        ) >= 32
        assert (
            not (folder / "seen_token").read_text()
            in (folder / gw.STATE_FILE).read_text()
        )
    finally:
        assert gw.stop_gateway(str(folder))
    assert not gw.is_running(str(folder)) and not (folder / gw.TOKEN_FILE).exists()


def test_a_gateway_that_does_not_start_never_fails_the_run(tmp_path):
    from y_web.src.dating import gateway as gw

    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / "server_config.json").write_text(json.dumps({"human": {"enabled": True}}))
    assert gw.start_gateway(str(folder), str(tmp_path / "missing")) is None
    assert not (folder / gw.TOKEN_FILE).exists()


def test_the_client_only_talks_to_a_loopback_gateway(tmp_path):
    from y_web.src.dating import gateway as gw

    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / gw.STATE_FILE).write_text(
        json.dumps({"host": "192.168.1.9", "port": 80, "pid": 1})
    )
    (folder / gw.TOKEN_FILE).write_text("t" * 32)
    (folder / "ray_ready.temp").write_text("x")
    with pytest.raises(gw.GatewayUnavailable):
        gw.GatewayClient(str(folder)).state("a")
