"""F7.1: the derived analytics of a World Simulation equal a by-hand computation on a small run; the build is
deterministic, never writes the coordinator database and keeps the previous file when it fails."""

import hashlib
import json
import os
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.src.federation import analytics_etl as etl  # noqa: E402


def membership(db, tick, gid, member, old, new, reason="join"):
    db.execute("INSERT INTO federation_event (tick, kind, detail_json, at) VALUES (?,?,?,0)",
               (tick, "membership_change", json.dumps({"global_agent_id": gid, "member": member, "from": old, "to": new,
                                                       "reason": reason})))


def crosspost(db, n, source_ref, target, tick):
    db.execute("INSERT INTO federation_message VALUES (?,?,?,?,?,?,?)",
               (f"1:{n}", "coordinator", target, tick, tick + 1, "crosspost.v1",
                json.dumps({"source_ref": source_ref, "text_excerpt": "x"})))


@pytest.fixture()
def folder(tmp_path):
    db = sqlite3.connect(tmp_path / "federation.db", isolation_level=None)
    db.executescript(SCHEMA)
    # attention: day 0 a1 splits 0.5/0.5, a2 only on forum; day 1 only micro
    for gid, member, day, w in (("a1", "micro", 0, .5), ("a1", "forum", 0, .5), ("a2", "forum", 0, 1.0),
                                ("a1", "micro", 1, 1.0), ("a2", "forum", 1, 0.0)):
        db.execute("INSERT INTO federation_attention VALUES (?,?,?,?,1.0)", (gid, member, day, w))
    # a1 leaves micro on day 1 and joins forum the same day; a2 joins dating with no previous leave on day 2
    membership(db, 30, "a1", "micro", "active", "left", "churn")
    membership(db, 31, "a1", "forum", "dormant", "active")
    membership(db, 50, "a2", "dating", "dormant", "active")
    ref = "ysocial://1/micro/post/7"
    crosspost(db, 0, ref, "forum", 5)
    crosspost(db, 1, ref, "dating", 5)
    crosspost(db, 2, "ysocial://1/forum/post/3", "micro", 30)
    for member, day, gid in (("micro", 0, "a1"), ("micro", 0, "a2"), ("micro", 1, "a1"), ("forum", 0, "a1")):
        db.execute("INSERT INTO federation_affective VALUES (?,?,?,0,0,0,0)", (member, day, gid))
    db.close()
    return str(tmp_path)


def rows(folder, table):
    return etl.table_rows(folder, table)[1]


def test_the_derived_tables_equal_a_computation_by_hand(folder):
    assert etl.build(folder)["ok"]
    assert rows(folder, "daily_attention") == [(0, "forum", 2, 1.5, .75), (0, "micro", 1, .5, .25), (1, "micro", 1, 1.0, 1.0)]
    assert rows(folder, "migration_flows") == [(1, "micro", "forum", 1), (2, etl.NEW, "dating", 1)]
    assert rows(folder, "crosspost_flows") == [(0, "micro", "dating", 1), (0, "micro", "forum", 1), (1, "forum", "micro", 1)]
    assert rows(folder, "cascades") == [("ysocial://1/forum/post/3", "forum", 1, 1, 1), ("ysocial://1/micro/post/7", "micro", 0, 2, 2)]
    assert rows(folder, "survival") == [(0, "forum", 1, 0, 1.0), (0, "micro", 2, 0, 1.0), (1, "micro", 1, 1, .5)]


def test_two_builds_give_the_same_rows_and_the_source_is_untouched(folder):
    digest = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
    before = digest(os.path.join(folder, "federation.db"))
    etl.build(folder)
    first = {t: rows(folder, t) for t in etl.EXPORT_TABLES}
    etl.build(folder)
    assert {t: rows(folder, t) for t in etl.EXPORT_TABLES} == first
    assert digest(os.path.join(folder, "federation.db")) == before


def test_state_goes_from_never_to_fresh_to_stale(folder):
    assert etl.read_state(folder)["state"] == "never"
    assert etl.ensure_derived(folder)["state"] == "fresh" and etl.read_state(folder)["last_day"] == 1
    db = sqlite3.connect(os.path.join(folder, "federation.db"), isolation_level=None)
    crosspost(db, 9, "ysocial://1/micro/post/9", "forum", 60)
    db.close()
    assert etl.read_state(folder)["state"] == "stale"
    assert etl.ensure_derived(folder)["state"] == "fresh" and etl.read_state(folder)["last_day"] == 2


def test_a_failed_build_keeps_the_previous_file_and_a_missing_source_is_reported(folder, tmp_path_factory):
    etl.build(folder)
    kept = {t: rows(folder, t) for t in etl.EXPORT_TABLES}
    with open(os.path.join(folder, "federation.db"), "wb") as handle:
        handle.write(b"not a database")
    res = etl.build(folder)
    assert not res["ok"] and etl.read_state(folder)["state"] == "failed"
    assert {t: rows(folder, t) for t in etl.EXPORT_TABLES} == kept
    empty = str(tmp_path_factory.mktemp("empty"))
    assert etl.build(empty)["ok"] is False and etl.cards(empty)["tables"] == {}


def test_cards_and_field_map(folder):
    cards = etl.cards(folder)
    assert set(cards["tables"]) == set(etl.FIELD_MAP) and cards["state"]["state"] == "fresh"
    assert cards["tables"]["survival"][2] == {"day": 1, "member": "micro", "active": 1, "left": 1, "survival": .5}
    with pytest.raises(KeyError):
        etl.table_rows(folder, "sqlite_master")
    for table, (_d, _s, cols) in etl.FIELD_MAP.items():
        assert f"### `{table}`" in etl.render_field_map() and cols
