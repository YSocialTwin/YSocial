import sqlite3

import pytest

from y_web.routes.admin.sub.experiments._opinion import (
    _build_toxicity_analytics_payload,
)

pytestmark = pytest.mark.unit


def test_toxicity_analytics_exposes_moderator_target_drilldown(tmp_path):
    db_path = tmp_path / "toxicity_moderator.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE user_mgmt (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                user_type TEXT
            );
            CREATE TABLE rounds (
                id TEXT PRIMARY KEY,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL
            );
            CREATE TABLE post (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                round TEXT NOT NULL,
                tweet TEXT
            );
            CREATE TABLE post_toxicity (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                toxicity FLOAT NOT NULL
            );
            CREATE TABLE plugin_moderation_actions (
                id INTEGER PRIMARY KEY,
                moderated_post_id TEXT NOT NULL,
                moderated_agent_id TEXT NOT NULL,
                moderator_agent_id TEXT NOT NULL,
                moderation_type TEXT NOT NULL,
                round_id TEXT NOT NULL,
                generated_comment_id TEXT
            );
        """)
        conn.executemany(
            "INSERT INTO user_mgmt(id, username, user_type) VALUES (?, ?, ?)",
            [
                ("mod1", "mod_alpha", "moderator"),
                ("u1", "alice", "standard"),
                ("u2", "bob", "standard"),
            ],
        )
        conn.executemany(
            "INSERT INTO rounds(id, day, hour) VALUES (?, ?, ?)",
            [("r1", 1, 0), ("r2", 2, 0), ("r3", 3, 0)],
        )
        conn.executemany(
            "INSERT INTO post(id, user_id, round, tweet) VALUES (?, ?, ?, ?)",
            [
                ("p1", "u1", "r1", "post one"),
                ("p2", "u1", "r2", "post two"),
                ("p3", "u2", "r2", "post three"),
            ],
        )
        conn.executemany(
            "INSERT INTO post_toxicity(id, post_id, toxicity) VALUES (?, ?, ?)",
            [
                ("t1", "p1", 0.2),
                ("t2", "p2", 0.6),
                ("t3", "p3", 0.4),
            ],
        )
        conn.executemany(
            """
            INSERT INTO plugin_moderation_actions(
                id, moderated_post_id, moderated_agent_id, moderator_agent_id,
                moderation_type, round_id, generated_comment_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "p1", "u1", "mod1", "personalized", "r1", None),
                (2, "p2", "u1", "mod1", "personalized", "r2", None),
                (3, "p3", "u2", "mod1", "one_fits_all", "r2", None),
            ],
        )
        conn.commit()

    analytics = _build_toxicity_analytics_payload(
        str(db_path),
        filter_day=3,
        filter_hour=0,
        threshold=0.1,
        selected_target_uid="u1",
    )

    moderator_targets = analytics["moderator_targets"]
    assert moderator_targets["available"] is True
    assert moderator_targets["deployed_agents"] == 1
    assert moderator_targets["selected_uid"] == "u1"
    assert moderator_targets["selected_username"] == "alice"
    assert moderator_targets["moderation_count"] == 2
    assert moderator_targets["moderator_usernames"] == ["mod_alpha"]
    assert moderator_targets["trend_data"]["datasets"][0]["data"] == [0.2, 0.6, 0.0]
    assert moderator_targets["trend_data"]["datasets"][1]["data"] == [0.2, 0.6, 0.0]
    assert moderator_targets["trend_data"]["datasets"][2]["data"] == [1, 1, 0]
    assert moderator_targets["interaction_events"][0]["day"] == 2
    assert (
        moderator_targets["interaction_events"][0]["moderation_type"] == "personalized"
    )
