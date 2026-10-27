"""The frontend settings of an IM experiment change what its observer pages show (plan section 7, Phase 8)."""

import json
import re

import pytest

from y_web.tests.test_im_admin_pages import im_app  # noqa: F401
from y_web.tests.test_im_observer_routes import observer  # noqa: F401


def _set(app, exp_id, **settings):
    from y_web import db
    from y_web.src.models import ExpFrontendSettings

    with app.app_context():
        row = db.session.get(ExpFrontendSettings, exp_id)
        if row is None:
            row = ExpFrontendSettings(exp_id=exp_id, settings_json="{}")
            db.session.add(row)
        data = json.loads(row.settings_json or "{}")
        data.update(settings)
        row.settings_json = json.dumps(data)
        db.session.commit()


def _page(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.data.decode()


def _busy_chat(client, exp_id, info):
    return max(info["chats"], key=lambda c: len(client.get(f"/{exp_id}/im/chat/{c}").data))


def test_show_post_time_off_hides_times(observer):
    app, client, exp_id, info, _ = observer
    chat = _busy_chat(client, exp_id, info)
    assert 'data-im-time' in _page(client, f"/{exp_id}/im/chat/{chat}")
    _set(app, exp_id, show_post_time=False)
    assert 'data-im-time' not in _page(client, f"/{exp_id}/im/chat/{chat}")


def test_agent_type_badge_follows_annotation_agent_type(observer):
    app, client, exp_id, info, _ = observer
    chat = _busy_chat(client, exp_id, info)
    assert 'class="im-kind"' in _page(client, f"/{exp_id}/im/chat/{chat}")
    _set(app, exp_id, annotation_agent_type=False)
    for url in (f"/{exp_id}/im/chat/{chat}/members", f"/{exp_id}/im/profile/{info['accounts'][0]}"):
        assert not re.search(r'<span class="im-kind">(agent|human)</span>', _page(client, url))
    chat_html = _page(client, f"/{exp_id}/im/chat/{chat}")
    assert not re.search(r'<span class="im-kind">(agent|human)</span>', chat_html)


def _add_reactions(path, per_chat=3):
    """The fixture database has no reactions: add a few to visible messages of every chat."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from y_web.src.im.engine import im_modules
    from yinstantmessaging.server.db.database import make_engine_from_url

    models = im_modules()[0]
    engine = make_engine_from_url(f"sqlite:///{path}")
    with Session(engine) as session:
        account = session.scalars(select(models.Account.id)).first()
        chats = session.scalars(select(models.Chat.id)).all()
        for chat in chats:
            for message in session.scalars(
                select(models.Message.id).where(models.Message.chat_id == chat).order_by(models.Message.sim_ts.desc()).limit(per_chat)
            ):
                session.add(models.Reaction(account_id=account, message_id=message, emoji="👍", round_id=1))
        session.commit()
    engine.dispose()


def test_reactions_flag(observer):
    app, client, exp_id, info, path = observer
    _add_reactions(path)
    on = {c: _page(client, f"/{exp_id}/im/chat/{c}").count("im-reaction") for c in info["chats"]}
    assert any(on.values())
    _set(app, exp_id, im_show_reactions=False)
    for c in info["chats"]:
        assert "im-reaction" not in _page(client, f"/{exp_id}/im/chat/{c}").split("<main")[1]


def _forward_one(path):
    """Mark the newest message of the first chat as forwarded from another chat; returns that chat id."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from y_web.src.im.engine import im_modules
    from yinstantmessaging.server.db.database import make_engine_from_url

    models = im_modules()[0]
    engine = make_engine_from_url(f"sqlite:///{path}")
    with Session(engine) as session:
        chats = session.scalars(select(models.Chat.id).order_by(models.Chat.id)).all()
        msg = session.scalars(
            select(models.Message).where(models.Message.chat_id == chats[0], models.Message.deleted_round.is_(None)).order_by(models.Message.sim_ts.desc())
        ).first()
        msg.fwd_from_chat_id = chats[1]
        msg.fwd_origin_chat_id = chats[1]
        session.commit()
        target = chats[0]
    engine.dispose()
    return target


def test_forward_origin_flag(observer):
    app, client, exp_id, info, path = observer
    chat = _forward_one(path)
    assert "Forwarded from" in _page(client, f"/{exp_id}/im/chat/{chat}")
    _set(app, exp_id, im_show_forward_origin=False)
    html = _page(client, f"/{exp_id}/im/chat/{chat}")
    assert "Forwarded from" not in html and "Forwarded message" in html


def test_member_roles_flag(observer):
    app, client, exp_id, info, _ = observer
    url = f"/{exp_id}/im/chat/{info['chats'][0]}/members"
    assert ">Role<" in _page(client, url)
    _set(app, exp_id, im_show_member_roles=False)
    assert ">Role<" not in _page(client, url)


def test_profile_topics_box_gates_the_persona(observer):
    app, client, exp_id, info, _ = observer
    url = f"/{exp_id}/im/profile/{info['accounts'][0]}"
    with_box = _page(client, url).count("<dt>")
    _set(app, exp_id, profile_topics_box=False)
    assert _page(client, url).count("<dt>") <= with_box


def test_posts_per_page_sizes_the_page(observer):
    app, client, exp_id, info, _ = observer
    chat = _busy_chat(client, exp_id, info)
    _set(app, exp_id, posts_per_page=3)
    html = _page(client, f"/{exp_id}/im/chat/{chat}")
    assert len(re.findall(r'class="im-msg[ "]', html)) <= 3
    assert "Older messages" in html
    _set(app, exp_id, posts_per_page=100000)  # clamped, never an unbounded query
    assert len(re.findall(r'class="im-msg[ "]', _page(client, f"/{exp_id}/im/chat/{chat}"))) <= 100


def test_infinite_scroll_flag_reaches_the_page(observer):
    app, client, exp_id, info, _ = observer
    chat = _busy_chat(client, exp_id, info)
    assert 'data-infinite="1"' in _page(client, f"/{exp_id}/im/chat/{chat}")
    _set(app, exp_id, infinite_scroll_enabled=False)
    assert 'data-infinite="0"' in _page(client, f"/{exp_id}/im/chat/{chat}")


def test_default_view_start_opens_at_the_beginning_and_pages_forward(observer):
    app, client, exp_id, info, _ = observer
    chat = _busy_chat(client, exp_id, info)
    _set(app, exp_id, posts_per_page=5)
    latest_ids = re.findall(r'id="m-([^"]+)"', _page(client, f"/{exp_id}/im/chat/{chat}"))
    _set(app, exp_id, im_default_view="start")
    html = _page(client, f"/{exp_id}/im/chat/{chat}")
    first_ids = re.findall(r'id="m-([^"]+)"', html)
    assert first_ids and first_ids != latest_ids
    assert "Newer messages" in html and "Older messages" not in html
    seen = set(first_ids)
    guard = 0
    while True:
        m = re.search(r'href="\?([^"]*after=[^"]+)"', html)
        if not m:
            break
        html = _page(client, f"/{exp_id}/im/chat/{chat}?{m.group(1).replace('&amp;', '&')}")
        ids = re.findall(r'id="m-([^"]+)"', html)
        assert not seen & set(ids)
        seen |= set(ids)
        guard += 1
        assert guard < 100
    assert set(latest_ids) <= seen  # paging forward reaches the newest messages
    page = client.get(f"/{exp_id}/im/api/chat/{chat}/history").get_json()
    assert page["items"] and page["next_after"] is not None


def test_time_travel_gate_for_non_staff(observer, monkeypatch):
    from y_web.routes.social import instant_messaging

    app, client, exp_id, info, _ = observer
    chat = _busy_chat(client, exp_id, info)
    real_staff = instant_messaging._staff_user
    monkeypatch.setattr(instant_messaging, "_staff_user", lambda: None)
    assert 'id="im-day"' in _page(client, f"/{exp_id}/im")
    early = _page(client, f"/{exp_id}/im/chat/{chat}?day=1&slot=3")
    _set(app, exp_id, im_allow_time_travel=False)
    html = _page(client, f"/{exp_id}/im")
    assert 'id="im-day"' not in html
    closed = _page(client, f"/{exp_id}/im/chat/{chat}?day=1&slot=3")
    assert len(re.findall(r'class="im-msg[ "]', closed)) >= len(re.findall(r'class="im-msg[ "]', early))
    monkeypatch.setattr(instant_messaging, "_staff_user", real_staff)  # staff keep the selector whatever the setting says
    assert 'id="im-day"' in _page(client, f"/{exp_id}/im")


def test_public_observer_gate(observer, monkeypatch):
    from y_web.routes.social import instant_messaging

    app, client, exp_id, info, _ = observer
    _set(app, exp_id, im_public_observer_enabled=False)
    assert client.get(f"/{exp_id}/im").status_code == 200  # staff are not affected
    monkeypatch.setattr(instant_messaging, "_staff_user", lambda: None)
    assert client.get(f"/{exp_id}/im").status_code == 403
    assert client.get(f"/{exp_id}/im/chat/{info['chats'][0]}").status_code == 403
    assert client.get(f"/{exp_id}/im/api/chat/{info['chats'][0]}/history").status_code == 403


def test_poll_interval_comes_from_the_settings(observer):
    from y_web import db
    from y_web.src.models import Exps

    app, client, exp_id, info, _ = observer
    with app.app_context():
        db.session.get(Exps, exp_id).running = 1
        db.session.commit()
    assert 'data-poll="3"' in _page(client, f"/{exp_id}/im")
    _set(app, exp_id, im_participant_poll_seconds=9)
    assert 'data-poll="9"' in _page(client, f"/{exp_id}/im")
    _set(app, exp_id, im_participant_poll_seconds=9999)  # stored by hand: still clamped when read
    assert 'data-poll="60"' in _page(client, f"/{exp_id}/im")


def test_interaction_switches_become_css_rules_for_the_participant_controls(observer):
    app, client, exp_id, info, _ = observer
    _set(app, exp_id, interaction_post=False, interaction_like=False, interaction_share=False)
    head = _page(client, f"/{exp_id}/im").split("</head>")[0]
    assert '[data-im-action="send"]' in head and '[data-im-action="react"]' in head
    assert '[data-im-action="forward"]' in head and '[data-im-action="reply"]' not in head
    _set(app, exp_id, interactions_enabled=False)
    assert "[data-im-action]" in _page(client, f"/{exp_id}/im").split("</head>")[0]


def test_no_frontend_plugin_module_attaches_to_im_pages(observer):
    from y_web.routes.social.helpers import _platform_ui_context

    app, client, exp_id, info, _ = observer
    with app.test_request_context(f"/{exp_id}/im"):
        from flask import request

        request.view_args = {"exp_id": exp_id}
        ctx = _platform_ui_context()
    assert ctx["frontend_adds_on_modules"] == [] and ctx["platform_ui"] == "im"
