"""The RSS feeds page of the forum also serves IM experiments (news pages and snapshot)."""

import json

import pytest

from y_web.tests.test_im_admin_pages import im_app  # noqa: F401  (fixture)
from y_web.tests.test_im_opinion_page import _setup

pytestmark = pytest.mark.integration


def test_feeds_are_selected_and_the_snapshot_is_written(im_app, monkeypatch, tmp_path):
    app, http = im_app
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path)
    )
    exp_id, _client_id, folder = _setup(app, tmp_path, opinion=False)
    from y_web import db
    from y_web.src.im import news
    from y_web.src.models import ForumRssFeedResource

    with app.app_context():
        res = ForumRssFeedResource(
            name="BBC", feed_url="http://bbc/rss", url_site="http://bbc", description=""
        )
        db.session.add(res)
        db.session.commit()
        res_id = res.id
    page = http.get(f"/admin/rss_feeds/{exp_id}")
    html = page.data.decode()
    assert (
        page.status_code == 200
        and "News snapshot" in html
        and "Direct Article URLs" not in html
    )
    saved = http.post(
        f"/admin/update_rss_feeds/{exp_id}",
        data={"rss_feed_resource_ids": [str(res_id)]},
    )
    assert saved.status_code == 302
    assert news.selected_feeds(str(folder)) == [
        {"name": "BBC", "feed_url": "http://bbc/rss"}
    ]
    assert not (folder / "url_feeds.txt").exists()  # direct URLs are a forum notion

    seen = []
    monkeypatch.setattr(
        news,
        "write_snapshot",
        lambda f, urls, **k: seen.append(sorted(urls))
        or {"articles": 2, "feeds": {"http://bbc/rss": 2}, "written": True},
    )
    assert http.post(f"/admin/im_news_snapshot/{exp_id}").status_code == 302
    assert seen and "http://bbc/rss" in seen[0]
    # once the server created its database the news are fixed
    (folder / "database_server.db").write_text("")
    seen.clear()
    assert (
        http.post(f"/admin/im_news_snapshot/{exp_id}").status_code == 302 and not seen
    )
