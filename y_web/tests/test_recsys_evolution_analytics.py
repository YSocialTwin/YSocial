import sqlite3

import pytest

from y_web.routes.admin.sub.experiments._opinion import _build_recsys_evolution_payload

pytestmark = pytest.mark.unit


def test_recsys_evolution_tracks_recommendation_distributions_and_author_reach(
    tmp_path,
):
    db_path = tmp_path / "recsys_evolution.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE user_mgmt (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                recsys_type TEXT
            );
            CREATE TABLE rounds (
                id TEXT PRIMARY KEY,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL
            );
            CREATE TABLE post (
                id TEXT PRIMARY KEY,
                tweet TEXT,
                user_id TEXT NOT NULL,
                round TEXT NOT NULL
            );
            CREATE TABLE recommendations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                post_ids TEXT,
                round TEXT NOT NULL
            );
            CREATE TABLE follow (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                follower_id TEXT NOT NULL,
                action TEXT,
                round TEXT NOT NULL
            );
        """)
        conn.executemany(
            "INSERT INTO user_mgmt(id, username, recsys_type) VALUES (?, ?, ?)",
            [
                ("u1", "alice", "ReverseChronoFollowersPopularity"),
                ("u2", "bob", "random"),
                ("u3", "carol", "ReverseChronoFollowersPopularity"),
                ("u4", "dave", "random"),
            ],
        )
        conn.executemany(
            "INSERT INTO rounds(id, day, hour) VALUES (?, ?, ?)",
            [("r1", 1, 1), ("r2", 2, 1), ("r3", 3, 1)],
        )
        conn.executemany(
            "INSERT INTO post(id, tweet, user_id, round) VALUES (?, ?, ?, ?)",
            [
                ("p1", "first post", "u1", "r1"),
                ("p2", "second post", "u1", "r2"),
                ("p3", "third post", "u2", "r2"),
            ],
        )
        conn.executemany(
            "INSERT INTO recommendations(id, user_id, post_ids, round) VALUES (?, ?, ?, ?)",
            [
                ("rec1", "u3", "p1|p3", "r1"),
                ("rec2", "u4", "p1|p2", "r2"),
                ("rec3", "u2", "p2", "r3"),
            ],
        )
        conn.executemany(
            "INSERT INTO follow(id, user_id, follower_id, action, round) VALUES (?, ?, ?, ?, ?)",
            [
                ("f1", "u2", "u1", "follow", "r1"),
                ("f2", "u1", "u3", "follow", "r1"),
            ],
        )
        conn.commit()

    analytics = _build_recsys_evolution_payload(
        str(db_path),
        filter_day=3,
        filter_hour=1,
        selected_author_uid="u1",
    )

    assert analytics["distribution"]["labels"] == [
        "random",
        "ReverseChronoFollowersPopularity",
    ]
    assert analytics["distribution"]["datasets"][0]["data"] == [2, 1]
    assert analytics["trend"]["labels"] == ["1", "2"]
    assert analytics["trend"]["datasets"][0]["data"] == [1, 2]
    assert analytics["secondary"]["labels"] == ["alice", "bob"]
    assert analytics["secondary"]["datasets"][0]["data"] == [4, 1]
    assert analytics["summary"]["rows"][0][0] == "alice"
    assert analytics["summary"]["rows"][0][1] == 4
    assert analytics["summary"]["rows"][0][2] == 3

    author_panel = analytics["recsys_author"]
    assert author_panel["selected_username"] == "alice"
    assert author_panel["unique_recipients"] == 3
    assert author_panel["total_recommendations"] == 4
    assert author_panel["recommended_posts"] == 2
    assert author_panel["followers_count"] == 1
    assert author_panel["followees_count"] == 1
    assert author_panel["reach_trend"]["labels"] == ["Day 1", "Day 2", "Day 3"]
    assert author_panel["reach_trend"]["datasets"][0]["data"] == [1, 2, 3]
    assert (
        author_panel["reach_trend"]["datasets"][1]["label"]
        == "Avg. Reach of People Following This Author"
    )
    assert author_panel["reach_trend"]["datasets"][1]["data"] == [1.0, 1.0, 1.0]
    assert (
        author_panel["reach_trend"]["datasets"][2]["label"]
        == "Avg. Reach of People This Author Follows"
    )
    assert author_panel["reach_trend"]["datasets"][2]["data"] == [0.0, 0.0, 0.0]
    assert author_panel["receiver_diversity_trend"]["labels"] == [
        "Day 1",
        "Day 2",
        "Day 3",
    ]
    assert (
        author_panel["receiver_diversity_trend"]["datasets"][0]["label"]
        == "Selected User"
    )
    assert author_panel["receiver_diversity_trend"]["datasets"][0]["data"] == [0, 0, 0]
    assert (
        author_panel["receiver_diversity_trend"]["datasets"][1]["label"]
        == "Avg. Diversity of People Following This Author"
    )
    assert author_panel["receiver_diversity_trend"]["datasets"][1]["data"] == [
        0.0,
        0.0,
        1.0,
    ]
    assert (
        author_panel["receiver_diversity_trend"]["datasets"][2]["label"]
        == "Avg. Diversity of People This Author Follows"
    )
    assert author_panel["receiver_diversity_trend"]["datasets"][2]["data"] == [
        2.0,
        2.0,
        2.0,
    ]
    assert author_panel["post_distribution"]["type"] == "line"
    assert author_panel["post_distribution"]["labels"] == []
    assert author_panel["post_distribution"]["options"]["xType"] == "linear"
    assert (
        author_panel["post_distribution"]["options"]["xTitle"] == "Recommendation Count"
    )
    assert author_panel["post_distribution"]["options"]["yTitle"] == "Density"
    assert author_panel["post_distribution"]["datasets"][0]["label"] == "Density"
    assert author_panel["post_distribution"]["datasets"][0]["data"]
    first_point = author_panel["post_distribution"]["datasets"][0]["data"][0]
    assert set(first_point.keys()) == {"x", "y"}
    assert author_panel["summary_rows"][0][0] == "p1"
    assert author_panel["summary_rows"][0][2] == 2
