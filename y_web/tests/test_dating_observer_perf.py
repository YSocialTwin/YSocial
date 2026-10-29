"""Performance target of the dating observer (plan 6.5): a deck page in under 300 ms at 1000 agents and 7 days.

The database is generated with the indexes of the YDating schema (the observer is read only: an index that is
missing would have to be added by the runtime, not here).
"""

import sqlite3
import time
import uuid

import pytest

from y_web.src.dating.reader import Viewpoint, open_reader
from y_web.tests.dating_fixture import DDL

INDEXES = """
CREATE INDEX idx_match_rec_viewer_round ON match_recommendations (viewer_id, round_id);
CREATE INDEX idx_match_rec_candidate ON match_recommendations (candidate_id);
CREATE UNIQUE INDEX uq_swipe_active_pair ON swipes (swiper_id, target_id);
CREATE INDEX idx_swipes_round ON swipes (round_id);
CREATE INDEX idx_matches_user_a ON matches (user_a);
CREATE INDEX idx_matches_user_b ON matches (user_b);
CREATE INDEX idx_messages_match ON messages (match_id, round_id);
CREATE INDEX idx_profile_events_user_id ON profile_events (user_id);
CREATE INDEX idx_user_interest_user_id ON user_interest (user_id);
CREATE INDEX idx_profile_media_user_id ON profile_media (user_id);
CREATE UNIQUE INDEX uq_rounds_day_hour ON rounds (day, hour);
"""

USERS, DAYS, SLOTS, DECK = 1000, 7, 24, 10


def _build(path):
    c = sqlite3.connect(path)
    c.executescript(DDL + INDEXES)
    rounds = [
        (str(uuid.uuid4()), d, h)
        for d in range(1, DAYS + 1)
        for h in range(1, SLOTS + 1)
    ]
    c.executemany("INSERT INTO rounds VALUES (?,?,?)", rounds)
    uids = [str(uuid.uuid4()) for _ in range(USERS)]
    c.executemany(
        "INSERT INTO user_mgmt (id, username, user_type, age, gender, joined_on, is_page, status) VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                u,
                f"user_{i:04d}",
                "user",
                20 + i % 30,
                "woman" if i % 2 else "man",
                rounds[0][0],
                0,
                "active",
            )
            for i, u in enumerate(uids)
        ],
    )
    c.executemany(
        "INSERT INTO dating_profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (u, "[]", 20, 40, 30.0, 0.0, 0.0, "Pisa", "unsure", f"bio {i}", "{}", 3)
            for i, u in enumerate(uids)
        ],
    )
    c.execute("INSERT INTO interests VALUES ('i1','hiking')")
    c.executemany(
        "INSERT INTO user_interest VALUES (?,?,?,?)",
        [(str(uuid.uuid4()), u, "i1", rounds[0][0]) for u in uids],
    )
    c.executemany(
        "INSERT INTO profile_media VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                str(uuid.uuid4()),
                u,
                p,
                "c",
                None,
                None,
                None,
                None,
                None,
                rounds[0][0],
                1,
            )
            for u in uids
            for p in range(3)
        ],
    )
    recs, swipes = [], []
    for k, u in enumerate(uids):
        for r in range(
            k % 6, len(rounds), 6
        ):  # every user is served a deck every sixth round
            for j in range(DECK):
                cand = uids[(k + 1 + (r // 6) * DECK + j) % USERS]
                rid = str(uuid.uuid4())
                recs.append(
                    (rid, u, cand, "preference_similarity", 1.0, j, rounds[r][0], "r")
                )
                swipes.append(
                    (
                        str(uuid.uuid4()),
                        u,
                        cand,
                        "LIKE" if j % 3 else "PASS",
                        rid,
                        "rule",
                        rounds[r][0],
                        0,
                    )
                )
    c.executemany("INSERT INTO match_recommendations VALUES (?,?,?,?,?,?,?,?)", recs)
    c.executemany("INSERT OR IGNORE INTO swipes VALUES (?,?,?,?,?,?,?,?)", swipes)
    matches, msgs = [], []
    for m in range(3000):
        mid = str(uuid.uuid4())
        a, b = uids[m % USERS], uids[(m * 7 + 3) % USERS]
        if a == b:
            continue
        matches.append((mid, a, b, rounds[10 + m % 100][0], "active", None, None, a))
        for k in range(10):
            msgs.append(
                (
                    str(uuid.uuid4()),
                    mid,
                    a if k % 2 else b,
                    "hello",
                    None,
                    rounds[20 + m % 100 + k][0],
                    k,
                    None,
                    0,
                )
            )
    c.executemany("INSERT OR IGNORE INTO matches VALUES (?,?,?,?,?,?,?,?)", matches)
    c.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)", msgs)
    c.commit()
    c.close()
    return uids


def _best(fn, n=3):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    return min(out)


@pytest.mark.timeout(110)
def test_deck_and_showcase_under_the_target(tmp_path):
    path = str(tmp_path / "big.db")
    uids = _build(path)
    with open_reader(path) as reader:
        latest = reader.latest_round()
        assert latest == DAYS * SLOTS
        vp = Viewpoint("account", uids[0], latest)
        deck = reader.deck(uids[0], vp)
        assert len(deck["cards"]) == DECK
        t_deck = _best(lambda: reader.deck(uids[0], vp))
        t_show = _best(lambda: reader.showcase(latest, 3, 24))
        t_matches = _best(lambda: reader.matches(uids[0], vp))
        ov = Viewpoint("overview", None, latest)
        t_hist = _best(lambda: reader.history(ov))
    print(
        f"deck {t_deck*1000:.0f} ms, showcase {t_show*1000:.0f} ms, matches {t_matches*1000:.0f} ms, history {t_hist*1000:.0f} ms"
    )
    assert t_deck < 0.3 and t_show < 0.3 and t_matches < 0.3
