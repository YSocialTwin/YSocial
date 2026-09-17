"""Regression tests for the microblogging Personalized Feed recommender."""

import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from y_web import db
from y_web.src.recsys.content_recsys import (
    PersonalizedFeedRankingError,
    _filter_bubble_score,
    get_suggested_posts,
)


pytestmark = pytest.mark.integration

CLIMATE_TOPIC = "d0f183ca-7a16-46fc-9493-553fa45a25ba"
EXPECTED_CLIMATE_POSTS = [
    "539388cf-44a7-47ec-829a-2eb761d5ee17",
    "7973189c-1592-4fe3-8777-1bee9eb0aef3",
    "dd1d3eca-7240-4358-807a-b25aebb4b5b2",
]


def _create_uuid_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user_topic_interest (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            interest_level REAL NOT NULL
        );
        CREATE TABLE agent_opinion (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            tid TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            id_interacted_with TEXT,
            id_post TEXT,
            opinion REAL NOT NULL
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
            comment_to TEXT,
            shared_from TEXT,
            reaction_count INTEGER DEFAULT 0
        );
        CREATE TABLE post_topics (
            id TEXT PRIMARY KEY,
            post_id TEXT NOT NULL,
            topic_id TEXT NOT NULL
        );

        INSERT INTO rounds VALUES ('round-uuid', 1, 10);
        INSERT INTO user_topic_interest VALUES ('uti-1', 'user-uuid', 'topic-uuid', 1.0);
        INSERT INTO agent_opinion VALUES
            ('op-user', 'user-uuid', '0', 'topic-uuid', NULL, NULL, 0.9),
            ('op-close', 'author-close', '0', 'topic-uuid', NULL, NULL, 0.9),
            ('op-far', 'author-far', '0', 'topic-uuid', NULL, NULL, 0.1);
        INSERT INTO post VALUES
            ('post-close-uuid', 'author-close', 'round-uuid', '-1', '-1', 0),
            ('post-far-uuid', 'author-far', 'round-uuid', '-1', '-1', 0);
        INSERT INTO post_topics VALUES
            ('pt-close', 'post-close-uuid', 'topic-uuid'),
            ('pt-far', 'post-far-uuid', 'topic-uuid');
        """
    )
    connection.commit()
    connection.close()


def _create_integer_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user_topic_interest (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            interest_level REAL NOT NULL
        );
        CREATE TABLE agent_opinion (
            id INTEGER PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            tid INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            id_interacted_with INTEGER,
            id_post INTEGER,
            opinion REAL NOT NULL
        );
        CREATE TABLE rounds (id INTEGER PRIMARY KEY, day INTEGER, hour INTEGER);
        CREATE TABLE post (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            round INTEGER NOT NULL,
            comment_to INTEGER,
            shared_from INTEGER,
            reaction_count INTEGER DEFAULT 0
        );
        CREATE TABLE post_topics (
            id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL
        );
        INSERT INTO rounds VALUES (10, 1, 10);
        INSERT INTO user_topic_interest VALUES (1, 8, 100, 1.0);
        INSERT INTO agent_opinion VALUES
            (1, 8, 0, 100, NULL, NULL, 0.8),
            (2, 20, 0, 100, NULL, NULL, 0.8),
            (3, 30, 0, 100, NULL, NULL, 0.0);
        INSERT INTO post VALUES
            (200, 20, 10, -1, -1, 0),
            (300, 30, 10, -1, -1, 0);
        INSERT INTO post_topics VALUES (1, 200, 100), (2, 300, 100);
        """
    )
    connection.commit()
    connection.close()


def test_uuid_ranking_uses_author_opinion_similarity(tmp_path):
    database = tmp_path / "uuid-personalized.db"
    _create_uuid_fixture(database)
    engine = create_engine(f"sqlite:///{database}")

    scores = _filter_bubble_score(
        "user-uuid",
        engine,
        {"filter_bubble_alpha": 2.0, "filter_bubble_sort": "score"},
    )

    assert list(scores) == ["post-close-uuid", "post-far-uuid"]
    assert scores["post-close-uuid"] > scores["post-far-uuid"]


def test_integer_schema_remains_supported(tmp_path):
    database = tmp_path / "integer-personalized.db"
    _create_integer_fixture(database)
    engine = create_engine(f"sqlite:///{database}")

    scores = _filter_bubble_score(8, engine, {"filter_bubble_alpha": 2.0})

    assert list(scores) == [200, 300]
    assert scores[200] > scores[300]


def test_operational_failure_is_not_reported_as_cold_start(tmp_path):
    empty_database = tmp_path / "missing-personalization-schema.db"
    engine = create_engine(f"sqlite:///{empty_database}")

    with pytest.raises(PersonalizedFeedRankingError):
        _filter_bubble_score("user-uuid", engine, {})


def test_human_only_catalog_entry_is_not_exposed_to_hpc_agents(monkeypatch):
    from y_web.routes.admin.sub.experiments import _frontend_settings as module
    from y_web.src.models.config import Content_Recsys

    rows = [
        SimpleNamespace(
            id=1,
            name="ContentBasedFeatures",
            value="Content based",
            category="HPC",
            enabled="HPC",
        ),
        SimpleNamespace(
            id=2,
            name="FilterBubble",
            value="Personalized Feed",
            category="Personalization",
            enabled="HumanOnly",
        ),
    ]

    class _ScalarResult:
        def __init__(self, values):
            self._values = values

        def all(self):
            return self._values

    def _scalars(statement):
        entity = statement.column_descriptions[0].get("entity")
        return _ScalarResult(rows if entity is Content_Recsys else [])

    monkeypatch.setattr(
        module,
        "db",
        SimpleNamespace(session=SimpleNamespace(scalars=_scalars)),
    )

    agent_options = module._load_recsys_options("HPC", include_human_only=False)
    human_options = module._load_recsys_options("HPC", include_human_only=True)

    assert [item["name"] for item in agent_options["content"]] == [
        "ContentBasedFeatures"
    ]
    assert [item["name"] for item in human_options["content"]] == [
        "ContentBasedFeatures",
        "FilterBubble",
    ]


def test_linked_experiment_user_8_ranks_climate_posts_first(tmp_path):
    """Exercise the reported HPC experiment without modifying its live DB."""
    repository_root = Path(__file__).resolve().parents[2]
    source = (
        repository_root
        / "y_web"
        / "experiments"
        / "e436722f_632d_4e35_9389_1ecacd63fede"
        / "database_server.db"
    )
    if not source.exists():
        pytest.skip("The linked experiment snapshot is not available")

    experiment_copy = tmp_path / "database_server.db"
    dashboard_copy = tmp_path / "dashboard.db"
    shutil.copy2(source, experiment_copy)
    sqlite3.connect(dashboard_copy).close()

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{dashboard_copy}",
        SQLALCHEMY_BINDS={"db_exp": f"sqlite:///{experiment_copy}"},
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"check_same_thread": False},
            "poolclass": NullPool,
        },
    )
    db.init_app(app)

    settings = {
        "filter_bubble_alpha": 2.0,
        "filter_bubble_beta": 0.0,
        "filter_bubble_gamma": 0.0,
        "filter_bubble_sort": "score",
    }
    with app.app_context():
        engine = db.engines["db_exp"]
        scores = _filter_bubble_score("8", engine, settings)
        assert list(scores) == EXPECTED_CLIMATE_POSTS

        posts, additional = get_suggested_posts(
            "8",
            "FilterBubble",
            page=1,
            per_page=5,
            exp_engine=engine,
            fb_settings=settings,
        )
        assert additional is None
        assert [str(post.id) for post in posts.items[:3]] == EXPECTED_CLIMATE_POSTS

        placeholders = ",".join("?" for _ in EXPECTED_CLIMATE_POSTS)
        connection = sqlite3.connect(experiment_copy)
        topic_rows = connection.execute(
            f"SELECT post_id, topic_id FROM post_topics WHERE post_id IN ({placeholders})",
            EXPECTED_CLIMATE_POSTS,
        ).fetchall()
        connection.close()
        assert {str(topic_id) for _, topic_id in topic_rows} == {CLIMATE_TOPIC}


def test_linked_experiment_declared_topics_drive_profile_recommenders(tmp_path):
    """Profile topics must work without legacy behavioral user_interest rows."""
    repository_root = Path(__file__).resolve().parents[2]
    source = (
        repository_root
        / "y_web"
        / "experiments"
        / "e436722f_632d_4e35_9389_1ecacd63fede"
        / "database_server.db"
    )
    if not source.exists():
        pytest.skip("The linked experiment snapshot is not available")

    experiment_copy = tmp_path / "database_server.db"
    dashboard_copy = tmp_path / "dashboard.db"
    shutil.copy2(source, experiment_copy)
    sqlite3.connect(dashboard_copy).close()

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{dashboard_copy}",
        SQLALCHEMY_BINDS={"db_exp": f"sqlite:///{experiment_copy}"},
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"check_same_thread": False},
            "poolclass": NullPool,
        },
    )
    db.init_app(app)

    with app.app_context():
        for mode in ("CommonInterests", "ContentBasedFeatures"):
            posts, additional = get_suggested_posts(
                "8", mode, page=1, per_page=3
            )
            assert additional is None
            assert [str(post.id) for post in posts.items] == EXPECTED_CLIMATE_POSTS

        db.session.remove()
