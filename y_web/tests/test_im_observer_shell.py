"""The three-pane observer shell: staff menu, view-as-account, info panel and annotation chips."""

import re

from y_web.tests.test_im_admin_pages import im_app  # noqa: F401
from y_web.tests.test_im_observer_routes import observer  # noqa: F401
from y_web.tests.test_im_observer_settings import _busy_chat, _page, _set


def test_staff_menu_links_back_to_the_administration(observer):
    app, client, exp_id, info, _ = observer
    html = _page(client, f"/{exp_id}/im")
    assert f'href="/admin/experiment_details/{exp_id}"' in html
    assert 'href="/admin/experiments"' in html
    assert 'name="acc"' in html and 'list="im-accounts"' in html  # the "view as account" picker


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
