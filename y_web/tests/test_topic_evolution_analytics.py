import importlib
import sqlite3

import pytest

opinion_module = importlib.import_module("y_web.routes.admin.sub.experiments._opinion")


pytestmark = pytest.mark.unit


def test_topic_evolution_tracks_volume_population_share_and_lifecycle(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "topic_evolution.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE user_mgmt (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL
            );
            CREATE TABLE rounds (
                id TEXT PRIMARY KEY,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL
            );
            CREATE TABLE post (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                round TEXT NOT NULL
            );
            CREATE TABLE post_topics (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                topic_id TEXT NOT NULL
            );
            CREATE TABLE reactions (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                round TEXT NOT NULL
            );
            CREATE TABLE reported (
                id TEXT PRIMARY KEY,
                to_post TEXT NOT NULL,
                from_uid TEXT NOT NULL,
                tid TEXT NOT NULL
            );
            CREATE TABLE interests (
                iid TEXT PRIMARY KEY,
                interest TEXT NOT NULL
            );
            """)
        conn.executemany(
            "INSERT INTO user_mgmt(id, username) VALUES (?, ?)",
            [("u1", "alice"), ("u2", "bob"), ("u3", "carol"), ("u4", "dave")],
        )
        conn.executemany(
            "INSERT INTO rounds(id, day, hour) VALUES (?, ?, ?)",
            [("r1", 1, 1), ("r2", 2, 1), ("r3", 3, 1)],
        )
        conn.executemany(
            "INSERT INTO interests(iid, interest) VALUES (?, ?)",
            [("t1", "Climate"), ("t2", "Robotics")],
        )
        conn.executemany(
            "INSERT INTO post(id, user_id, round) VALUES (?, ?, ?)",
            [("p1", "u1", "r1"), ("p2", "u2", "r2"), ("p3", "u3", "r3")],
        )
        conn.executemany(
            "INSERT INTO post_topics(id, post_id, topic_id) VALUES (?, ?, ?)",
            [("pt1", "p1", "t1"), ("pt2", "p2", "t1"), ("pt3", "p3", "t2")],
        )
        conn.executemany(
            "INSERT INTO reactions(id, post_id, user_id, round) VALUES (?, ?, ?, ?)",
            [("re1", "p1", "u2", "r1"), ("re2", "p2", "u3", "r2")],
        )
        conn.execute(
            "INSERT INTO reported(id, to_post, from_uid, tid) VALUES (?, ?, ?, ?)",
            ("rp1", "p2", "u4", "r2"),
        )
        conn.commit()

    monkeypatch.setattr(
        opinion_module,
        "_topic_name_mapping",
        lambda expid, conn: {"t1": "Climate", "t2": "Robotics"},
    )

    analytics = opinion_module._build_topic_evolution_payload(
        1,
        str(db_path),
        filter_day=3,
        filter_hour=1,
        selected_topic_ids=["t1", "t2"],
    )

    assert analytics["distribution"]["labels"] == ["Climate", "Robotics"]
    assert analytics["distribution"]["datasets"][0]["data"] == [5, 1]
    assert analytics["trend_mode"] == "daily"
    assert analytics["trend"]["type"] == "heatmap"
    assert analytics["secondary"]["type"] == "heatmap"
    assert analytics["trend"]["labels"] == ["Day 1", "Day 2", "Day 3"]
    assert analytics["trend"]["row_labels"] == ["Climate", "Robotics"]
    climate_day_2 = next(
        cell for cell in analytics["trend"]["cells"]
        if cell["topic_label"] == "Climate" and cell["time_label"] == "Day 2"
    )
    robotics_day_3 = next(
        cell for cell in analytics["trend"]["cells"]
        if cell["topic_label"] == "Robotics" and cell["time_label"] == "Day 3"
    )
    assert climate_day_2["actual"] == 3
    assert climate_day_2["intensity"] == 1.0
    assert robotics_day_3["actual"] == 1
    reach_day_2 = next(
        cell for cell in analytics["secondary"]["cells"]
        if cell["topic_label"] == "Climate" and cell["time_label"] == "Day 2"
    )
    assert reach_day_2["actual"] == 3
    assert reach_day_2["percent"] == 75.0
    assert analytics["topic_lifecycle"]["labels"] == ["Day 1", "Day 2", "Day 3"]
    assert analytics["topic_lifecycle"]["datasets"][0]["data"] == [1, 1, 1]
    assert analytics["topic_lifecycle"]["datasets"][1]["data"] == [1, 0, 1]
    assert analytics["topic_lifecycle"]["datasets"][2]["data"] == [0, 1, 1]
    assert analytics["summary"]["rows"][0][0] == "Climate"
    assert analytics["summary"]["rows"][0][3] == 5
    assert analytics["summary"]["rows"][0][5] == "100.0%"
    assert analytics["selected_topic_ids"] == ["t1", "t2"]


def test_topic_evolution_supports_cumulative_trends(tmp_path, monkeypatch):
    db_path = tmp_path / "topic_evolution_cumulative.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE user_mgmt (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL
            );
            CREATE TABLE rounds (
                id TEXT PRIMARY KEY,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL
            );
            CREATE TABLE post (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                round TEXT NOT NULL
            );
            CREATE TABLE post_topics (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                topic_id TEXT NOT NULL
            );
            """)
        conn.executemany(
            "INSERT INTO user_mgmt(id, username) VALUES (?, ?)",
            [("u1", "alice"), ("u2", "bob"), ("u3", "carol"), ("u4", "dave")],
        )
        conn.executemany(
            "INSERT INTO rounds(id, day, hour) VALUES (?, ?, ?)",
            [("r1", 1, 1), ("r2", 2, 1), ("r3", 3, 1)],
        )
        conn.executemany(
            "INSERT INTO post(id, user_id, round) VALUES (?, ?, ?)",
            [("p1", "u1", "r1"), ("p2", "u2", "r2"), ("p3", "u1", "r3")],
        )
        conn.executemany(
            "INSERT INTO post_topics(id, post_id, topic_id) VALUES (?, ?, ?)",
            [("pt1", "p1", "t1"), ("pt2", "p2", "t1"), ("pt3", "p3", "t1")],
        )
        conn.commit()

    monkeypatch.setattr(
        opinion_module,
        "_topic_name_mapping",
        lambda expid, conn: {"t1": "Climate"},
    )

    analytics = opinion_module._build_topic_evolution_payload(
        1,
        str(db_path),
        filter_day=3,
        filter_hour=1,
        selected_topic_ids=["t1"],
        trend_mode="cumulative",
    )

    assert analytics["trend_mode"] == "cumulative"
    assert analytics["trend"]["datasets"][0]["data"] == [1, 2, 3]
    assert analytics["secondary"]["datasets"][0]["data"] == [25.0, 50.0, 50.0]
    assert "Cumulative" in analytics["trend"]["description"]
    assert "Cumulative" in analytics["secondary"]["description"]
