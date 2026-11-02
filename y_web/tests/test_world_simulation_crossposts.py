"""World Simulation: platforms are named after their experiments in the frontends, the Cross-posts tab (real links, search,
paging, CSV) and the cross-posting statistics of the Agents tab. Everything is keyed by member; the experiments are called
XW and FW (never like their platform type) so a type leaking into a label is caught."""

import csv
import io
import json
import os
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import agent_states as ast, backlinks as bl, crossposts as cps, names, quotes  # noqa: E402
from y_web.tests.test_federation_backlinks import activate, server_db  # noqa: E402
from y_web.tests.test_federation_humans import Offline, make, user  # noqa: E402,F401
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_ui import login, site  # noqa: E402,F401  (fixtures)

QUOTED = {"author_name": "bob", "global_agent_id": "g2", "member": "forum", "source_ref": "ysocial://1/forum/post/10", "text_excerpt": "x"}


def payload(gid, ref, text, **extra):
    return json.dumps({"global_agent_id": gid, "source_ref": ref, "kind": "post", "text_excerpt": text, "image_ref": None,
                       "topics": [], "lang": "en", "target_account_id": "1", **extra})


def rename(exps):
    from y_web import db
    from y_web.src.models.admin import Exps

    db.session.get(Exps, exps["microblogging"]).exp_name = "XW"
    db.session.get(Exps, exps["forum"]).exp_name = "FW"
    db.session.commit()


def coordinator(fed, messages, deliveries, extra=0):
    """federation.db with ``(fed_msg_id, source, target, tick, payload)`` messages, ``(fed_msg_id, target, acked)`` deliveries,
    the identities of alice (g1) and bob (g2) and ``extra`` more forum -> microblogging cross-posts of alice."""
    conn = sqlite3.connect(os.path.join(fed.folder, "federation.db"))
    conn.executescript(
        "CREATE TABLE federation_message (fed_msg_id TEXT PRIMARY KEY, source_member TEXT, target_member TEXT, tick_emitted INTEGER,"
        " deliver_at_tick INTEGER, payload_type TEXT, payload_json TEXT);"
        "CREATE TABLE federation_delivery (fed_msg_id TEXT, target_member TEXT, acked_tick INTEGER, UNIQUE (fed_msg_id, target_member));"
        "CREATE TABLE federation_identity (global_agent_id TEXT, member TEXT, local_account_id TEXT, state TEXT, joined_tick INTEGER, left_tick INTEGER);"
        "CREATE TABLE federation_identity_kind (global_agent_id TEXT PRIMARY KEY, kind TEXT);"
        "CREATE TABLE federation_agent_name (global_agent_id TEXT PRIMARY KEY, name TEXT);")
    for n in range(extra):
        messages.append((f"x{n}", "forum", "microblogging", 100 + n, payload("g1", "ysocial://1/forum/post/11", f"bulk {n}")))
        deliveries.append((f"x{n}", "microblogging", 101 + n))
    conn.executemany("INSERT INTO federation_message VALUES (?,?,?,?,?,'crosspost.v1',?)", [(a, b, c, d, d + 1, e) for a, b, c, d, e in messages])
    conn.execute("INSERT INTO federation_message VALUES ('e1','microblogging','coordinator',3,4,'exposure.v1','{}')")
    conn.executemany("INSERT INTO federation_delivery VALUES (?,?,?)", deliveries)
    conn.executemany("INSERT INTO federation_identity VALUES (?,?,?,'active',0,NULL)",
                     [("g1", "forum", "1"), ("g1", "microblogging", "1"), ("g2", "forum", "2"), ("g2", "microblogging", "2")])
    conn.executemany("INSERT INTO federation_agent_name VALUES (?,?)", [("g1", "Alice Agent"), ("g2", "Bob Agent")])
    conn.commit()
    conn.close()


def link_agents(fed):
    """YWeb knows alice (g1) and bob (g2) on both members (the rows of the Agents tab come from these links)."""
    from y_web import db
    from y_web.src.models.admin import FederationIdentityLink

    db.session.add_all([FederationIdentityLink(federation_pk=fed.id, global_agent_id=g, member=m, local_account_id=a)
                        for g, m, a in (("g1", "forum", "1"), ("g1", "microblogging", "1"), ("g2", "forum", "2"), ("g2", "microblogging", "2"))])
    db.session.commit()


MESSAGES = [
    ("m1", "forum", "microblogging", 3, payload("g2", "ysocial://1/forum/post/10", "Inflation talk")),
    ("m2", "forum", "microblogging", 5, payload("g1", "ysocial://1/forum/post/11", "hello world")),
    ("m3", "forum", "microblogging", 30, payload("g1", "ysocial://1/forum/post/12", "Third post")),
    ("m4", "microblogging", "forum", 26, payload("g1", "ysocial://1/microblogging/post/20", "from micro")),
    ("m5", "forum", "microblogging", 6, payload("g1", "ysocial://1/forum/post/11", "sharing bob", quoted=QUOTED)),
    ("m6", "coordinator", "forum", 50, payload("g2", "ysocial://1/microblogging/post/21", "rule based")),
]
DELIVERIES = [("m1", "microblogging", 4), ("m2", "microblogging", 6), ("m4", "forum", 27), ("m5", "microblogging", 7), ("m6", "forum", 51)]


@pytest.fixture
def cw(world):  # noqa: F811
    """A World Simulation with experiments XW (microblogging, id 1) and FW (forum, id 2), both frontends active, and the
    cross-posts above (alice = g1, bob = g2)."""
    fed, tmp = make(world)
    app, exps, _ = world
    rename(exps)
    server_db(tmp, "forum", posts=[(10, 2), (11, 1), (12, 1), (30, 1), (31, 2)],
              refs=[("post", 30, "ysocial://1/microblogging/post/20"), ("post", 31, "ysocial://1/microblogging/post/21")])
    server_db(tmp, "microblogging", posts=[(13, 2), (14, 1), (15, 1), (20, 1), (21, 2)],
              refs=[("post", 13, "ysocial://1/forum/post/10"), ("post", 14, "ysocial://1/forum/post/11"), ("post", 15, "ysocial://1/forum/post/11")])
    # the copies are found by fed_msg_id (m1, m4, m6) or, failing that, by source_ref (m2); the federation_ref of server_db names them m<n>
    conn = sqlite3.connect(tmp / "experiments" / "microblogging" / "database_server.db")
    conn.execute("UPDATE federation_ref SET fed_msg_id = 'm1' WHERE local_id = 13")
    conn.execute("UPDATE federation_ref SET fed_msg_id = 'zz2' WHERE local_id = 14")  # m2: unknown fed_msg_id, found by source_ref
    conn.execute("UPDATE federation_ref SET fed_msg_id = 'm5' WHERE local_id = 15")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(tmp / "experiments" / "forum" / "database_server.db")
    conn.execute("UPDATE federation_ref SET fed_msg_id = 'm4' WHERE local_id = 30")
    conn.execute("UPDATE federation_ref SET fed_msg_id = 'm6' WHERE local_id = 31")
    conn.commit()
    conn.close()
    activate(app, exps, forum=1, microblogging=1)
    coordinator(fed, list(MESSAGES), list(DELIVERIES))
    link_agents(fed)
    return fed, exps, tmp


def f(**kw):
    return cps.parse_filters(kw, ["forum", "microblogging"])


def by_id(result):
    return {r["fed_msg_id"]: r for r in result["rows"]}


# ----------------------------------------------------------------------------------- (1) names, not types
def test_backlinks_name_the_experiment_and_keep_the_type_as_the_icon(cw):
    _, exps, _ = cw
    origin = bl.origin_for(exps["microblogging"], 13)
    assert origin["label"] == "FW" and origin["icon"] == "message-square" and origin["platform_type"] == "forum" and origin["exp_name"] == "FW"
    copies = bl.copies_for(exps["forum"], 10)
    assert [(c["member"], c["label"], c["icon"]) for c in copies] == [("microblogging", "XW", "message-circle")]


def test_the_origin_partial_shows_names_not_types(cw):
    from jinja2 import Environment, FileSystemLoader

    _, exps, _ = cw
    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")))
    env.globals.update(ws_origin=bl.origin_for, ws_copies=bl.copies_for, _=lambda s, **k: s % k if k else s)
    tpl = "{% set ws_exp = " + str(exps["microblogging"]) + " %}{% set ws_id = 13 %}{% include 'shared/world_simulation_origin.html' %}"
    html = env.from_string(tpl).render()
    assert "<strong>FW</strong>" in html and "Forum" not in html and "forum<" not in html and "<svg" in html
    tpl = "{% set ws_exp = " + str(exps["forum"]) + " %}{% set ws_id = 10 %}{% include 'shared/world_simulation_origin.html' %}"
    html = env.from_string(tpl).render()
    assert "<strong>XW</strong>" in html and "Microblogging" not in html


def test_profile_badges_show_the_experiment_name(world):  # noqa: F811
    from y_web.tests.test_federation_profile_badges import accounts, bind_all, first_agent, open_interfaces
    from y_web.src.federation import profile_badges as pb

    fed, _ = make(world)
    _, exps, _ = world
    rename(exps)
    open_interfaces(exps["microblogging"])
    gid = first_agent(fed)
    acc = accounts(fed, gid)
    bind_all(fed)
    badge = pb.badges_for(exps["forum"], acc["forum"])[0]
    assert badge["label"] == "XW" and badge["platform_type"] == "microblogging" and badge["icon"] == "message-circle"
    assert badge["href"] == f"/{exps['microblogging']}/profile/{acc['microblogging']}/recent/1"


def test_quotes_and_pending_notices_name_the_experiment(cw, tmp_path):
    from y_web.src.federation import pending_notice

    fed, exps, _ = cw
    assert quotes.platform_label("forum", {"forum": "FW"}) == "FW" and quotes.platform_label("forum") == "Forum"
    path = tmp_path / "q.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE federation_quoted (post_id INTEGER, author_name TEXT, member TEXT, text_excerpt TEXT, source_ref TEXT)")
    conn.execute("INSERT INTO federation_quoted VALUES (7, 'ann', 'forum', 'words', NULL)")
    conn.commit()
    conn.close()
    assert quotes.read_quotes(str(path), names.names_of(fed.id))["7"]["platform"] == "FW"
    line = pending_notice._line({"text_excerpt": "t", "source_member": "forum", "quoted": {"author_name": "ann", "member": "microblogging"}},
                                names.names_of(fed.id))
    assert line["source"] == "FW" and "@ XW" in line["attribution"]


def test_the_composer_offers_the_experiment_names(world):  # noqa: F811
    import jinja2

    from y_web import db
    from y_web.src.federation import humans, human_outbox
    from y_web.src.models import Admin_users

    fed, _ = make(world)
    _, exps, _ = world
    rename(exps)
    db.session.add(Admin_users(id=7, username="giulio", email="g@x.org", password="x", role="researcher", last_seen="2026-01-01"))
    db.session.commit()
    humans.enrol(fed, user(), ["forum", "microblogging"], offline=Offline())
    dests = human_outbox.destinations_for(exps["forum"], 7)
    assert dests == [{"member": "microblogging", "platform_type": "microblogging", "label": "XW"}]
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")), autoescape=True)
    env.globals.update(ws_destinations=lambda e: dests, _=lambda s, **k: s % k if k else s, url_for=lambda endpoint, **k: "/s/" + k["filename"])
    html = env.get_template("shared/world_simulation_crosspost.html").render(ws_exp=1)
    assert "XW" in html and "Microblogging" not in html and 'value="microblogging"' in html  # the value stays the member


def test_names_fall_back_to_the_member_and_outside_a_world_there_are_none(world):  # noqa: F811
    _, exps, _ = world
    assert names.world_names(exps["forum"]) == {} and names.world_names(None) == {}
    assert names.label_of({"a": "AA"}, "a") == "AA" and names.label_of({}, "photo_sharing") == "Photo sharing"


# ----------------------------------------------------------------------------------- (2) the Cross-posts table
def test_rows_have_real_links_and_names(cw):
    fed, exps, _ = cw
    rows = by_id(cps.search(fed, f()))
    assert set(rows) == {"m1", "m2", "m3", "m4", "m5", "m6"}  # exposure.v1 is not a cross-post
    m1 = rows["m1"]
    assert (m1["day"], m1["slot"], m1["tick"]) == (0, 3, 3) and m1["author"] == "bob" and m1["delivered"] is True
    assert m1["origin"]["href"] == f"/{exps['forum']}/rthread/10" and m1["origin"]["exp_name"] == "FW" and m1["origin"]["icon"] == "message-square"
    assert m1["destination"]["href"] == f"/{exps['microblogging']}/thread/13" and m1["destination"]["exp_name"] == "XW"
    assert m1["author_href"] == f"/{exps['forum']}/profile/2/recent/1" and m1["mode"] == "agent_action"
    assert rows["m2"]["destination"]["href"] == f"/{exps['microblogging']}/thread/14"  # found by source_ref
    assert rows["m4"]["origin"]["href"] == f"/{exps['microblogging']}/thread/20" and rows["m4"]["destination"]["href"] == f"/{exps['forum']}/rthread/30"
    assert rows["m6"]["mode"] == "coordinator_rule" and rows["m6"]["origin"]["member"] == "microblogging"  # origin from the source_ref
    assert rows["m5"]["shared"] is True and rows["m5"]["shared_from"] == "bob" and rows["m1"]["shared"] is False
    assert (rows["m3"]["delivered"], rows["m3"]["destination"]["href"], rows["m3"]["destination"]["available"]) == (False, None, False)


def test_links_only_when_the_frontend_is_active(cw):
    fed, exps, _ = cw
    from y_web import db
    from y_web.src.models.admin import Exps

    db.session.get(Exps, exps["microblogging"]).status = 0
    db.session.commit()
    m1 = by_id(cps.search(fed, f()))["m1"]
    assert m1["origin"]["href"] is not None and m1["origin"]["active"] is True
    assert m1["destination"]["href"] is None and m1["destination"]["active"] is False and m1["destination"]["id"] == "13"
    m4 = by_id(cps.search(fed, f()))["m4"]
    assert m4["origin"]["href"] is None and m4["author_href"] is None and m4["destination"]["href"] is not None


def test_a_removed_origin_and_a_missing_copy_have_no_link(cw):
    fed, exps, tmp = cw
    conn = sqlite3.connect(tmp / "experiments" / "forum" / "database_server.db")
    conn.execute("DELETE FROM post WHERE id = 10")
    conn.commit()
    conn.close()
    m1 = by_id(cps.search(fed, f()))["m1"]
    assert m1["origin"]["href"] is None and m1["origin"]["available"] is False
    assert m1["author"] == "Bob Agent"  # the name of the agent when the author cannot be read from the content
    assert m1["destination"]["href"] is not None


def test_search_by_text_and_by_author(cw):
    fed, _, _ = cw
    assert set(by_id(cps.search(fed, f(q="inflation")))) == {"m1"}
    assert set(by_id(cps.search(fed, f(q="bob")))) == {"m1", "m6"} | {"m5"}  # bob's own and the text of the share that names bob
    assert set(by_id(cps.search(fed, f(q="ALICE")))) == {"m2", "m3", "m4", "m5"}  # the username in the platform database
    assert set(by_id(cps.search(fed, f(q="Bob Agent")))) == {"m1", "m6"}  # the name of the agent
    assert cps.search(fed, f(q="%"))["total"] == 0 and cps.search(fed, f(q="g2"))["total"] == 2


def test_filters_by_experiment_agent_state_mode_and_ticks(cw):
    fed, _, _ = cw
    ids = lambda **kw: set(by_id(cps.search(fed, f(**kw))))  # noqa: E731
    assert ids(source="microblogging") == {"m4", "m6"} and ids(source="forum") == {"m1", "m2", "m3", "m5"}
    assert ids(destination="forum") == {"m4", "m6"} and ids(source="forum", destination="forum") == set()
    assert ids(agent="g2") == {"m1", "m6"} and ids(status="pending") == {"m3"} and ids(status="delivered") == {"m1", "m2", "m4", "m5", "m6"}
    assert ids(mode="coordinator_rule") == {"m6"} and ids(mode="agent_action") == {"m1", "m2", "m3", "m4", "m5"}
    assert ids(tick_from="5", tick_to="26") == {"m2", "m4", "m5"} and ids(tick_from="x") == set(MESSAGES_IDS)
    assert ids(ref="ysocial://1/forum/post/11") == {"m2", "m5"}
    assert ids(source="nope") == set(MESSAGES_IDS)  # an unknown experiment is ignored
    assert ids(source="forum", status="delivered", q="hello") == {"m2"}


MESSAGES_IDS = [m[0] for m in MESSAGES]


def test_order_and_paging(world):  # noqa: F811
    fed, tmp = make(world)
    _, exps, _ = world
    rename(exps)
    server_db(tmp, "forum", posts=[(11, 1)])
    server_db(tmp, "microblogging", posts=[(1, 1)])
    coordinator(fed, [], [], extra=60)
    total = cps.search(fed, f())
    assert total["total"] == 60 and len(total["rows"]) == 25 and total["rows"][0]["tick"] == 159  # newest first by default
    assert [r["tick"] for r in cps.search(fed, f(sort="tick_asc"))["rows"]][:2] == [100, 101]
    p3 = cps.search(fed, f(size="25", page="3"))
    assert [len(p3["rows"]), p3["rows"][0]["tick"]] == [10, 109]
    assert len(cps.search(fed, f(size="100"))["rows"]) == 60 and len(cps.search(fed, f(size="7"))["rows"]) == 25  # sizes: 25/50/100
    assert len(cps.search(fed, f(size="50"))["rows"]) == 50
    assert cps.search(fed, f(page="99999999"))["rows"] == []  # the offset is bounded, not an error
    assert len(cps.export_rows(fed, f(q="bulk 1"))) == 11  # bulk 1, bulk 10 .. bulk 19


def test_no_database_or_tables_means_no_rows(world):  # noqa: F811
    fed, _ = make(world)
    assert cps.search(fed, f()) == {"rows": [], "total": 0, "capped": False, "available": False}
    sqlite3.connect(os.path.join(fed.folder, "federation.db")).close()
    assert cps.search(fed, f())["rows"] == [] and cps.search(fed, f())["total"] == 0


def test_the_database_is_never_written(cw):
    fed, _, _ = cw
    path = os.path.join(fed.folder, "federation.db")
    before = os.stat(path).st_mtime_ns
    cps.search(fed, f(q="alice"))
    assert os.stat(path).st_mtime_ns == before and not os.path.exists(path + "-wal")


def test_query_args_keep_only_what_is_set():
    assert cps.query_args(f(q="x", size="50", sort="tick_asc")) == {"q": "x", "size": 50, "sort": "tick_asc"}
    assert cps.query_args(f()) == {} and cps.query_args(f(q="x"), agent="g1") == {"q": "x", "agent": "g1"}


def test_the_page_the_pager_the_links_and_the_csv(site):
    app, exps, tmp = site
    fed, _ = make(site)
    rename(exps)
    server_db(tmp, "forum", posts=[(10, 2), (11, 1), (12, 1)])
    server_db(tmp, "microblogging", posts=[(13, 2)], refs=[("post", 13, "ysocial://1/forum/post/10")])
    conn = sqlite3.connect(tmp / "experiments" / "microblogging" / "database_server.db")
    conn.execute("UPDATE federation_ref SET fed_msg_id = 'm1'")
    conn.commit()
    conn.close()
    activate(app, exps, forum=1, microblogging=0)
    coordinator(fed, [MESSAGES[0], MESSAGES[1]], [DELIVERIES[0], DELIVERIES[1]], extra=30)
    client = login(app, "admin")
    base = f"/admin/world_simulation/{fed.id}/crossposts"
    html = client.get(base + "?sort=tick_asc").get_data(as_text=True)
    assert 'id="ws-crossposts-table"' in html and 'title="FW"' in html and 'title="XW' in html
    assert f'href="/{exps["forum"]}/rthread/10"' in html  # the origin is active
    assert "the web interface of this experiment is not active" in html  # the destination is not
    assert "Page 1 of 2" in html and "sort=tick_asc" in html and "32 cross-posts" in html
    filtered = client.get(base + "?q=bulk&status=delivered&size=50").get_data(as_text=True)
    assert "30 cross-posts" in filtered
    assert 'name="q" value="bulk"' in filtered and "bulk 3" in filtered and "hello world" not in filtered
    assert "q=bulk" in filtered and "/crossposts.csv?" in filtered
    two = client.get(base + "?page=2").get_data(as_text=True)
    assert "Page 2 of 2" in two and "q=" not in two.split("ws-pager")[1].split("</p>")[0]
    assert client.get(base + "?page=-4&size=oops&sort=zzz").status_code == 200  # tolerant
    got = client.get(base + ".csv?q=hello")
    assert got.mimetype == "text/csv"
    lines = list(csv.reader(io.StringIO(got.get_data(as_text=True))))
    assert lines[0] == cps.CSV_COLUMNS and len(lines) == 2
    row = dict(zip(lines[0], lines[1]))
    assert row["author"] == "alice" and row["origin_experiment"] == "FW" and row["destination_experiment"] == "XW"
    assert row["origin_platform"] == "forum" and row["delivered"] == "yes" and row["text"] == "hello world"
    assert row["origin_url"] == f"/{exps['forum']}/rthread/11" and row["destination_url"] == ""  # inactive destination
    assert len(list(csv.reader(io.StringIO(client.get(base + ".csv").get_data(as_text=True))))) == 33
    assert client.get("/admin/world_simulation/99999/crossposts").status_code == 404
    assert 'href="' + base + '"' in html  # the tab is in the tab bar


def test_the_cascades_table_links_to_the_filtered_tab():
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "assets", "js", "admin-world-simulation.js"), encoding="utf-8").read()
    html = open(os.path.join(os.path.dirname(__file__), "..", "templates", "admin", "world_simulation", "detail.html"), encoding="utf-8").read()
    assert "?ref=' + encodeURIComponent" in js and 'data-crossposts-url="{{ url_for(\'world_simulation.crossposts\'' in html


# ----------------------------------------------------------------------------------- (3) statistics per agent
def test_statistics_count_own_shared_and_delivered_copies(cw):
    fed, _, _ = cw
    stats = ast._stats(fed.folder)
    assert stats["g1"] == {"made_own": 3, "made_others": 1, "times": 2, "by_dest": {"forum": 1, "microblogging": 1}}
    assert stats["g2"] == {"made_own": 2, "made_others": 0, "times": 2, "by_dest": {"forum": 1, "microblogging": 1}}
    assert ast._stats(os.path.join(fed.folder, "missing")) is None


def test_the_table_carries_the_statistics_and_filters_and_sorts_by_them(cw):
    fed, _, _ = cw
    data = ast.table(fed)
    assert data["stats_available"] is True and data["names"] == {"forum": "FW", "microblogging": "XW"}
    by = {r["id"]: r for r in data["rows"]}
    assert by["g1"]["stats"]["made_own"] == 3 and by["g2"]["stats"]["times"] == 2
    zero = [r for r in data["rows"] if r["id"] not in ("g1", "g2")]
    assert all(r["stats"] == ast.NO_STATS for r in zero)
    assert {r["id"] for r in ast.filtered(data, activity="made")} == {"g1", "g2"} and {r["id"] for r in ast.filtered(data, activity="crossposted")} == {"g1", "g2"}
    assert {r["id"] for r in ast.filtered(data, activity="none")} == {r["id"] for r in zero}
    assert [r["id"] for r in ast.sorted_rows(ast.filtered(data, activity="made"), "made_own")] == ["g1", "g2"]
    assert [r["id"] for r in ast.sorted_rows(ast.filtered(data, activity="made"), "made_own", "asc")] == ["g2", "g1"]
    assert [r["id"] for r in ast.sorted_rows(ast.filtered(data, activity="made"), "made_others")][0] == "g1"
    assert ast.sorted_rows(data["rows"], "nope") == data["rows"] and ast.sorted_rows(data["rows"]) == data["rows"]


def test_without_the_message_tables_the_statistics_are_zero_and_marked_unavailable(world):  # noqa: F811
    from y_web.tests.test_world_simulation_agents import coordinator as identities_only

    fed, _ = make(world)
    identities_only(fed, [])
    data = ast.table(fed)
    assert data["stats_available"] is False and all(r["stats"] == ast.NO_STATS for r in data["rows"])


def test_the_agents_page_shows_the_columns_and_the_csv_has_them(site, monkeypatch):
    app, exps, tmp = site
    fed, _ = make(site)
    rename(exps)
    coordinator(fed, list(MESSAGES), list(DELIVERIES))
    link_agents(fed)
    client = login(app, "admin")
    base = f"/admin/world_simulation/{fed.id}/agents"
    html = client.get(base).get_data(as_text=True)
    assert 'data-stat="made_own"' in html and 'data-stat="made_others"' in html and 'data-stat="times"' in html
    assert "sort=made_own" in html and "FW: 1; XW: 1" in html and f"/crossposts?agent=g1&amp;status=delivered" in html
    only = client.get(base + "?activity=made&sort=times&dir=desc").get_data(as_text=True)
    assert "activity=made" in only and only.count('data-stat="made_own"') == 2 and "No account matches" not in only
    none = client.get(base + "?activity=none").get_data(as_text=True)
    assert 'data-stat="made_own">0<' in none and 'data-stat="made_own">3<' not in none
    lines = list(csv.reader(io.StringIO(client.get(base + ".csv").get_data(as_text=True))))
    assert lines[0][-4:] == ["crossposts_own", "crossposts_of_others", "times_crossposted", "times_crossposted_by_destination"]
    g1 = [dict(zip(lines[0], l)) for l in lines[1:] if l[0] == "g1"]
    assert g1 and all((r["crossposts_own"], r["crossposts_of_others"], r["times_crossposted"]) == ("3", "1", "2") for r in g1)
    assert g1[0]["times_crossposted_by_destination"] == "FW: 1; XW: 1"
