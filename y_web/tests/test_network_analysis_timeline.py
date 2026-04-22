import sqlite3

import pytest

from y_web.routes.admin.sub.experiments._opinion import _build_network_analytics_payload


pytestmark = pytest.mark.unit


def test_network_analysis_extends_flat_timeline_after_last_follow_event(tmp_path):
    db_path = tmp_path / "network.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_mgmt (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL
            );
            CREATE TABLE rounds (
                id TEXT PRIMARY KEY,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL
            );
            CREATE TABLE follow (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                follower_id TEXT NOT NULL,
                action TEXT,
                round TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO user_mgmt(id, username) VALUES (?, ?)",
            [("u1", "alice"), ("u2", "bob")],
        )
        conn.executemany(
            "INSERT INTO rounds(id, day, hour) VALUES (?, ?, ?)",
            [("r1", 1, 1), ("r2", 2, 1), ("r3", 3, 1)],
        )
        conn.execute(
            "INSERT INTO follow(id, user_id, follower_id, action, round) VALUES (?, ?, ?, ?, ?)",
            ("f1", "u2", "u1", "follow", "r1"),
        )
        conn.commit()

    analytics = _build_network_analytics_payload(str(db_path), filter_day=3, filter_hour=1)

    assert analytics["secondary"]["labels"] == ["Day 1", "Day 2", "Day 3"]
    assert analytics["secondary"]["datasets"][1]["data"] == [1, 1, 1]
    assert analytics["secondary"]["labels"] == ["Day 1", "Day 2", "Day 3"]
    assert analytics["component_share"]["labels"] == ["Day 1", "Day 2", "Day 3"]
    assert analytics["granularity"] == "day"
    assert analytics["distribution"]["options"]["xType"] == "logarithmic"
    assert analytics["trend"]["options"]["yType"] == "logarithmic"


def test_network_analysis_supports_mention_network(tmp_path):
    db_path = tmp_path / "mention_network.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
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
            CREATE TABLE mentions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                post_id TEXT NOT NULL,
                round TEXT NOT NULL,
                answered INTEGER
            );
            """
        )
        conn.executemany(
            "INSERT INTO user_mgmt(id, username) VALUES (?, ?)",
            [("u1", "alice"), ("u2", "bob"), ("u3", "carol")],
        )
        conn.executemany(
            "INSERT INTO rounds(id, day, hour) VALUES (?, ?, ?)",
            [("r1", 1, 1), ("r2", 2, 1), ("r3", 3, 1)],
        )
        conn.executemany(
            "INSERT INTO post(id, user_id, round) VALUES (?, ?, ?)",
            [("p1", "u1", "r1"), ("p2", "u2", "r2")],
        )
        conn.executemany(
            "INSERT INTO mentions(id, user_id, post_id, round, answered) VALUES (?, ?, ?, ?, ?)",
            [("m1", "u2", "p1", "r1", 0), ("m2", "u3", "p2", "r2", 0)],
        )
        conn.commit()

    analytics = _build_network_analytics_payload(
        str(db_path), filter_day=3, filter_hour=1, network_type="mention"
    )

    assert analytics["network_type"] == "mention"
    assert analytics["description"] == "Track how the mention network evolves across the experiment."
    assert analytics["secondary"]["datasets"][1]["label"] == "Mention Edges"
    assert analytics["secondary"]["datasets"][1]["data"] == [1, 2, 2]
    assert analytics["ego_network"]["title"] == "Mention Network Ego Network Over Time"


def test_network_analysis_supports_hourly_granularity(tmp_path):
    db_path = tmp_path / "hourly_network.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_mgmt (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL
            );
            CREATE TABLE rounds (
                id TEXT PRIMARY KEY,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL
            );
            CREATE TABLE follow (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                follower_id TEXT NOT NULL,
                action TEXT,
                round TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO user_mgmt(id, username) VALUES (?, ?)",
            [("u1", "alice"), ("u2", "bob")],
        )
        conn.executemany(
            "INSERT INTO rounds(id, day, hour) VALUES (?, ?, ?)",
            [("r1", 1, 1), ("r2", 1, 2), ("r3", 1, 3)],
        )
        conn.executemany(
            "INSERT INTO follow(id, user_id, follower_id, action, round) VALUES (?, ?, ?, ?, ?)",
            [("f1", "u2", "u1", "follow", "r1"), ("f2", "u1", "u2", "follow", "r3")],
        )
        conn.commit()

    analytics = _build_network_analytics_payload(
        str(db_path), filter_day=1, filter_hour=3, granularity="hour"
    )

    assert analytics["granularity"] == "hour"
    assert analytics["secondary"]["labels"] == ["Day 1, Hour 1", "Day 1, Hour 2", "Day 1, Hour 3"]
    assert analytics["secondary"]["datasets"][1]["data"] == [1, 1, 2]


def test_ego_network_includes_alter_alter_edges(tmp_path):
    db_path = tmp_path / "ego_network.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_mgmt (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL
            );
            CREATE TABLE rounds (
                id TEXT PRIMARY KEY,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL
            );
            CREATE TABLE follow (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                follower_id TEXT NOT NULL,
                action TEXT,
                round TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO user_mgmt(id, username) VALUES (?, ?)",
            [("u1", "alice"), ("u2", "bob"), ("u3", "carol")],
        )
        conn.executemany(
            "INSERT INTO rounds(id, day, hour) VALUES (?, ?, ?)",
            [("r1", 1, 1), ("r2", 1, 2), ("r3", 1, 3)],
        )
        conn.executemany(
            "INSERT INTO follow(id, user_id, follower_id, action, round) VALUES (?, ?, ?, ?, ?)",
            [
                ("f1", "u2", "u1", "follow", "r1"),
                ("f2", "u3", "u1", "follow", "r1"),
                ("f3", "u3", "u2", "follow", "r2"),
            ],
        )
        conn.commit()

    analytics = _build_network_analytics_payload(
        str(db_path), filter_day=1, filter_hour=3, selected_uid="u1"
    )

    rendered_edges = {
        tuple(sorted((edge["source"], edge["target"])))
        for edge in analytics["ego_network"]["edges"]
    }
    assert ("u1", "u2") in rendered_edges
    assert ("u1", "u3") in rendered_edges
    assert ("u2", "u3") in rendered_edges
