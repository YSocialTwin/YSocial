"""Hashtags: canonical form, apostrophes/accents kept in the tag, duplicates merged, copies in sync."""
import importlib.util
import pathlib

import pytest
from sqlalchemy import create_engine, text

from y_web.hashtag_text import extract_hashtags, hashtag_key, normalize_hashtag
from y_web.src.experiment.hashtag_migration import merge_duplicate_hashtags

ROOT = pathlib.Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("#repubblica", "repubblica"),
        ("repubblica", "repubblica"),
        ("##DelPiero", "DelPiero"),
        ("#c’èdavverounveroitaliano", "c’èdavverounveroitaliano"),
        ("#quant'altro,", "quant'altro"),
        ("#l'", "l"),
        ("#città", "città"),
        ("#", ""),
        (None, ""),
    ],
)
def test_normalize(raw, expected):
    assert normalize_hashtag(raw) == expected


def test_identity_ignores_hash_and_case():
    assert hashtag_key("#Sustainability") == hashtag_key("sustainability") == hashtag_key("##SUSTAINABILITY")


def test_extraction_keeps_apostrophes_and_accents_inside_the_tag():
    text_ = "Ciao #c’èdavverounveroitaliano e #quant'altro! #Roma #roma #città"
    assert extract_hashtags(text_) == ["c’èdavverounveroitaliano", "quant'altro", "Roma", "città"]


def _db(tmp_path, ids):
    engine = create_engine(f"sqlite:///{tmp_path / 'x.db'}")
    with engine.begin() as c:
        idtype = "INTEGER PRIMARY KEY" if ids == "int" else "TEXT PRIMARY KEY"
        c.execute(text(f"CREATE TABLE hashtags (id {idtype}, hashtag TEXT)"))
        c.execute(text("CREATE TABLE post_hashtags (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id TEXT, hashtag_id TEXT)"))
    return engine


@pytest.mark.parametrize("ids", ["int", "uuid"])
def test_merge_duplicates_and_relink(tmp_path, ids):
    engine = _db(tmp_path, ids)
    a, b, c_, d = ("1", "2", "3", "4") if ids == "int" else ("ua", "ub", "uc", "ud")
    with engine.begin() as c:
        for i, h in [(a, "#Sustainability"), (b, "sustainability"), (c_, "Sustainability"), (d, "#solo")]:
            c.execute(text("INSERT INTO hashtags (id, hashtag) VALUES (:i, :h)"), {"i": i, "h": h})
        for post, tag in [("p1", a), ("p2", b), ("p3", c_), ("p1", b), ("p4", d)]:
            c.execute(text("INSERT INTO post_hashtags (post_id, hashtag_id) VALUES (:p, :t)"), {"p": post, "t": tag})
    res = merge_duplicate_hashtags(engine)
    assert res == {"merged": 2, "renamed": 2}
    with engine.connect() as c:
        tags = dict(c.execute(text("SELECT id, hashtag FROM hashtags")).fetchall())
        assert sorted(tags.values()) == ["Sustainability", "solo"]
        per_post = c.execute(text("SELECT post_id, COUNT(*) FROM post_hashtags WHERE hashtag_id = :k GROUP BY post_id"), {"k": a}).fetchall()
        assert sorted(per_post) == [("p1", 1), ("p2", 1), ("p3", 1)]
        assert c.execute(text("SELECT COUNT(*) FROM post_hashtags WHERE hashtag_id NOT IN (SELECT id FROM hashtags)")).scalar() == 0
    assert merge_duplicate_hashtags(engine) == {"merged": 0, "renamed": 0}


def test_database_without_hashtags_is_left_alone(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'y.db'}")
    assert merge_duplicate_hashtags(engine) == {"merged": 0, "renamed": 0}


COPIES = [
    "external/YServer/y_server",
    "external/YServerReddit/y_server",
    "external/YClient/y_client",
    "external/YClientReddit/y_client",
    "external/YSimulator/YSimulator",
    "external/YPhotoSharing/YPhotoSharing",
]


@pytest.mark.integration
@pytest.mark.external_repo
@pytest.mark.parametrize("rel", COPIES)
def test_copies_are_identical(rel):
    path = ROOT / rel / "hashtag_text.py"
    if not path.exists():
        pytest.skip("external repo not present")
    assert path.read_bytes() == (ROOT / "y_web" / "hashtag_text.py").read_bytes()
