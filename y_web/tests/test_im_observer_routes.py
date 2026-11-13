"""IM observer blueprint: pages per viewpoint and role, time travel, no db_exp bind, read-only (Phase 7)."""

import hashlib
import os
import uuid

import pytest

from y_web.tests.im_fixture_db import build_random_db
from y_web.tests.test_im_admin_pages import _make_im_experiment, im_app  # noqa: F401


@pytest.fixture
def observer(im_app, tmp_path):
    from y_web import db
    from y_web.src.models import Exps

    app, client = im_app
    exp_id = _make_im_experiment(app)
    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        exp.status = 1
        db.session.commit()
        folder = tmp_path / "y_web" / "experiments" / exp.db_name.split("/")[1]
        folder.mkdir(parents=True)
        info = build_random_db(
            str(folder / "database_server.db"), seed=5, rounds=30, messages=200
        )
    return app, client, exp_id, info, str(folder / "database_server.db")


def _get(client, path, **kw):
    return client.get(path, **kw)


def test_index_lists_chats_for_the_overview_with_the_omniscient_banner(observer):
    app, client, exp_id, info, _ = observer
    r = _get(client, f"/{exp_id}/im")
    html = r.data.decode()
    assert r.status_code == 200
    assert "Omniscient researcher view" in html
    for chat in info["chats"]:
        assert f"/{exp_id}/im/chat/{chat}" in html


def test_public_viewpoint_hides_private_chats_and_refuses_them(observer):
    from y_web.src.im import engine

    app, client, exp_id, info, path = observer
    with engine.open_reader(path) as session:
        models = engine.im_modules()[0]
        private = [
            c.id
            for c in session.query(models.Chat)
            if c.visibility == "private" or c.type == "private"
        ]
        public = [c.id for c in session.query(models.Chat) if c.id not in private]
    assert private and public
    html = _get(client, f"/{exp_id}/im?vp=public").data.decode()
    assert all(f"/chat/{c}" not in html for c in private)
    assert "Omniscient" not in html
    for c in private:
        assert _get(client, f"/{exp_id}/im/chat/{c}?vp=public").status_code == 404
        assert (
            _get(client, f"/{exp_id}/im/chat/{c}").status_code == 200
        )  # the overview may open it
    assert _get(client, f"/{exp_id}/im/chat/{public[0]}?vp=public").status_code == 200


def test_chat_page_renders_bubbles_tombstones_and_pagination(observer):
    app, client, exp_id, info, path = observer
    pages = [
        (_get(client, f"/{exp_id}/im/chat/{c}").data.decode(), c) for c in info["chats"]
    ]
    joined = "\n".join(p for p, _c in pages)
    assert "im-bubble" in joined and "This message was deleted." in joined
    assert "im-reply" in joined  # replies carry a preview
    assert any("Older messages" in p for p, _c in pages) or all(
        "im-msg" in p for p, _c in pages
    )


def test_account_viewpoint_shows_unread_and_banner(observer):
    app, client, exp_id, info, _ = observer
    r = _get(client, f"/{exp_id}/im?vp=account&acc={info['accounts'][1]}")
    assert r.status_code == 200 and "Viewing as account" in r.data.decode()
    assert _get(client, f"/{exp_id}/im?vp=account&acc=ghost").status_code == 400
    assert _get(client, f"/{exp_id}/im?vp=account").status_code == 400
    assert _get(client, f"/{exp_id}/im?vp=bogus").status_code == 400


def test_time_travel_shows_only_earlier_content(observer):
    app, client, exp_id, info, _ = observer
    chat = max(
        info["chats"], key=lambda c: len(_get(client, f"/{exp_id}/im/chat/{c}").data)
    )
    full = _get(client, f"/{exp_id}/im/chat/{chat}").data.decode()
    early = _get(client, f"/{exp_id}/im/chat/{chat}?day=1&slot=3").data.decode()
    assert early.count('class="im-msg') < full.count('class="im-msg')
    assert "day 1, slot 4" not in early and "day 1, slot 5" not in early
    assert _get(client, f"/{exp_id}/im/chat/{chat}?day=x&slot=1").status_code == 400


def test_participants_get_the_public_view_only(observer, monkeypatch):
    from y_web.routes.social import instant_messaging

    app, client, exp_id, info, _ = observer
    monkeypatch.setattr(instant_messaging, "_staff_user", lambda: None)
    assert _get(client, f"/{exp_id}/im").status_code == 200
    html = _get(client, f"/{exp_id}/im").data.decode()
    assert "Omniscient" not in html and 'value="overview"' not in html
    assert _get(client, f"/{exp_id}/im?vp=overview").status_code == 403
    assert (
        _get(client, f"/{exp_id}/im?vp=account&acc={info['accounts'][0]}").status_code
        == 403
    )
    assert (
        _get(
            client, f"/{exp_id}/im/profile/{info['accounts'][0]}?vp=public"
        ).status_code
        == 200
    )


def test_api_status_history_and_search(observer):
    app, client, exp_id, info, _ = observer
    status = _get(client, f"/{exp_id}/im/api/status?after=1").get_json()
    assert (
        status["round"] == 30
        and status["changed"] is True
        and status["running"] is False
    )
    assert (
        _get(client, f"/{exp_id}/im/api/status?after=30").get_json()["changed"] is False
    )
    page = _get(client, f"/{exp_id}/im/api/chat/{info['chats'][0]}/history").get_json()
    assert "items" in page and "next_before" in page
    assert _get(client, f"/{exp_id}/im/api/chat/nope/history").status_code == 404
    assert _get(client, f"/{exp_id}/im/search?q=text").status_code == 200
    assert (
        _get(client, f"/{exp_id}/im/search?q=a").status_code == 200
    )  # too short: a hint, not an error


def test_members_thread_profile_pages(observer):
    from y_web.src.im import engine

    app, client, exp_id, info, path = observer
    assert (
        _get(client, f"/{exp_id}/im/chat/{info['chats'][0]}/members").status_code == 200
    )
    with engine.open_reader(path) as session:
        models = engine.im_modules()[0]
        reply = (
            session.query(models.Message)
            .filter(models.Message.reply_to_message_id.is_not(None))
            .first()
            .id
        )
    assert _get(client, f"/{exp_id}/im/thread/{reply}").status_code == 200
    assert _get(client, f"/{exp_id}/im/thread/nope").status_code == 404
    assert (
        _get(client, f"/{exp_id}/im/profile/{info['accounts'][0]}").status_code == 200
    )
    assert _get(client, f"/{exp_id}/im/profile/ghost").status_code == 404


def test_browsing_never_writes_and_never_binds_db_exp(observer):
    app, client, exp_id, info, path = observer
    before = hashlib.sha256(open(path, "rb").read()).hexdigest()
    binds_before = set(app.config["SQLALCHEMY_BINDS"])
    for url in (
        f"/{exp_id}/im",
        f"/{exp_id}/im?vp=public",
        f"/{exp_id}/im/chat/{info['chats'][0]}",
        f"/{exp_id}/im/search?q=text",
        f"/{exp_id}/im/api/status",
    ):
        _get(client, url)
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == before
    assert set(app.config["SQLALCHEMY_BINDS"]) == binds_before
    assert f"db_exp_{exp_id}" not in app.config["SQLALCHEMY_BINDS"]


def test_unknown_non_im_and_unreadable_experiments(observer, im_app, monkeypatch):
    from y_web import db
    from y_web.src.models import Exps

    app, client, exp_id, info, path = observer
    assert _get(client, "/999999/im").status_code == 404
    other_uid = uuid.uuid4().hex
    # the fixture's writable path is one folder for everything, so a YSocial bind cannot be built here
    monkeypatch.setattr(
        "y_web.src.experiment.context.register_experiment_database",
        lambda *a, **k: None,
    )
    with app.app_context():
        other = Exps(
            exp_name="mb2",
            platform_type="microblogging",
            simulator_type="HPC",
            db_name=f"experiments/{other_uid}/database_server.db",
            owner="adm",
            exp_descr="d",
            status=1,
            port=5097,
            server="127.0.0.1",
            prompt_language="en",
        )
        db.session.add(other)
        db.session.commit()
        other_id = other.idexp
    assert _get(client, f"/{other_id}/im").status_code == 404
    os.remove(path)
    r = _get(client, f"/{exp_id}/im")
    assert r.status_code == 503 and b"cannot be shown" in r.data
    assert _get(client, f"/{exp_id}/im/api/status").status_code == 503


def test_join_experiment_opens_the_observer(observer, monkeypatch):
    app, client, exp_id, info, _ = observer
    r = client.get(f"/admin/join_experiment/{exp_id}")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/{exp_id}/im")


def test_accessibility_smoke_headings_labels_and_landmarks(observer):
    import re

    app, client, exp_id, info, _ = observer
    for url in (
        f"/{exp_id}/im",
        f"/{exp_id}/im/chat/{info['chats'][0]}",
        f"/{exp_id}/im/chat/{info['chats'][0]}/members",
    ):
        html = client.get(url).data.decode()
        assert html.count("<h1") == 1 and "<main" in html and 'lang="' in html
        assert 'class="im-skip"' in html
        ids = set(re.findall(r'<(?:input|select)[^>]*\bid="([^"]+)"', html))
        labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))
        assert ids <= labelled | {"im-theme"}, ids - labelled
