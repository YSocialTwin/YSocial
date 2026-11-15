"""The recommender catalogue ships empty: every row is declared by a platform and added at start-up (plan F10, R-2)."""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from y_web.platforms import registry
from y_web.platforms.recsys_catalog import ensure_catalog
from y_web.src.models import Content_Recsys, Follow_Recsys

TEMPLATE = Path(__file__).resolve().parents[2] / "data_schema" / "database_dashboard.db"
SQL_DUMP = Path(__file__).resolve().parents[2] / "data_schema" / "postgre_dashboard.sql"

needs_microblogging = pytest.mark.skipif(
    registry.get("microblogging") is None, reason="needs a microblogging repository"
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Content_Recsys.__table__.create(engine)
    Follow_Recsys.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _enabled(session, model):
    return {r.name: r.enabled for r in session.query(model).all()}


def test_the_shipped_tables_hold_no_recommender():
    conn = sqlite3.connect(TEMPLATE)
    try:
        for table in ("content_recsys", "follow_recsys"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        conn.close()
    dump = SQL_DUMP.read_text()
    assert "INSERT INTO content_recsys" not in dump
    assert "INSERT INTO follow_recsys" not in dump


@needs_microblogging
def test_the_platforms_fill_the_empty_tables(session):
    assert ensure_catalog(session) > 0
    content = _enabled(session, Content_Recsys)
    follow = _enabled(session, Follow_Recsys)
    assert content["ReverseChrono"] == "HPC,Standard"
    assert content["CollaborativeUserUser"] == "HPC"
    assert content["FilterBubble"] == "HumanOnly"
    assert follow["Jaccard"] == "HPC,Standard"
    assert follow["RandomWalkRestart"] == "HPC"
    if registry.get("forum") is not None:
        assert content["HotRanking"] == "Forum"
    assert ensure_catalog(session) == 0  # idempotent


@needs_microblogging
def test_an_older_database_gets_only_what_it_left_empty(session):
    session.add_all(
        [
            Content_Recsys(
                name="ReverseChrono", value="mine", category=None, enabled=None
            ),
            Content_Recsys(
                name="Jaccard", value="x", category="Mine", enabled="Standard"
            ),
            Content_Recsys(
                name="Custom", value="c", category="Own", enabled="Standard"
            ),
            Follow_Recsys(name="Jaccard", value="J", category=None, enabled=""),
        ]
    )
    session.commit()
    ensure_catalog(session)
    rows = {r.name: r for r in session.query(Content_Recsys).all()}
    assert rows["ReverseChrono"].enabled == "HPC,Standard"  # was empty: filled
    assert rows["ReverseChrono"].category == "Global"
    assert rows["ReverseChrono"].value == "mine"  # an edited label stays
    assert rows["Jaccard"].enabled == "Standard"  # chosen by the administrator
    assert rows["Custom"].enabled == "Standard"  # not declared by anybody: untouched
    follow = {r.name: r for r in session.query(Follow_Recsys).all()}
    assert follow["Jaccard"].enabled == "HPC,Standard"
