"""H8: the analytics tell what people did (cross-posts under a human:<id> identity) and leave the agents' tables as they were."""

import json
import sqlite3

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.src.federation import analytics_etl as etl  # noqa: E402


def xp(db, n, source, target, tick, gid, ref, quoted=None, topics=()):
    body = {"global_agent_id": gid, "source_ref": ref, "text_excerpt": "x", "topics": list(topics)}
    if quoted:
        body["quoted"] = quoted
    db.execute("INSERT INTO federation_message VALUES (?,?,?,?,?,?,?)",
               (f"1:{source}:{n}", source, target, tick, tick + 1, "crosspost.v1", json.dumps(body)))


@pytest.fixture()
def folder(tmp_path):
    db = sqlite3.connect(tmp_path / "federation.db", isolation_level=None)
    db.executescript(SCHEMA)
    q = {"author_name": "ann", "global_agent_id": "2", "member": "micro", "source_ref": "ysocial://1/micro/post/9", "text_excerpt": "t"}
    xp(db, 0, "forum", "micro", 5, "human:7", "ysocial://1/forum/post/1")
    xp(db, 1, "forum", "dating", 6, "human:7", "ysocial://1/forum/post/1")
    xp(db, 2, "micro", "forum", 30, "human:7", "ysocial://1/micro/post/4", quoted=q)
    xp(db, 3, "micro", "forum", 31, "human:9", "ysocial://1/micro/post/5")
    xp(db, 4, "micro", "forum", 5, "3", "ysocial://1/micro/post/6")  # an agent: never listed among the people
    db.close()
    return str(tmp_path)


def rows(folder, table):
    return etl.table_rows(folder, table)[1]


def test_people_tables_equal_a_computation_by_hand(folder):
    etl.build(folder)
    assert rows(folder, "human_crossposts") == [
        (0, "human:7", "forum", "dating", 0, 1), (0, "human:7", "forum", "micro", 0, 1),
        (1, "human:7", "micro", "forum", 1, 1), (1, "human:9", "micro", "forum", 0, 1)]
    assert rows(folder, "human_activity") == [("human:7", 3, 1, 2, 3, 0, 1), ("human:9", 1, 0, 1, 1, 1, 1)]


def test_agents_are_not_people_and_the_other_tables_still_count_everything(folder):
    etl.build(folder)
    assert all(not r[1].startswith("agent") and r[1].startswith("human:") for r in rows(folder, "human_crossposts"))
    assert sum(r[3] for r in rows(folder, "crosspost_flows")) == 5  # every cross-post, people included
    assert [r[2] for r in rows(folder, "shares")] == ["human:7"]  # the share of a person is a share like any other


def test_no_people_no_rows_and_the_field_map_documents_the_tables(tmp_path):
    db = sqlite3.connect(tmp_path / "federation.db", isolation_level=None)
    db.executescript(SCHEMA)
    xp(db, 0, "micro", "forum", 1, "3", "ysocial://1/micro/post/6")
    db.close()
    etl.build(str(tmp_path))
    assert rows(str(tmp_path), "human_crossposts") == [] and rows(str(tmp_path), "human_activity") == []
    text = etl.render_field_map()
    assert "### `human_crossposts`" in text and "### `human_activity`" in text
