"""Back-links of cross-posted content: where a post comes from and where it was copied to (read-only, never breaks a page)."""

import os
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from y_web.src.federation import backlinks as bl  # noqa: E402
from y_web.tests.test_federation_humans import make  # noqa: E402,F401
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)

TEMPLATES = os.path.join(os.path.dirname(__file__), "..", "templates")


def server_db(tmp, platform, posts=(), refs=(), users=((1, "alice"), (2, "bob"))):
    """A minimal runtime database: user_mgmt, post (id, user_id) and federation_ref rows ``(kind, local id, source_ref)``."""
    path = tmp / "experiments" / platform / "database_server.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE user_mgmt (id INTEGER PRIMARY KEY, username TEXT)")
    conn.execute("CREATE TABLE post (id INTEGER PRIMARY KEY, user_id INTEGER, tweet TEXT)")
    conn.execute("CREATE TABLE federation_ref (local_kind TEXT, local_id INTEGER, source_ref TEXT, fed_msg_id TEXT)")
    conn.executemany("INSERT INTO user_mgmt VALUES (?,?)", users)
    conn.executemany("INSERT INTO post VALUES (?,?,'t')", posts)
    conn.executemany("INSERT INTO federation_ref VALUES (?,?,?,?)", [(k, i, r, f"m{n}") for n, (k, i, r) in enumerate(refs)])
    conn.commit()
    conn.close()
    return path


def activate(app, exps, **status):
    from y_web import db
    from y_web.src.models.admin import Exps

    for name, value in status.items():
        db.session.get(Exps, exps[name]).status = value
    db.session.commit()


@pytest.fixture
def crossposted(world):
    """Forum post 10 (by bob) was copied to the microblogging post 13; forum post 11 was never copied."""
    fed, tmp = make(world)
    app, exps, _ = world
    server_db(tmp, "forum", posts=[(10, 2), (11, 1)])
    server_db(tmp, "microblogging", posts=[(13, 1), (14, 2)], refs=[("post", 13, "ysocial://1/forum/post/10")])
    activate(app, exps, forum=1, microblogging=1)
    return app, exps, tmp


def test_a_copy_knows_where_it_comes_from(crossposted):
    _, exps, _ = crossposted
    origin = bl.origin_for(exps["microblogging"], 13)
    assert origin["member"] == "forum" and origin["label"] == "Forum" and origin["icon"] == "message-square"
    assert origin["author"] == "bob" and origin["exp_name"] == "forum" and origin["id"] == "10"
    assert origin["href"] == f"/{exps['forum']}/rthread/10" and origin["available"] is True


def test_the_original_knows_where_it_was_copied(crossposted):
    _, exps, _ = crossposted
    copies = bl.copies_for(exps["forum"], 10)
    assert [(c["member"], c["label"], c["href"]) for c in copies] == [
        ("microblogging", "Microblogging", f"/{exps['microblogging']}/thread/13")]
    assert bl.copies_for(exps["forum"], 11) == []


def test_content_that_was_not_cross_posted_has_nothing(crossposted):
    _, exps, _ = crossposted
    assert bl.origin_for(exps["microblogging"], 14) is None and bl.origin_for(exps["forum"], 10) is None
    assert bl.origin_for(exps["microblogging"], None) is None and bl.copies_for(exps["forum"], None) == []


def test_nothing_outside_a_world_simulation(world):
    _, exps, _ = world
    assert bl.origin_for(exps["forum"], 1) is None and bl.copies_for(exps["forum"], 1) == []
    assert bl.origin_for(None, 1) is None and bl.origin_for(99999, 1) is None


def test_a_removed_origin_is_shown_without_link(world):
    fed, tmp = make(world)
    app, exps, _ = world
    server_db(tmp, "forum", posts=[])  # post 10 was removed
    server_db(tmp, "microblogging", posts=[(13, 1)], refs=[("post", 13, "ysocial://1/forum/post/10")])
    activate(app, exps, forum=1, microblogging=1)
    origin = bl.origin_for(exps["microblogging"], 13)
    assert origin["label"] == "Forum" and origin["href"] is None and origin["author"] is None and origin["available"] is False


def test_an_origin_whose_frontend_is_not_active_has_no_link(crossposted):
    app, exps, _ = crossposted
    activate(app, exps, forum=0)
    origin = bl.origin_for(exps["microblogging"], 13)
    assert origin["label"] == "Forum" and origin["author"] == "bob" and origin["href"] is None
    activate(app, exps, forum=1, microblogging=0)  # an inactive destination does not hide the link to an active copy's page
    assert bl.copies_for(exps["forum"], 10)[0]["href"] is None


def test_one_original_with_several_destinations(world):
    from y_web import db
    from y_web.src.models.admin import Exps, FederationMember

    fed, tmp = make(world)
    app, exps, _ = world
    exp = Exps(platform_type="photo_sharing", exp_name="photo", db_name="experiments/photo/db.db", owner="admin", exp_descr="",
               status=1, running=0, port=5002, simulator_type="Standard", exp_status="stopped")
    db.session.add(exp)
    db.session.flush()
    db.session.add(FederationMember(federation_pk=fed.id, exp_id=exp.idexp, member="photo", platform_type="photo_sharing", position=2))
    db.session.commit()
    (tmp / "experiments" / "photo").mkdir()
    server_db(tmp, "forum", posts=[(10, 2)])
    server_db(tmp, "microblogging", posts=[(13, 1)], refs=[("post", 13, "ysocial://1/forum/post/10")])
    path = tmp / "experiments" / "photo" / "database_server.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE user_mgmt (id TEXT PRIMARY KEY, username TEXT)")
    conn.execute("CREATE TABLE photos (id TEXT PRIMARY KEY, user_id TEXT)")
    conn.execute("CREATE TABLE federation_ref (local_kind TEXT, local_id TEXT, source_ref TEXT, fed_msg_id TEXT)")
    conn.execute("INSERT INTO user_mgmt VALUES ('u1','carol')")
    conn.execute("INSERT INTO photos VALUES ('p1','u1')")
    conn.execute("INSERT INTO federation_ref VALUES ('photo','p1','ysocial://1/forum/post/10','m9')")
    conn.commit()
    conn.close()
    activate(app, exps, forum=1, microblogging=1)
    copies = bl.copies_for(exps["forum"], 10)
    assert [c["member"] for c in copies] == ["microblogging", "photo"]
    assert copies[1]["href"] == f"/{exp.idexp}/photo/profile/u1/recent/1#feed-post-p1" and copies[1]["icon"] == "camera"
    origin = bl.origin_for(exp.idexp, "p1")
    assert origin["member"] == "forum" and origin["href"] == f"/{exps['forum']}/rthread/10"


def test_the_sdk_missing_gives_nothing_and_touches_no_database(crossposted, monkeypatch):
    from y_web.src.federation import availability

    _, exps, _ = crossposted
    monkeypatch.setattr(availability, "sdk_available", lambda refresh=False: False)
    monkeypatch.setattr(bl, "_query", lambda *a, **k: pytest.fail("a database was read"))
    assert bl.origin_for(exps["microblogging"], 13) is None and bl.copies_for(exps["forum"], 10) == []


def test_missing_tables_or_files_never_raise(world):
    fed, tmp = make(world)
    _, exps, _ = world
    assert bl.origin_for(exps["microblogging"], 13) is None and bl.copies_for(exps["forum"], 10) == []  # no database at all
    (tmp / "experiments" / "microblogging" / "database_server.db").write_bytes(b"not a database")
    assert bl.origin_for(exps["microblogging"], 13) is None


def test_a_page_asks_once_per_experiment_not_once_per_post(crossposted, monkeypatch):
    app, exps, tmp = crossposted
    calls = []
    real = bl._query
    monkeypatch.setattr(bl, "_query", lambda path, sql, params=(): calls.append(sql) or real(path, sql, params))
    with app.test_request_context("/"):
        for post_id in range(1, 60):
            bl.origin_for(exps["microblogging"], post_id)
            bl.copies_for(exps["microblogging"], post_id)
    first = len(calls)
    assert 0 < first <= 6  # federation_ref + authors of the origins + copies of the other member, whatever the posts
    with app.test_request_context("/"):
        bl.origin_for(exps["microblogging"], 13)
        n = len(calls)
        bl.origin_for(exps["microblogging"], 14)
    assert len(calls) == n


def test_the_databases_are_only_read(crossposted):
    _, exps, tmp = crossposted
    paths = [tmp / "experiments" / p / "database_server.db" for p in ("forum", "microblogging")]
    before = [p.stat().st_mtime_ns for p in paths]
    bl.origin_for(exps["microblogging"], 13)
    bl.copies_for(exps["forum"], 10)
    assert [p.stat().st_mtime_ns for p in paths] == before


def test_unreadable_source_refs_are_ignored():
    assert bl.parse_ref("ysocial://1/forum/post/10") == ("forum", "post", "10")
    assert bl.parse_ref("nonsense") is None and bl.parse_ref(None) is None


def test_the_address_of_each_platform():
    assert bl.content_href("microblogging", 3, 7) == "/3/thread/7"
    assert bl.content_href("forum", 3, 7) == "/3/rthread/7"
    assert bl.content_href("instant_messaging", 3, "m1") == "/3/im/thread/m1"
    assert bl.content_href("photo_sharing", 3, "p1", "u1") == "/3/photo/profile/u1/recent/1#feed-post-p1"
    assert bl.content_href("photo_sharing", 3, "p1") is None and bl.content_href("dating", 3, 1) is None


# ---------------------------------------------------------------------------------------------------------- partial
def render(origin=None, copies=(), quote=None):
    env = Environment(loader=FileSystemLoader(TEMPLATES))
    env.globals.update(ws_origin=lambda e, i: origin, ws_copies=lambda e, i: list(copies),
                       federation_quote=lambda e, i: quote, _=lambda s, **k: s % k if k else s)
    return env.from_string("{% set ws_exp = 1 %}{% set ws_id = 5 %}{% include 'shared/world_simulation_origin.html' %}").render()


FORUM = {"member": "forum", "label": "Forum", "icon": "message-square", "author": "bob", "href": "/2/rthread/10"}
MICRO = {"member": "microblogging", "label": "Microblogging", "icon": "message-circle", "href": "/1/thread/13"}


def test_the_partial_links_a_copy_to_its_original():
    html = render(origin=FORUM)
    assert "Cross-posted from" in html and 'href="/2/rthread/10"' in html and "@bob" in html and "Forum" in html and "<svg" in html
    assert "Cross-posted to" not in html


def test_the_partial_shows_the_label_without_link_when_the_original_is_not_reachable():
    html = render(origin=dict(FORUM, href=None, author=None))
    assert "Forum" in html and "<a " not in html and "@" not in html and "The original is not available" in html


def test_the_partial_lists_every_copy_of_an_original():
    html = render(copies=[MICRO, dict(MICRO, member="photo", label="Photo sharing", icon="camera", href="/3/photo/profile/u/recent/1#feed-post-p")])
    assert html.count('class="ws-copy-link"') == 2 and "Cross-posted to" in html and 'href="/1/thread/13"' in html
    assert "Cross-posted from" not in html


def test_a_quoted_share_keeps_its_own_attribution_only():
    assert "Cross-posted from" not in render(origin=FORUM, quote={"author_name": "x"})
    assert render(origin=FORUM, quote=None).count("Cross-posted from") == 1


def test_the_partial_is_empty_for_other_content():
    assert render().strip() == ""


@pytest.mark.parametrize("name,key", [("microblogging/components/posts.html", "item['post_id']"),
                                      ("microblogging/components/thread-post.html", "thread['post_id']"),
                                      ("forum/components/posts.html", "item['post_id']"),
                                      ("forum/components/thread-post.html", "thread['post_id']"),
                                      ("photo/components/posts.html", "item['post_id']"),
                                      ("im/_message.html", "m.id")])
def test_every_post_card_includes_the_back_link(name, key):
    text = open(os.path.join(TEMPLATES, name), encoding="utf-8").read()
    assert "{% set ws_id = " + key + " %}{% include 'shared/world_simulation_origin.html' %}" in text
    assert text.index("federation_quote_block(") < text.index("world_simulation_origin.html")  # quote block first


def test_the_template_functions_are_registered():
    text = open(os.path.join(os.path.dirname(__file__), "..", "__init__.py"), encoding="utf-8").read()
    assert 'app.jinja_env.globals["ws_origin"] = _ws_origin' in text and 'app.jinja_env.globals["ws_copies"] = _ws_copies' in text
    assert "except Exception" in text[text.index("def _ws_origin"):text.index('globals["ws_origin"]')]  # a page never fails


def test_the_italian_strings_are_translated():
    from babel.messages.pofile import read_po

    po = read_po(open(os.path.join(os.path.dirname(__file__), "..", "translations", "it", "LC_MESSAGES", "messages.po"), "rb"))
    for msgid in ("Cross-posted from", "Cross-posted to", "Open the original on %(platform)s",
                  "Open the copy on %(platform)s", "The original is not available"):
        message = po.get(msgid)
        assert message is not None and message.string and message.string != msgid, msgid
