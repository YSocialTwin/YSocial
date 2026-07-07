import importlib
import sqlite3

import pytest

opinion_module = importlib.import_module("y_web.routes.admin.sub.experiments._opinion")
from y_web.routes.admin.sub.experiments._opinion import (
    _build_emotion_analytics_payload,
    _build_hashtag_evolution_payload,
    _build_network_analytics_payload,
    _build_recsys_evolution_payload,
    _build_topic_evolution_payload,
)

pytestmark = pytest.mark.unit


def _create_photo_sharing_analytics_db(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
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
            CREATE TABLE interests (
                iid TEXT PRIMARY KEY,
                interest TEXT NOT NULL
            );
            CREATE TABLE hashtags (
                id TEXT PRIMARY KEY,
                hashtag TEXT NOT NULL
            );
            CREATE TABLE photos (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                round TEXT NOT NULL,
                caption TEXT,
                alt_text TEXT,
                image_url TEXT
            );
            CREATE TABLE photo_topics (
                id TEXT PRIMARY KEY,
                photo_id TEXT NOT NULL,
                topic_id TEXT NOT NULL
            );
            CREATE TABLE photo_hashtags (
                id TEXT PRIMARY KEY,
                photo_id TEXT NOT NULL,
                hashtag_id TEXT NOT NULL
            );
            CREATE TABLE photo_emotions (
                id TEXT PRIMARY KEY,
                photo_id TEXT NOT NULL,
                emotion_id TEXT NOT NULL,
                score REAL,
                viral_score REAL
            );
            CREATE TABLE emotions (
                id TEXT PRIMARY KEY,
                emotion TEXT NOT NULL
            );
            CREATE TABLE recommendations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                photo_ids TEXT,
                round TEXT NOT NULL
            );
            CREATE TABLE follow (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                follower_id TEXT NOT NULL,
                action TEXT,
                round TEXT NOT NULL
            );
            CREATE TABLE mentions (
                id TEXT PRIMARY KEY,
                photo_id TEXT,
                comment_id TEXT,
                user_id TEXT NOT NULL,
                round TEXT NOT NULL
            );
            CREATE TABLE reactions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                photo_id TEXT NOT NULL,
                reaction_type TEXT,
                round TEXT NOT NULL
            );
            CREATE TABLE reported (
                id TEXT PRIMARY KEY,
                reporter_id TEXT NOT NULL,
                content_id TEXT NOT NULL,
                content_type TEXT NOT NULL,
                reason TEXT,
                round_id TEXT
            );
            """
        )
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
            [("r1", 1, 1), ("r2", 2, 1)],
        )
        conn.executemany(
            "INSERT INTO interests(iid, interest) VALUES (?, ?)",
            [("t1", "Climate"), ("t2", "Robotics")],
        )
        conn.executemany(
            "INSERT INTO hashtags(id, hashtag) VALUES (?, ?)",
            [("h1", "ClimateNow"), ("h2", "RoboticsFuture")],
        )
        conn.executemany(
            "INSERT INTO emotions(id, emotion) VALUES (?, ?)",
            [("e1", "joy"), ("e2", "surprise")],
        )
        conn.executemany(
            "INSERT INTO photos(id, user_id, round, caption, alt_text, image_url) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("p1", "u1", "r1", "first photo", "", "https://example.com/p1.jpg"),
                ("p2", "u2", "r2", "second photo", "", "https://example.com/p2.jpg"),
                ("p3", "u1", "r2", "third photo", "", "https://example.com/p3.jpg"),
            ],
        )
        conn.executemany(
            "INSERT INTO photo_topics(id, photo_id, topic_id) VALUES (?, ?, ?)",
            [("pt1", "p1", "t1"), ("pt2", "p2", "t1"), ("pt3", "p3", "t2")],
        )
        conn.executemany(
            "INSERT INTO photo_hashtags(id, photo_id, hashtag_id) VALUES (?, ?, ?)",
            [("ph1", "p1", "h1"), ("ph2", "p2", "h1"), ("ph3", "p3", "h2")],
        )
        conn.executemany(
            "INSERT INTO photo_emotions(id, photo_id, emotion_id, score, viral_score) VALUES (?, ?, ?, ?, ?)",
            [("pe1", "p1", "e1", 0.9, 0.4), ("pe2", "p2", "e1", 0.8, 0.3), ("pe3", "p3", "e2", 0.7, 0.2)],
        )
        conn.executemany(
            "INSERT INTO recommendations(id, user_id, photo_ids, round) VALUES (?, ?, ?, ?)",
            [
                ("rec1", "u3", '["p1", "p3"]', "r1"),
                ("rec2", "u4", '["p1", "p2"]', "r2"),
                ("rec3", "u2", "p2", "r2"),
            ],
        )
        conn.executemany(
            "INSERT INTO follow(id, user_id, follower_id, action, round) VALUES (?, ?, ?, ?, ?)",
            [
                ("f1", "u2", "u1", "follow", "r1"),
                ("f2", "u3", "u1", "follow", "r1"),
            ],
        )
        conn.executemany(
            "INSERT INTO mentions(id, photo_id, comment_id, user_id, round) VALUES (?, ?, ?, ?, ?)",
            [
                ("m1", "p1", None, "u2", "r1"),
                ("m2", "p2", None, "u3", "r2"),
            ],
        )
        conn.executemany(
            "INSERT INTO reactions(id, user_id, photo_id, reaction_type, round) VALUES (?, ?, ?, ?, ?)",
            [
                ("rct1", "u2", "p1", "LIKE", "r1"),
                ("rct2", "u3", "p2", "LOVE", "r2"),
            ],
        )
        conn.executemany(
            "INSERT INTO reported(id, reporter_id, content_id, content_type, reason, round_id) VALUES (?, ?, ?, ?, ?, ?)",
            [("rep1", "u4", "p2", "photo", "spam", "r2")],
        )
        conn.commit()


def test_photo_topic_and_hashtag_analytics_use_photo_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "photo_analytics.db"
    _create_photo_sharing_analytics_db(db_path)
    monkeypatch.setattr(
        opinion_module,
        "_topic_name_mapping",
        lambda expid, conn: {"t1": "Climate", "t2": "Robotics"},
    )

    topic_analytics = opinion_module._build_topic_evolution_payload(
        1,
        str(db_path),
        filter_day=2,
        filter_hour=1,
        selected_topic_ids=["t1", "t2"],
    )
    hashtag_analytics = opinion_module._build_hashtag_evolution_payload(
        str(db_path),
        filter_day=2,
        filter_hour=1,
        selected_hashtag_ids=["h1", "h2"],
    )

    assert topic_analytics["distribution"]["labels"] == ["Climate", "Robotics"]
    assert topic_analytics["distribution"]["datasets"][0]["data"] == [5, 1]
    assert topic_analytics["summary"]["rows"][0][0] == "Climate"
    assert topic_analytics["summary"]["rows"][0][3] == 5
    assert hashtag_analytics["distribution"]["labels"] == [
        "#ClimateNow",
        "#RoboticsFuture",
    ]
    assert hashtag_analytics["distribution"]["datasets"][0]["data"] == [5, 1]
    assert hashtag_analytics["summary"]["rows"][0][0] == "#ClimateNow"
    assert hashtag_analytics["summary"]["rows"][0][3] == 5


def test_photo_recsys_analytics_use_photo_ids_and_captions(tmp_path):
    db_path = tmp_path / "photo_recsys.db"
    _create_photo_sharing_analytics_db(db_path)

    analytics = _build_recsys_evolution_payload(
        str(db_path),
        filter_day=2,
        filter_hour=1,
        selected_author_uid="u1",
    )

    assert analytics["distribution"]["datasets"][0]["data"] == [2, 1]
    author_panel = analytics["recsys_author"]
    assert author_panel["selected_username"] == "alice"
    assert author_panel["unique_recipients"] == 2
    assert author_panel["total_recommendations"] == 3
    assert author_panel["recommended_posts"] == 2
    assert author_panel["followers_count"] == 2
    assert author_panel["followees_count"] == 0
    assert author_panel["summary_rows"][0][0] == "p1"
    assert author_panel["summary_rows"][0][1] == "first photo"


def test_photo_emotion_analytics_use_photo_emotions(tmp_path):
    db_path = tmp_path / "photo_emotion.db"
    _create_photo_sharing_analytics_db(db_path)

    analytics = _build_emotion_analytics_payload(str(db_path), filter_day=2, filter_hour=1)

    stats = {item["key"]: item["value"] for item in analytics["stats"]}
    assert stats["annotated_posts"] == 3
    assert analytics["distribution"]["labels"] == ["joy", "surprise"]
    assert analytics["distribution"]["datasets"][0]["data"] == [2, 1]
    assert analytics["summary"]["rows"][0] == ["joy", 2]


def test_photo_network_mention_analytics_use_photo_mentions(tmp_path):
    db_path = tmp_path / "photo_network.db"
    _create_photo_sharing_analytics_db(db_path)

    analytics = _build_network_analytics_payload(
        str(db_path),
        filter_day=2,
        filter_hour=1,
        network_type="mention",
    )

    assert analytics["network_type"] == "mention"
    assert analytics["secondary"]["datasets"][1]["data"] == [1, 2]
    assert analytics["secondary"]["datasets"][1]["label"] == "Mention Edges"
