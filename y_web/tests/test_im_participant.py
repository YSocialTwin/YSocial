"""Human participation in the IM frontend, against a real orchestrator and a real gateway (Phase 10 gate).

Nothing is mocked between the YWeb routes and the IM server: the participant pages read the run database
read-only and every write travels through the gateway (HTTP, per-run token) to the server's own handlers.
"""

import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.tests.test_im_admin_pages import _make_im_experiment, im_app  # noqa: F401

IM_REPO = Path(__file__).resolve().parents[2] / "external" / "YInstantMessaging"
TOKEN = "k" * 32

pytestmark = pytest.mark.integration
if not (IM_REPO / "yinstantmessaging").is_dir():
    pytest.skip("YInstantMessaging is not installed", allow_module_level=True)


def _im_helpers():
    spec = importlib.util.spec_from_file_location("im_test_helpers", IM_REPO / "tests" / "helpers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Stack:
    pass


@pytest.fixture
def stack(im_app, tmp_path, monkeypatch):
    from y_web import db
    from y_web.src.im.engine import ensure_im_importable
    from y_web.src.models import Admin_users, Exps, User_Experiment

    ensure_im_importable(str(IM_REPO))
    from yinstantmessaging.client.server_api import LocalServer
    from yinstantmessaging.common.config import load_server_config
    from yinstantmessaging.gateway import HumanGateway, serve
    from yinstantmessaging.gateway.core import RateLimiter
    from yinstantmessaging.server.orchestrator import OrchestratorServer

    helpers = _im_helpers()
    app, client = im_app
    s = Stack()
    s.app, s.client = app, client
    s.exp_id = _make_im_experiment(app)
    with app.app_context():
        exp = db.session.get(Exps, s.exp_id)
        exp.status, exp.running = 1, 1
        uid = exp.db_name.split("/")[1]
        user = Admin_users(
            username="part1", email=f"{uuid.uuid4().hex}@x.test", password="x",
            last_seen="2026-01-01", role="user",
        )
        db.session.add(user)
        db.session.commit()
        db.session.add(User_Experiment(user_id=user.id, exp_id=exp.id if hasattr(exp, "id") else s.exp_id))
        db.session.commit()
        s.user_id, s.uid = user.id, uid
    s.folder = tmp_path / "y_web" / "experiments" / s.uid
    helpers.write_experiment(
        s.folder,
        human={"enabled": True, "max_humans": 5},
        telegram={"time": {"ticks_per_round": 12}, "edits": {"enabled": True}},
    )
    cfg = load_server_config(s.folder)
    cfg["logging"]["log_dir"] = str(s.folder / "logs")
    s.srv = OrchestratorServer(
        db_config=cfg["database"], config_path=str(s.folder), min_to_start=cfg["min_to_start"],
        server_name=cfg["server_name"], timeout_seconds=cfg["timeout_seconds"], simulation_config=cfg,
    )
    s.srv.register_client("c1", {})
    s.srv.bootstrap_population("c1", helpers.AGENTS, helpers.TOPOLOGY)
    assert s.srv.open_round("c1", 1, 1).ok
    gateway = HumanGateway(LocalServer(s.srv).call, limiter=RateLimiter(burst=1000, per_second=1000))
    s.gateway = gateway
    s.http = serve(gateway, TOKEN)
    (s.folder / "human_gateway.json").write_text(
        json.dumps({"host": "127.0.0.1", "port": s.http.server_address[1], "pid": os.getpid()})
    )
    (s.folder / "human_gateway.token").write_text(TOKEN)
    s.participant = SimpleNamespace(
        is_authenticated=True, is_active=True, is_anonymous=False, id=s.user_id, username="part1",
        role="user", telemetry_enabled=0, get_id=lambda: str(s.user_id), email="p@x.test",
    )
    monkeypatch.setattr("flask_login.utils._get_user", lambda: s.participant)
    yield s
    s.http.shutdown()


def _csrf(html):
    return re.search(r'data-csrf="([^"]+)"', html).group(1)


def _enter(s):
    r = s.client.get(f"/{s.exp_id}/im")
    assert r.status_code == 200, r.data[:500]
    return r.data.decode()


def _act(s, payload, token=None, **kw):
    headers = {"X-CSRF-Token": token or _csrf(_enter(s))}
    return s.client.post(f"/{s.exp_id}/im/act", json=payload, headers=headers, **kw)


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
    from y_web.src.im.human_identity import human_account_id

    return human_account_id(s.uid, s.user_id)


def _texts(s):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from yinstantmessaging.server.db import models as m

    with s.srv.sessions() as session:
        return [
            (r.text, r.sender_account_id, r.origin)
            for r in session.scalars(select(m.Message).order_by(m.Message.sim_ts))
        ]


def test_first_entry_creates_the_account_and_shows_the_participant_ui(stack):
    s = stack
    html = _enter(s)
    assert 'data-participant="1"' in html and 'data-writable="1"' in html
    assert "Omniscient" not in html and 'id="im-vp"' not in html  # no viewpoint or time selectors
    from yinstantmessaging.server.db import models as m

    with s.srv.sessions() as session:
        row = session.get(m.Account, _account(s))
        assert row is not None and row.kind == "human" and row.username == "participant-%d" % s.user_id


def test_the_account_is_derived_from_the_session_never_from_the_request(stack):
    s = stack
    assert _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "j1"}).status_code == 200
    r = _act(
        s,
        {
            "type": "post", "chat_id": "c-chat", "text": "hello from a human",
            "client_action_id": "p1", "actor_account_id": "a-alice", "account_id": "a-alice",
            "generation": {"model": "x"},
        },
    )
    assert r.status_code == 200 and r.get_json()["data"]["outcomes"][0]["ok"]
    rows = [t for t in _texts(s) if t[0] == "hello from a human"]
    assert rows == [("hello from a human", _account(s), "human")]


def test_a_sent_message_shows_in_the_chat_page_and_a_retry_is_deduplicated(stack):
    s = stack
    _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "j1"})
    payload = {"type": "post", "chat_id": "c-chat", "text": "once only", "client_action_id": "same"}
    assert _act(s, payload).status_code == 200
    again = _act(s, payload)
    assert again.status_code == 200
    assert again.get_json()["data"]["outcomes"][0]["code"] == "duplicate_action"
    assert [t for t in _texts(s) if t[0] == "once only"].__len__() == 1
    page = s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()
    assert "once only" in page and 'id="im-composer"' in page


def test_reply_react_edit_delete_and_forward(stack):
    s = stack
    _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "j"})
    _act(s, {"type": "post", "chat_id": "c-chat", "text": "base", "client_action_id": "b"})
    from sqlalchemy import select

    from yinstantmessaging.server.db import models as m

    with s.srv.sessions() as session:
        base = session.scalars(select(m.Message).where(m.Message.text == "base")).one().id
    ok = lambda r: r.status_code == 200 and r.get_json()["data"]["outcomes"][0]["ok"]  # noqa: E731
    assert ok(_act(s, {"type": "reply", "chat_id": "c-chat", "text": "re", "reply_to_message_id": base, "client_action_id": "r"}))
    assert ok(_act(s, {"type": "react", "message_id": base, "emoji": "👍", "client_action_id": "x"}))
    assert ok(_act(s, {"type": "edit", "message_id": base, "text": "base edited", "client_action_id": "e"}))
    assert ok(_act(s, {"type": "forward", "chat_id": "c-chat", "forward_of_message_id": base, "client_action_id": "f"}))
    assert ok(_act(s, {"type": "delete", "message_id": base, "client_action_id": "d"}))


def test_csrf_is_required_and_checked(stack):
    s = stack
    _enter(s)
    body = {"type": "join", "chat_id": "c-chat", "client_action_id": "j"}
    assert s.client.post(f"/{s.exp_id}/im/act", json=body).status_code == 400
    assert s.client.post(f"/{s.exp_id}/im/act", json=body, headers={"X-CSRF-Token": "nope"}).status_code == 400


def test_switched_off_interactions_are_refused_by_the_server_and_hidden(stack):
    s = stack
    _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "j"})
    _set(s, interaction_post=False)
    r = _act(s, {"type": "post", "chat_id": "c-chat", "text": "no", "client_action_id": "n1"})
    assert r.status_code == 403 and r.get_json()["code"] == "interaction_post_disabled"
    assert 'data-im-action="send"' in s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()
    assert '[data-im-action="send"]' in s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()  # the gating rule
    _set(s, interaction_post=True, interactions_enabled=False)
    assert _act(s, {"type": "react", "message_id": "m", "emoji": "👍", "client_action_id": "n2"}).status_code == 403
    assert not [t for t in _texts(s) if t[0] == "no"]


def test_only_assigned_participants_and_never_staff_can_write(stack, monkeypatch):
    s = stack
    token = _csrf(_enter(s))
    admin = SimpleNamespace(
        is_authenticated=True, is_active=True, is_anonymous=False, id=1, username="adm", role="admin",
        telemetry_enabled=0, get_id=lambda: "1", email="a@x.test",
    )
    monkeypatch.setattr("flask_login.utils._get_user", lambda: admin)
    r = s.client.post(f"/{s.exp_id}/im/act", json={"type": "join", "chat_id": "c-chat", "client_action_id": "z"}, headers={"X-CSRF-Token": token})
    assert r.status_code == 403
    stranger = SimpleNamespace(**{**vars(s.participant), "id": s.user_id + 99, "username": "other", "get_id": lambda: "x"})
    monkeypatch.setattr("flask_login.utils._get_user", lambda: stranger)
    r = s.client.post(f"/{s.exp_id}/im/act", json={"type": "join", "chat_id": "c-chat", "client_action_id": "z"}, headers={"X-CSRF-Token": token})
    assert r.status_code == 403  # not assigned to this experiment


def test_a_stopped_simulation_is_read_only(stack):
    from y_web import db
    from y_web.src.models import Exps

    s = stack
    token = _csrf(_enter(s))
    with s.app.app_context():
        db.session.get(Exps, s.exp_id).running = 0
        db.session.commit()
    r = s.client.post(f"/{s.exp_id}/im/act", json={"type": "join", "chat_id": "c-chat", "client_action_id": "q"}, headers={"X-CSRF-Token": token})
    assert r.status_code == 409 and r.get_json()["code"] == "not_running"
    page = s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()
    assert 'id="im-composer"' not in page and "Reading only" in page


def test_a_dead_gateway_is_connection_lost_not_an_error(stack):
    s = stack
    token = _csrf(_enter(s))
    s.http.shutdown()
    s.http.server_close()
    r = s.client.post(f"/{s.exp_id}/im/act", json={"type": "join", "chat_id": "c-chat", "client_action_id": "q"}, headers={"X-CSRF-Token": token})
    assert r.status_code == 503 and r.get_json()["code"] == "unavailable"
    assert s.client.get(f"/{s.exp_id}/im/api/gateway").get_json()["online"] is False
    page = s.client.get(f"/{s.exp_id}/im")  # the history stays readable
    assert page.status_code == 200 and 'id="im-composer"' not in page.data.decode()


def test_first_entry_without_the_gateway_falls_back_to_the_public_view(stack):
    s = stack
    s.http.shutdown()
    s.http.server_close()
    page = s.client.get(f"/{s.exp_id}/im")
    html = page.data.decode()
    assert page.status_code == 200 and "not ready yet" in html and 'data-participant="1"' not in html


def test_the_notice_comes_before_the_first_entry(stack):
    s = stack
    _set(s, im_participant_notice="This study records your messages.")
    r = s.client.get(f"/{s.exp_id}/im")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/{s.exp_id}/im/notice")
    page = s.client.get(f"/{s.exp_id}/im/notice").data.decode()
    assert "This study records your messages." in page
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    assert s.client.post(f"/{s.exp_id}/im/notice", data={"csrf_token": "bad"}).status_code == 400
    assert s.client.post(f"/{s.exp_id}/im/notice", data={"csrf_token": token}).status_code == 302
    assert s.client.get(f"/{s.exp_id}/im").status_code == 200


def test_notifications_page_follows_the_setting(stack):
    s = stack
    _enter(s)
    assert s.client.get(f"/{s.exp_id}/im/notifications").status_code == 200
    assert "/im/notifications" in _enter(s)
    _set(s, notifications_menu=False)
    assert s.client.get(f"/{s.exp_id}/im/notifications").status_code == 404
    assert "/im/notifications" not in _enter(s)


def test_participation_off_keeps_the_public_observer(stack):
    s = stack
    _set(s, im_participant_mode_enabled=False)
    html = _enter(s)
    assert 'data-participant="1"' not in html
    r = s.client.post(f"/{s.exp_id}/im/act", json={"type": "join", "chat_id": "c-chat", "client_action_id": "q"})
    assert r.status_code == 403


def test_identity_matches_the_runtime(stack):
    from y_web.src.im.human_identity import human_account_id, human_key
    from yinstantmessaging.server.orchestrator import OrchestratorServer

    assert human_account_id("abc_1", 7) == OrchestratorServer.human_account_id(human_key("abc_1", 7))
    assert human_account_id("abc_1", 7) != human_account_id("abc_1", 8)
    assert human_account_id("abc_1", 7) != human_account_id("abc_2", 7)


def test_edit_and_delete_buttons_follow_the_run_configuration(stack):
    s = stack
    _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "j"})
    _act(s, {"type": "post", "chat_id": "c-chat", "text": "mine", "client_action_id": "m"})
    page = s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()
    assert 'data-im-do="edit"' in page and 'data-im-do="delete"' in page
    cfg = json.loads((s.folder / "server_config.json").read_text())
    cfg["telegram"]["edits"]["enabled"] = False
    (s.folder / "server_config.json").write_text(json.dumps(cfg))
    page = s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()
    assert 'data-im-do="edit"' not in page and 'data-im-do="reply"' in page


def test_html_in_a_message_is_escaped_in_the_pages(stack):
    s = stack
    assert _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "xj"}).status_code == 200
    evil = '<script>alert(1)</script><img src=x onerror=alert(2)>'
    r = _act(s, {"type": "post", "chat_id": "c-chat", "text": evil, "client_action_id": "xp"})
    assert r.status_code == 200 and r.get_json()["data"]["outcomes"][0]["ok"]
    page = s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()
    assert evil not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_a_burst_of_actions_is_rate_limited_and_writes_nothing_extra(stack):
    s = stack
    assert _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "bj"}).status_code == 200
    token = _csrf(_enter(s))
    from yinstantmessaging.gateway.core import RateLimiter

    s.gateway.limiter = RateLimiter(burst=5, per_second=0.01)
    codes = [
        _act(s, {"type": "post", "chat_id": "c-chat", "text": "burst %d" % i, "client_action_id": "b%d" % i}, token=token).status_code
        for i in range(60)
    ]
    assert 429 in codes, codes
    written = [t for t in _texts(s) if t[0].startswith("burst ")]
    assert 0 < len(written) <= 5
    assert all(sender == _account(s) and origin == "human" for _, sender, origin in written)


def test_what_a_participant_reads_is_recorded_as_exposures_once_per_round_and_chat(stack):
    from sqlalchemy import func, select

    from yinstantmessaging.server.db import models as m

    s = stack
    _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "j"})
    _act(s, {"type": "post", "chat_id": "c-chat", "text": "read me", "client_action_id": "p"})

    def exposures():
        with s.srv.sessions() as session:
            return session.scalar(
                select(func.count()).select_from(m.Exposure).where(m.Exposure.account_id == _account(s))
            )

    assert exposures() == 0
    page = s.client.get(f"/{s.exp_id}/im/chat/c-chat")
    assert page.status_code == 200 and "read me" in page.data.decode()
    first = exposures()
    assert first >= 1
    # a refresh, the history API and the topic-less page again: same round and chat, nothing counted twice
    s.client.get(f"/{s.exp_id}/im/chat/c-chat")
    assert s.client.get(f"/{s.exp_id}/im/api/chat/c-chat/history").status_code == 200
    assert exposures() == first
    # a gateway that does not answer never breaks the page
    s.http.shutdown()
    assert s.client.get(f"/{s.exp_id}/im/chat/c-chat").status_code == 200


def _outcome(r):
    assert r.status_code == 200, r.data[:300]
    return r.get_json()["data"]["outcomes"][0]


def test_a_participant_creates_chats_and_owns_them(stack):
    s = stack
    out = _outcome(_act(s, {"type": "create_chat", "chat_type": "channel", "title": "Night trains", "text": "Welcome aboard", "client_action_id": "mk1"}))
    assert out["ok"] and out["chat_id"]
    page = s.client.get(f"/{s.exp_id}/im/chat/{out['chat_id']}").data.decode()
    assert "Night trains" in page and "Welcome aboard" in page
    assert 'data-im-do="rename"' in page and 'data-im-do="leave"' not in page  # the owner renames and cannot leave
    renamed = _outcome(_act(s, {"type": "rename_chat", "chat_id": out["chat_id"], "title": "Day trains", "client_action_id": "rn1"}))
    assert renamed["ok"]
    assert "Day trains" in s.client.get(f"/{s.exp_id}/im/chat/{out['chat_id']}").data.decode()
    direct = _outcome(_act(s, {"type": "create_chat", "chat_type": "private", "target_account_id": "a-alice", "text": "hi Alice", "client_action_id": "mk2"}))
    assert direct["ok"] and direct["chat_id"] != out["chat_id"]


def test_chat_creation_is_limited_and_refused_with_a_reason(stack):
    s = stack
    cfg = json.loads((s.folder / "server_config.json").read_text())
    cfg["human"]["chat_creation"] = {"max_owned_chats": 1}
    (s.folder / "server_config.json").write_text(json.dumps(cfg))
    s.srv.messages.human_chats.cfg = type(s.srv.messages.human_chats.cfg)(max_owned_chats=1)
    assert _outcome(_act(s, {"type": "create_chat", "chat_type": "channel", "title": "One", "client_action_id": "a"}))["ok"]
    second = _outcome(_act(s, {"type": "create_chat", "chat_type": "channel", "title": "Two", "client_action_id": "b"}))
    assert not second["ok"] and second["reason"] == "creation_limit_reached"


def test_the_new_chat_button_follows_the_run_settings(stack):
    s = stack
    html = _enter(s)
    assert 'id="im-new-open"' in html and 'value="private"' in html and 'value="group"' in html
    cfg = json.loads((s.folder / "server_config.json").read_text())
    cfg["human"]["chat_creation"] = {"allow_direct": False, "allow_private_groups": False}
    (s.folder / "server_config.json").write_text(json.dumps(cfg))
    html = _enter(s)
    assert 'id="im-new-open"' in html and 'value="private"' not in html and 'value="group"' not in html
    cfg["human"]["chat_creation"] = {"enabled": False}
    (s.folder / "server_config.json").write_text(json.dumps(cfg))
    html = _enter(s)
    assert 'id="im-new-open"' not in html and 'id="im-new"' not in html


def test_join_and_leave_buttons_follow_the_membership_and_search_shows_it(stack):
    s = stack
    before = s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()
    assert 'data-im-do="join"' in before and 'data-im-do="leave"' not in before
    assert _outcome(_act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "j"}))["ok"]
    after = s.client.get(f"/{s.exp_id}/im/chat/c-chat").data.decode()
    assert 'data-im-do="leave"' in after and 'data-im-do="join"' not in after
    assert _outcome(_act(s, {"type": "leave", "chat_id": "c-chat", "client_action_id": "l"}))["ok"]
    from sqlalchemy import select

    from yinstantmessaging.server.db import models as m

    with s.srv.sessions() as session:
        title = session.get(m.Chat, "c-chat").title
    found = s.client.get(f"/{s.exp_id}/im/api/search?kind=chats&q={title[:3]}").get_json()
    hit = next(r for r in found["results"] if r["chat_id"] == "c-chat")
    assert hit["joined"] is False
    _act(s, {"type": "join", "chat_id": "c-chat", "client_action_id": "j2"})
    again = s.client.get(f"/{s.exp_id}/im/api/search?kind=chats&q={title[:3]}").get_json()
    assert next(r for r in again["results"] if r["chat_id"] == "c-chat")["joined"] is True
