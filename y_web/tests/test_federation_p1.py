"""P1: topic switch for microblogging, forum community, explicit dating story, link posts, topics read from member databases."""

import json
import pathlib
import sqlite3
from types import SimpleNamespace

from y_web.tests._platform_repos import platform_static_path
import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.src.federation import analytics_etl as etl  # noqa: E402
from y_web.src.federation import human_outbox as ho  # noqa: E402
from y_web.src.federation import service  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)


# -- (1) topic_migration for microblogging -----------------------------------------------------------------------
def test_microblogging_gets_topic_migration_false_only_when_the_admin_opted_out(world):
    app, exps, _ = world
    on = service.create_federation("p1-on", list(exps.values()))
    sections = {
        row.platform_type: service.member_section(on, row, exp)
        for row, exp in service.members_of(on)
    }
    assert (
        "topic_migration" not in sections["microblogging"]
    )  # default: the runtime's own default (on)
    service.delete_federation(on)
    off = service.create_federation(
        "p1-off", list(exps.values()), options={"topics": {"migration": False}}
    )
    sections = {
        row.platform_type: service.member_section(off, row, exp)
        for row, exp in service.members_of(off)
    }
    assert (
        sections["microblogging"]["topic_migration"] is False
        and sections["forum"]["topic_migration"] is False
    )


# -- (2) forum community --------------------------------------------------------------------------------------------
class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data


class _Session:
    def __init__(self, data, status=200):
        self.data, self.status, self.urls = data, status, []

    def get(self, url, timeout=0):
        self.urls.append(url)
        return _Resp(self.data, self.status)


def _exp(tmp_path, monkeypatch):
    cfg = tmp_path / "config_server.json"
    cfg.write_text(json.dumps({"host": "127.0.0.1", "port": 5099}))
    monkeypatch.setattr(service, "server_config_path", lambda exp: cfg)
    return SimpleNamespace(idexp=1)


def test_the_community_slug_becomes_the_topic_name_the_forum_server_lists(
    tmp_path, monkeypatch
):
    exp = _exp(tmp_path, monkeypatch)
    session = _Session(
        [{"id": 1, "name": "Climate Change"}, {"id": 2, "name": "music"}]
    )
    assert ho.forum_community(exp, "climate-change", session) == "Climate Change"
    assert ho.forum_community(exp, "r/music", session) == "music"
    assert session.urls[0] == "http://127.0.0.1:5099/get_topics"
    assert ho.forum_community(exp, "", session) is None
    assert (
        ho.forum_community(exp, "not-a-topic", session) is None
    )  # a community that is not a topic: the default board


def test_an_unreachable_forum_server_means_the_default_community(tmp_path, monkeypatch):
    exp = _exp(tmp_path, monkeypatch)
    assert ho.forum_community(exp, "music", _Session([], status=500)) is None

    class Down:
        def get(self, *a, **k):
            raise OSError("down")

    assert ho.forum_community(exp, "music", Down()) is None


def test_forum_post_carries_the_community_only_when_there_is_one():
    assert (
        ho.forum_post("t", [{"member": "m", "text": "x"}], "Music")["community"]
        == "Music"
    )
    assert "community" not in ho.forum_post("t", [{"member": "m", "text": "x"}])
    assert "community" not in ho.forum_post("t", [], None)


# -- (3) dating story ----------------------------------------------------------------------------------------------
def test_the_dating_route_sends_the_story_only_with_the_explicit_choice():
    text = pathlib.Path(
        "external/YDating/ysocial_platform/routes/social_dating_participant.py"
    ).read_text(encoding="utf-8")
    assert (
        "MESSAGE_ACTIONS" in text
        and "STORY_EVENTS" in text
        and 'item["story"] = {"event": event}' in text
    )
    assert (
        '"after_date_continue"' in text
        and '"after_date_ghost"' in text
        and '"after_date_close"' in text
    )


def test_the_dating_composer_has_the_explicit_story_choice_for_enrolled_people_only():
    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader("y_web/templates"), autoescape=True
    )
    env.globals.update(_=lambda s, **k: s)
    env.globals["ws_destinations"] = lambda exp_id: []
    assert (
        env.get_template("shared/world_simulation_dating_story.html")
        .render(ws_exp=1)
        .strip()
        == ""
    )
    env.globals["ws_destinations"] = lambda exp_id: [
        {"member": "forum", "platform_type": "forum"}
    ]
    html = env.get_template("shared/world_simulation_dating_story.html").render(
        ws_exp=1
    )
    for event in ("after_date_continue", "after_date_ghost", "after_date_close"):
        assert f'value="{event}"' in html
    assert 'id="ws-dating-story"' in html and 'id="ws-dating-story-text"' in html
    base = pathlib.Path(
        "external/YDating/ysocial_platform/templates/participant/base.html"
    )
    if base.exists():  # the page belongs to the YDating repository
        assert "shared/world_simulation_dating_story.html" in base.read_text(
            encoding="utf-8"
        )
    js = platform_static_path("YDating", "js/dating-participant.js").read_text(
        encoding="utf-8"
    )
    assert "item.story = { event: storyEl.value }" in js and "isMessage" in js


def _dating_items(monkeypatch, raw_actions):
    """Run the dating act route logic through its action cleaning with a fake targets function."""
    from y_web.routes.social import dating_participant as dp

    monkeypatch.setattr(
        ho,
        "targets_for_request",
        lambda exp_id, user, requested, story: (
            [{"member": "forum", "text": story}] if story else []
        ),
    )
    clean = []
    for (
        raw
    ) in (
        raw_actions
    ):  # same branch as the route (kept in step by the source test above)
        kind, payload = raw["type"], raw.get("payload") or {}
        item = {"type": kind, "payload": payload}
        event = (
            (raw.get("story") or {}).get("event")
            if isinstance(raw.get("story"), dict)
            else None
        )
        event = event if event in dp.STORY_EVENTS else None
        if kind in dp.MESSAGE_ACTIONS:
            story = (raw.get("crosspost_text") or "") if event else ""
        else:
            story = raw.get("crosspost_text") or payload.get("text") or ""
        targets = (
            ho.targets_for_request(1, None, ["forum"], story)
            if story or kind not in dp.MESSAGE_ACTIONS
            else []
        )
        if targets:
            item["crosspost_to"] = targets
            if event:
                item["story"] = {"event": event}
        clean.append(item)
    return clean


def test_a_message_is_never_shared_without_the_story_choice_and_the_persons_words(
    monkeypatch,
):
    out = _dating_items(
        monkeypatch,
        [
            {
                "type": "SEND_MESSAGE",
                "payload": {"text": "private"},
                "crosspost": ["forum"],
            },
            {
                "type": "SEND_MESSAGE",
                "payload": {"text": "private"},
                "crosspost": ["forum"],
                "story": {"event": "after_date_ghost"},
            },
            {
                "type": "SEND_MESSAGE",
                "payload": {"text": "private"},
                "crosspost": ["forum"],
                "story": {"event": "after_date_ghost"},
                "crosspost_text": "He never wrote back.",
            },
            {
                "type": "SEND_MESSAGE",
                "payload": {"text": "private"},
                "crosspost": ["forum"],
                "story": {"event": "bogus"},
                "crosspost_text": "x",
            },
        ],
    )
    assert [("crosspost_to" in i, i.get("story")) for i in out] == [
        (False, None),
        (False, None),
        (True, {"event": "after_date_ghost"}),
        (False, None),
    ]
    assert out[2]["crosspost_to"][0]["text"] == "He never wrote back."


# -- (4) link posts ---------------------------------------------------------------------------------------------------
def test_link_and_image_link_posts_hide_the_also_post_on_box():
    js = pathlib.Path("y_web/static/assets/js/world-simulation-crosspost.js").read_text(
        encoding="utf-8"
    )
    assert (
        "#link_post" in js
        and "#link-url" in js
        and "#image-url" in js
        and "data-ws-crosspost" in js
    )
    for route in (
        "y_web/routes/interactions/forum.py",
        "y_web/routes/interactions/microblogging.py",
    ):
        assert "if not url" in pathlib.Path(route).read_text(
            encoding="utf-8"
        )  # a link post keeps the direct path


# -- (5) topics from the member databases ---------------------------------------------------------------------------------
def send(db, n, tick, source, target, ref, gid, topics=()):
    body = {
        "source_ref": ref,
        "global_agent_id": gid,
        "text_excerpt": "x",
        "topics": list(topics),
    }
    db.execute(
        "INSERT INTO federation_message VALUES (?,?,?,?,?,?,?)",
        (f"1:{n}", source, target, tick, tick + 1, "crosspost.v1", json.dumps(body)),
    )


@pytest.fixture()
def run(tmp_path):
    db = sqlite3.connect(tmp_path / "federation.db", isolation_level=None)
    db.executescript(SCHEMA)
    send(
        db,
        0,
        5,
        "micro",
        "forum",
        "ysocial://1/micro/post/1",
        "a1",
        ["Climate", "music"],
    )
    send(db, 1, 30, "micro", "dating", "ysocial://1/micro/post/2", "a1", ["climate"])
    db.close()
    forum = sqlite3.connect(
        tmp_path / "forum.db"
    )  # the forum runtime's tables (names as YServerReddit writes them)
    forum.executescript(
        "CREATE TABLE federation_topic (name VARCHAR(20) PRIMARY KEY, created_tick INTEGER, source_member VARCHAR(64));"
        "CREATE TABLE federation_topic_origin (original VARCHAR(400) PRIMARY KEY, name VARCHAR(20), source_member VARCHAR(64));"
        "INSERT INTO federation_topic VALUES ('climate', 6, 'micro');"
        "INSERT INTO federation_topic VALUES ('a very long topic na~1f2e', 7, 'micro');"
        "INSERT INTO federation_topic_origin VALUES ('a very long topic name that is cut', 'a very long topic na~1f2e', 'micro');"
    )
    forum.commit()
    forum.close()
    micro = sqlite3.connect(
        tmp_path / "micro.db"
    )  # YServer: extra columns, a different origin table
    micro.executescript(
        "CREATE TABLE federation_topic (name VARCHAR(20) PRIMARY KEY, interest_id INTEGER, created_tick INTEGER, source_member VARCHAR(64));"
        "INSERT INTO federation_topic VALUES ('music', 4, 31, 'forum');"
    )
    micro.commit()
    micro.close()
    return str(tmp_path), {
        "forum": str(tmp_path / "forum.db"),
        "micro": str(tmp_path / "micro.db"),
        "dating": str(tmp_path / "missing.db"),
    }


def rows(folder, table):
    return etl.table_rows(folder, table)[1]


def test_topics_created_are_read_from_the_member_databases_read_only(run):
    folder, dbs = run
    before = {
        p: pathlib.Path(p).stat().st_mtime_ns
        for p in dbs.values()
        if pathlib.Path(p).exists()
    }
    assert etl.build(folder, dbs)["ok"]
    assert rows(folder, "topics_created") == [  # sorted by topic, then platform
        (
            "a very long topic na~1f2e",
            "forum",
            0,
            "micro",
            "a very long topic name that is cut",
        ),
        ("climate", "forum", 0, "micro", "climate"),
        ("music", "micro", 1, "forum", "music"),
    ]
    assert before == {
        p: pathlib.Path(p).stat().st_mtime_ns for p in before
    }  # nothing written


def test_diffusion_counts_platforms_carried_and_first_ticks(run):
    folder, dbs = run
    etl.build(folder, dbs)
    by_topic = {r[0]: r for r in rows(folder, "topic_diffusion")}
    # climate: micro (source), forum (received, also created there), dating (received); 2 cross-posts carried it
    assert by_topic["climate"] == ("climate", 3, 2, 1, 0, 1)
    # music: micro (source) and forum (received); created on micro on day 1, where it was already known
    assert by_topic["music"] == ("music", 2, 1, 1, 0, 0)
    assert (
        by_topic["a very long topic na~1f2e"][2] == 0
    )  # created on arrival under a shortened name, never carried by name
    first = {
        (t, m): (tick, via) for t, m, tick, via in rows(folder, "topic_first_seen")
    }
    assert first[("climate", "micro")] == (5, "source") and first[
        ("climate", "forum")
    ] == (6, "received")
    assert first[("climate", "dating")] == (31, "received")
    assert first[("music", "micro")] == (
        5,
        "source",
    )  # the earlier sighting wins over the later creation


def test_without_reachable_member_databases_the_creation_tables_are_empty_and_the_rest_still_works(
    run,
):
    folder, _ = run
    assert etl.build(folder)["ok"]
    assert rows(folder, "topics_created") == []
    by_topic = {r[0]: r for r in rows(folder, "topic_diffusion")}
    assert by_topic["climate"][3] == 0 and by_topic["climate"][2] == 2
    assert (
        etl.build(folder, {"forum": "/nonexistent/db"})["ok"]
        and rows(folder, "topics_created") == []
    )


def test_the_new_tables_are_exported_and_documented():
    for table in ("topics_created", "topic_first_seen", "topic_diffusion"):
        assert table in etl.EXPORT_TABLES and table in etl.render_field_map()


def test_the_analytics_routes_hand_the_member_databases_to_the_etl():
    text = pathlib.Path("y_web/routes/admin/sub/world_simulation.py").read_text(
        encoding="utf-8"
    )
    assert text.count("service.member_databases(fed)") >= 3
