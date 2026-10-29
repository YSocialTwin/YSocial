"""``Exp_stats`` of IM experiments is computed from the run database (read-only)."""

import hashlib
import sqlite3

from y_web.src.im.exp_stats import count_run
from y_web.tests.im_fixture_db import build_random_db


def _sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def test_counts_match_the_database_and_leave_it_untouched(tmp_path):
    src = str(tmp_path / "database_server.db")
    build_random_db(src, seed=3, rounds=20, messages=120)
    before = _sha(src)
    counts = count_run(src)
    with sqlite3.connect(src) as conn:
        one = lambda q: conn.execute(q).fetchone()[0] or 0  # noqa: E731
        assert counts["rounds"] == one("SELECT MAX(id) FROM rounds")
        assert counts["agents"] == one(
            "SELECT COUNT(*) FROM accounts WHERE kind='agent'"
        )
        assert counts["posts"] == one("SELECT COUNT(*) FROM messages") > 0
        assert counts["reactions"] == one("SELECT COUNT(*) FROM reactions")
        assert counts["mentions"] == one("SELECT COUNT(*) FROM mentions")
    assert _sha(src) == before


def test_missing_database_gives_zeros(tmp_path):
    assert set(count_run(str(tmp_path / "none.db")).values()) == {0}
