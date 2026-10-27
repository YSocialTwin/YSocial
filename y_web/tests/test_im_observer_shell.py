"""The three-pane observer shell: staff menu, view-as-account, info panel and annotation chips."""

import re

from y_web.tests.test_im_admin_pages import im_app  # noqa: F401
from y_web.tests.test_im_observer_routes import observer  # noqa: F401
from y_web.tests.test_im_observer_settings import _busy_chat, _page, _set


def test_staff_menu_has_one_dashboard_link_viewpoints_and_time(observer):
    app, client, exp_id, info, _ = observer
    html = _page(client, f"/{exp_id}/im")
    menu = html[html.index('id="im-menu"') : html.index("</details>")]
    assert menu.count('href="/admin/') == 1 and 'href="/admin/dashboard"' in menu
    assert "experiment_details" not in menu and "/admin/experiments" not in menu
    assert "vp=overview" in menu and "vp=public" in menu  # the viewpoints
    assert 'list="im-accounts"' in menu and 'name="day"' in menu  # view as account, time selection


def test_dark_mode_button_is_outside_the_menu_for_everyone(observer):
    app, client, exp_id, info, _ = observer
    html = _page(client, f"/{exp_id}/im")
    assert html.count('id="im-theme"') == 1
    menu = html[html.index('id="im-menu"') : html.index("</details>")]
    assert 'id="im-theme"' not in menu
    assert html.index('id="im-theme"') > html.index("</details>")


def test_wallpaper_is_neutral_not_green(observer):
    import os

    css = open(os.path.join(os.path.dirname(__file__), "..", "static", "assets", "css", "im.css")).read()
    assert "--im-wall-2" not in css and "#c6dca0" not in css and "#a9c98a" not in css
    assert "radial-gradient" not in css


def test_view_as_account_shows_the_chip_and_an_exit(observer):
    app, client, exp_id, info, _ = observer
    acc = info["accounts"][0]
    html = _page(client, f"/{exp_id}/im?vp=account&acc={acc}")
    assert 'class="im-viewing"' in html and "im-viewing-exit" in html
    assert "vp=overview" in html  # the way back to the researcher overview


def test_chat_has_info_panel_with_view_as_links_for_staff(observer):
    app, client, exp_id, info, _ = observer
    chat = _busy_chat(client, exp_id, info)
    html = _page(client, f"/{exp_id}/im/chat/{chat}")
    assert 'id="im-info"' in html and 'id="im-info-toggle"' in html
    assert re.search(r'class="im-viewas" href="/%s/im\?vp=account&acc=' % exp_id, html)
    assert 'class="im-day-chip"' in html


def test_profile_offers_view_as_for_staff(observer):
    app, client, exp_id, info, _ = observer
    html = _page(client, f"/{exp_id}/im/profile/{info['accounts'][0]}")
    assert "View as this account" in html


def _annotate(path):
    """Give the newest message of every chat a hashtag, a toxicity score and a sentiment."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from y_web.src.im.engine import im_modules
    from yinstantmessaging.server.db.database import make_engine_from_url

    m = im_modules()[0]
    engine = make_engine_from_url(f"sqlite:///{path}")
    with Session(engine) as session:
        session.add(m.AnnotationMethod(method_ref="toxicity@t", method_id="toxicity", version="1", params_hash="x"))
        session.add(m.AnnotationMethod(method_ref="sentiment@t", method_id="sentiment", version="1", params_hash="y"))
        tag = m.Hashtag(hashtag="shell")
        session.add(tag)
        session.flush()
        for chat in session.scalars(select(m.Chat.id)).all():
            msg = session.scalars(select(m.Message.id).where(m.Message.chat_id == chat).order_by(m.Message.sim_ts.desc())).first()
            if msg is None:
                continue
            session.add(m.MessageHashtag(message_id=msg, hashtag_id=tag.id))
            session.add(m.Annotation(message_id=msg, method_ref="toxicity@t", status="ok", value={"toxicity": 0.72}))
            session.add(m.Annotation(message_id=msg, method_ref="sentiment@t", status="ok", value={"compound": -0.4}))
        session.commit()
    engine.dispose()


def test_annotation_chips_are_shown_to_staff_whatever_the_setting(observer):
    app, client, exp_id, info, path = observer
    _annotate(path)
    chat = _busy_chat(client, exp_id, info)
    _set(app, exp_id, annotations_enabled=False)
    html = _page(client, f"/{exp_id}/im/chat/{chat}")
    assert "#shell" in html
    assert "is-tox is-high" in html and "is-sentiment is-negative" in html  # staff always see every annotation


def _names(path):
    from y_web.src.im import engine

    with engine.open_reader(path) as session:
        m = engine.im_modules()[0]
        chats = [(c.id, c.title, c.type, c.visibility) for c in session.query(m.Chat)]
        accounts = [(a.id, a.username) for a in session.query(m.Account)]
    return chats, accounts


def _find(client, exp_id, kind, q, extra=""):
    r = client.get(f"/{exp_id}/im/api/search?kind={kind}&q={q}{extra}")
    assert r.status_code == 200
    return r.get_json()


def test_search_overlay_is_in_the_shell_with_one_tab_per_kind(observer):
    app, client, exp_id, info, _ = observer
    html = _page(client, f"/{exp_id}/im")
    assert 'id="im-find"' in html and f'data-find-url="/{exp_id}/im/api/search"' in html
    tabs = re.findall(r'role="tab" data-kind="(\w+)"', html)
    assert tabs == ["chats", "users", "groups", "channels", "posts"]
    assert 'action="/%s/im/search"' % exp_id in html  # still works without JavaScript


def test_search_api_finds_chats_by_title_and_filters_by_kind(observer):
    app, client, exp_id, info, path = observer
    chats, _ = _names(path)
    group = next(c for c in chats if c[2] in ("group", "supergroup") and c[3] == "public" and c[1])
    data = _find(client, exp_id, "chats", group[1][:4].replace(" ", "%20"))
    assert group[0] in [r["chat_id"] for r in data["results"]]
    hit = next(r for r in data["results"] if r["chat_id"] == group[0])
    assert hit["href"].startswith(f"/{exp_id}/im/chat/{group[0]}") and "members" in hit["subtitle"]
    assert group[0] in [r["chat_id"] for r in _find(client, exp_id, "groups", group[1][:4])["results"]]
    assert group[0] not in [r["chat_id"] for r in _find(client, exp_id, "channels", group[1][:4])["results"]]


def test_search_api_finds_users_and_posts_and_reports_empty_states(observer):
    app, client, exp_id, info, path = observer
    _, accounts = _names(path)
    acc = next(a for a in accounts if a[1])
    users = _find(client, exp_id, "users", acc[1])["results"]
    assert acc[0] in [u["href"].split("/profile/")[1].split("?")[0] for u in users]
    assert _find(client, exp_id, "users", "zzzzqqqq")["message"]
    assert _find(client, exp_id, "chats", "")["results"] == []
    assert _find(client, exp_id, "posts", "a")["results"] == []  # posts need two characters
    assert _find(client, exp_id, "nonsense", "x")["kind"] == "chats"


def test_search_api_respects_the_viewpoint(observer):
    app, client, exp_id, info, path = observer
    chats, _ = _names(path)
    private = [c for c in chats if c[3] == "private" or c[2] == "private"]
    assert private
    for cid, title, ctype, vis in private:
        if not title:
            continue
        found = _find(client, exp_id, "chats", title[:4], "&vp=public")["results"]
        assert cid not in [r["chat_id"] for r in found]


def test_search_api_in_an_account_viewpoint_marks_joined_chats(observer):
    app, client, exp_id, info, path = observer
    acc = info["accounts"][0]
    chats, _ = _names(path)
    for cid, title, ctype, vis in chats:
        if title and ctype != "private":
            res = _find(client, exp_id, "chats", title[:4], f"&vp=account&acc={acc}")["results"]
            assert all("joined" in r for r in res)
            break


def _persona(path, account, persona):
    from sqlalchemy.orm import Session

    from y_web.src.im.engine import im_modules
    from yinstantmessaging.server.db.database import make_engine_from_url

    m = im_modules()[0]
    engine = make_engine_from_url(f"sqlite:///{path}")
    with Session(engine) as session:
        session.get(m.Account, account).persona = persona
        for variable, values in (("stress", (0.2, 0.4)), ("reward", (0.7, 0.6))):
            for n, value in enumerate(values, 1):
                session.add(m.StressReward(id=f"sr-{variable}-{n}", uid=account, variable=variable, value=value, type="aggregate", tid=n))
        session.commit()
    engine.dispose()


def test_the_agent_profile_is_laid_out_in_cards_without_raw_json(observer):
    app, client, exp_id, info, path = observer
    acc = info["accounts"][0]
    _persona(
        path,
        acc,
        {
            "age": 31, "gender": "female", "profession": "Hotel Receptionist", "education_level": "bachelor",
            "interests": {"tea": 1.0, "trains": 0.4}, "opinions": {}, "feed_url": None, "toxicity": "none",
            "big_five": {"ag": "critical/judgmental", "ne": "sensitive/nervous"}, "daily_activity_level": 2, "round_actions": 10,
            "favourite_colour": {"main": "blue"},
        },
    )
    html = _page(client, f"/{exp_id}/im/profile/{acc}")
    assert 'class="im-card"' in html and "Education" in html and "Hotel Receptionist" in html
    assert "Agreeableness" in html and "critical/judgmental" in html  # the Big Five by name, not by code
    assert 'class="im-interests"' in html and "tea" in html
    assert "{&#34;" not in html and '{"' not in html.split('class="im-page-body')[1]  # no JSON strings
    assert "Stress and reward" in html and "is-stress" in html and "is-reward" in html
    assert "feed_url" not in html and "Feed url" not in html  # empty attributes are not shown
    assert "Other attributes" in html and "main: blue" in html  # unknown attributes are readable too


def test_stress_and_reward_only_appear_when_the_run_computes_them(observer):
    app, client, exp_id, info, path = observer
    acc = info["accounts"][0]
    assert "Stress and reward" not in _page(client, f"/{exp_id}/im/profile/{acc}")
    _persona(path, acc, {"age": 20})
    assert "Stress and reward" in _page(client, f"/{exp_id}/im/profile/{acc}")


def test_llm_emotions_and_member_rights_are_readable(observer):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from y_web.src.im.engine import im_modules
    from yinstantmessaging.server.db.database import make_engine_from_url

    app, client, exp_id, info, path = observer
    chat = _busy_chat(client, exp_id, info)
    m = im_modules()[0]
    engine = make_engine_from_url(f"sqlite:///{path}")
    with Session(engine) as session:
        session.add(m.AnnotationMethod(method_ref="emotions_llm@t", method_id="emotions_llm", version="1", params_hash="z"))
        msg = session.scalars(select(m.Message.id).where(m.Message.chat_id == chat).order_by(m.Message.sim_ts.desc())).first()
        session.add(m.Annotation(message_id=msg, method_ref="emotions_llm@t", status="ok", value={"emotions": ["joy", "amusement"]}))
        session.commit()
    engine.dispose()
    assert "joy, amusement" in _page(client, f"/{exp_id}/im/chat/{chat}")
    members = _page(client, f"/{exp_id}/im/chat/{chat}/members")
    assert "Special rights" in members and "Permissions" not in members


def test_message_times_show_day_hour_and_the_estimated_minute(observer):
    app, client, exp_id, info, path = observer
    chat = _busy_chat(client, exp_id, info)
    html = _page(client, f"/{exp_id}/im/chat/{chat}")
    assert re.search(r'data-im-time="" title="[^"]+"[^>]*>d\d+ · \d\d:\d\d</time>', html)


def test_time_section_shows_the_moment_and_steps_between_slots(observer):
    app, client, exp_id, info, path = observer
    html = _page(client, f"/{exp_id}/im")
    menu = html[html.index('id="im-menu"') : html.index("</details>")]
    assert "im-time-now" in menu and "is-live" in menu and "Previous" in menu and "Next" not in menu.split("im-stepper")[1].split("</div>")[0].replace("Next slot", "")
    assert 'name="day"' in menu and 'name="slot"' in menu and "im-viewform" in menu
    past = _page(client, f"/{exp_id}/im?day=1&slot=2")
    pmenu = past[past.index('id="im-menu"') : past.index("</details>")]
    assert "is-past" in pmenu and "Next" in pmenu and "im-latest" in pmenu
