"""X3.2: share chains, bridge agents and topics carried, derived from the quoted and topics of crosspost.v1."""

import json
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.src.federation import analytics_etl as etl  # noqa: E402


def send(db, n, tick, target, source_ref, gid, quoted=None, topics=()):
    body = {"source_ref": source_ref, "global_agent_id": gid, "text_excerpt": "x", "topics": list(topics)}
    if quoted:
        body["quoted"] = quoted
    db.execute("INSERT INTO federation_message VALUES (?,?,?,?,?,?,?)",
               (f"1:{n}", "micro", target, tick, tick + 1, "crosspost.v1", json.dumps(body)))


def quote(author, gid, member, ref):
    return {"author_name": author, "global_agent_id": gid, "member": member, "source_ref": ref, "text_excerpt": "t"}


@pytest.fixture()
def folder(tmp_path):
    db = sqlite3.connect(tmp_path / "federation.db", isolation_level=None)
    db.executescript(SCHEMA)
    # a plain cross-post of micro/post/1 (a2) to forum, then a1 shares it from forum to dating (depth 2),
    # then a1 shares an own-platform post of a non member (depth 1) to micro and forum
    send(db, 0, 5, "forum", "ysocial://1/micro/post/1", "a2", topics=["climate", "Music"])
    send(db, 1, 30, "dating", "ysocial://1/forum/post/9", "a1", quote("ann", "a2", "forum", "ysocial://1/micro/post/1"), topics=["climate"])
    send(db, 2, 31, "micro", "ysocial://1/forum/post/10", "a1", quote("zed", None, "forum", None))
    send(db, 3, 31, "dating", "ysocial://1/forum/post/10", "a1", quote("zed", None, "forum", None))
    db.close()
    return str(tmp_path)


def rows(folder, table):
    return etl.table_rows(folder, table)[1]


def test_shares_depth_bridges_and_topics_equal_a_computation_by_hand(folder):
    assert etl.build(folder)["ok"]
    assert rows(folder, "shares") == [
        (1, 30, "a1", "forum", "dating", "ann", "a2", "ysocial://1/micro/post/1", 2),
        (1, 31, "a1", "forum", "dating", "zed", "", "", 1),
        (1, 31, "a1", "forum", "micro", "zed", "", "", 1)]
    assert rows(folder, "share_depth") == [(1, 2), (2, 1)]
    assert rows(folder, "bridge_agents") == [("a1", 3, 1, 2)]
    assert rows(folder, "topics_carried") == [("Music", "micro", "forum", 1, 0), ("climate", "forum", "dating", 1, 1),
                                              ("climate", "micro", "forum", 1, 0)]


def test_a_run_without_shares_has_empty_share_tables(tmp_path):
    db = sqlite3.connect(tmp_path / "federation.db", isolation_level=None)
    db.executescript(SCHEMA)
    send(db, 0, 5, "forum", "ysocial://1/micro/post/1", "a2")
    db.close()
    assert etl.build(str(tmp_path))["ok"]
    assert [rows(str(tmp_path), t) for t in ("shares", "share_depth", "bridge_agents", "topics_carried")] == [[], [], [], []]


def test_an_older_derived_database_is_stale_and_rebuilt(folder):
    etl.build(folder)
    with sqlite3.connect(etl.analytics_path(folder)) as conn:
        conn.execute("UPDATE etl_state SET schema_version = 1")
    assert etl.read_state(folder)["state"] == "stale"
    assert etl.ensure_derived(folder)["state"] == "fresh"
