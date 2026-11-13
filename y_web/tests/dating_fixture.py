"""A small dating run database for the observer tests, built with plain DDL (no YDating import).

The columns are the ones of the YDating server schema that the observer reads, plus the reserved ones that must
never reach a non-overview page. With ``sentinel=True`` every reserved field holds a unique marker value.
"""

import sqlite3
import uuid

SENTINELS = {
    "text": [
        "SENTINEL_REASON",
        "SENTINEL_MODEL",
        "SENTINEL_DELETED_TEXT",
        "SENTINEL_PWD",
        "SENTINEL_EMAIL",
        "SENTINEL_LEANING",
        "SENTINEL_ARCHETYPE",
        "SENTINEL_ACTIVITY",
        "SENTINEL_RECSYS",
        "SENTINEL_MODE",
        "SENTINEL_REPORT",
        "SENTINEL_STRESS",
    ],
    "numbers": ["0.31337", "7777.77", "0.424242", "9.8765", "0.171717"],
}

DDL = """
CREATE TABLE rounds (id TEXT PRIMARY KEY, day INTEGER, hour INTEGER);
CREATE TABLE user_mgmt (id TEXT PRIMARY KEY, username TEXT, email TEXT, password TEXT, user_type TEXT,
  leaning TEXT, age INTEGER, oe REAL, co REAL, ex REAL, ag REAL, ne REAL, recsys_type TEXT, language TEXT,
  owner TEXT, education_level TEXT, joined_on TEXT, frecsys_type TEXT, round_actions INTEGER, gender TEXT,
  nationality TEXT, toxicity TEXT, is_page INTEGER, left_on TEXT, daily_activity_level INTEGER, profession TEXT,
  activity_profile TEXT, archetype TEXT, cover_image TEXT, last_active_day INTEGER, match_recsys TEXT,
  status TEXT, left_reason TEXT);
CREATE TABLE dating_profile (user_id TEXT PRIMARY KEY, seeking_genders TEXT, age_min INTEGER, age_max INTEGER,
  max_distance_km REAL, lat REAL, lon REAL, city TEXT, intent TEXT, bio TEXT, prompt_answers TEXT,
  photo_count INTEGER);
CREATE TABLE dating_latent (user_id TEXT PRIMARY KEY, attractiveness REAL, selectivity REAL,
  responsiveness REAL, desirability_rating REAL);
CREATE TABLE interests (iid TEXT PRIMARY KEY, interest TEXT);
CREATE TABLE user_interest (id TEXT PRIMARY KEY, user_id TEXT, interest_id TEXT, round_id TEXT);
CREATE TABLE profile_media (id TEXT PRIMARY KEY, user_id TEXT, position INTEGER, caption TEXT, subject TEXT,
  media_url TEXT, model TEXT, embedding TEXT, vision_metadata TEXT, round_id TEXT, active INTEGER);
CREATE TABLE profile_events (id TEXT PRIMARY KEY, user_id TEXT, field TEXT, old TEXT, new TEXT, round_id TEXT);
CREATE TABLE match_recommendations (id TEXT PRIMARY KEY, viewer_id TEXT, candidate_id TEXT, model TEXT,
  score REAL, position INTEGER, round_id TEXT, reason TEXT);
CREATE TABLE swipes (id TEXT PRIMARY KEY, swiper_id TEXT, target_id TEXT, decision TEXT, rec_id TEXT,
  mode TEXT, round_id TEXT, undone INTEGER);
CREATE TABLE matches (id TEXT PRIMARY KEY, user_a TEXT, user_b TEXT, created_round TEXT, status TEXT,
  ended_by TEXT, ended_round TEXT, first_message_by TEXT);
CREATE TABLE messages (id TEXT PRIMARY KEY, match_id TEXT, sender_id TEXT, text TEXT, reply_to TEXT,
  round_id TEXT, minute INTEGER, read_round TEXT, deleted INTEGER);
CREATE TABLE date_proposals (id TEXT PRIMARY KEY, match_id TEXT, proposer_id TEXT, text TEXT, status TEXT,
  outcome TEXT, outcome_round TEXT, round_id TEXT);
CREATE TABLE blocks (id TEXT PRIMARY KEY, from_id TEXT, to_id TEXT, round_id TEXT);
CREATE TABLE reports (id TEXT PRIMARY KEY, from_id TEXT, to_id TEXT, message_id TEXT, reason TEXT, round_id TEXT);
CREATE TABLE stress_reward (id TEXT PRIMARY KEY, uid TEXT, variable TEXT, value REAL, type TEXT, action TEXT,
  tid TEXT);
"""


def _id():
    return str(uuid.uuid4())


def build_dating_db(path, sentinel=False, users=6, days=3, slots=4):
    """Create the database; returns ids: users (list), rounds (list), match, chat sender ids."""
    s = SENTINELS["text"] if sentinel else [""] * len(SENTINELS["text"])
    n = SENTINELS["numbers"] if sentinel else [None] * len(SENTINELS["numbers"])
    c = sqlite3.connect(path)
    c.executescript(DDL)
    rounds = []
    for d in range(1, days + 1):
        for h in range(1, slots + 1):
            rid = _id()
            rounds.append(rid)
            c.execute("INSERT INTO rounds VALUES (?,?,?)", (rid, d, h))
    uids = [_id() for _ in range(users)]
    for i, u in enumerate(uids):
        left = rounds[8] if i == users - 1 else None  # the last user leaves at round 9
        c.execute(
            "INSERT INTO user_mgmt VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                u,
                f"user_{i:02d}",
                s[4] or None,
                s[3],
                "user",
                s[5],
                25 + i,
                n[0],
                n[0],
                n[0],
                n[0],
                n[0],
                "default",
                "en",
                None,
                "",
                rounds[0],
                None,
                3,
                "woman" if i % 2 else "man",
                "",
                None,
                0,
                left,
                1,
                "",
                s[7],
                s[6],
                "",
                None,
                s[8],
                "left" if left else "active",
                None,
            ),
        )
        c.execute(
            "INSERT INTO dating_profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                u,
                '["woman"]',
                20,
                40,
                30.0,
                43.7,
                10.3,
                "Pisa",
                "unsure",
                ("new bio of 1" if i == 1 else f"bio of {i}"),
                '{"A good sign":"coffee"}',
                2,
            ),
        )
        c.execute(
            "INSERT INTO dating_latent VALUES (?,?,?,?,?)",
            (
                u,
                0.424242 if sentinel else 0.5,
                0.5,
                0.5,
                7777.77 if sentinel else 1000.0,
            ),
        )
        c.execute(
            "INSERT INTO profile_media VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (_id(), u, 0, f"photo of {i}", None, None, None, None, None, rounds[0], 1),
        )
    c.execute("INSERT INTO interests VALUES ('i1','hiking')")
    for u in uids:
        c.execute(
            "INSERT INTO user_interest VALUES (?,?,?,?)", (_id(), u, "i1", rounds[0])
        )
    # a bio edit of user 1 at round 6
    c.execute(
        "INSERT INTO profile_events VALUES (?,?,?,?,?,?)",
        (_id(), uids[1], "bio", "bio of 1", "new bio of 1", rounds[5]),
    )
    # the deck of user 0 at round 3: candidates 1..3
    recs = []
    for pos, cand in enumerate(uids[1:4]):
        rid = _id()
        recs.append(rid)
        c.execute(
            "INSERT INTO match_recommendations VALUES (?,?,?,?,?,?,?,?)",
            (
                rid,
                uids[0],
                cand,
                s[1] or "preference_similarity",
                9.8765 if sentinel else 1.0,
                pos,
                rounds[2],
                s[0] or "reason",
            ),
        )
    for rid, cand, dec in zip(recs, uids[1:4], ("LIKE", "PASS", "LIKE")):
        c.execute(
            "INSERT INTO swipes VALUES (?,?,?,?,?,?,?,?)",
            (_id(), uids[0], cand, dec, rid, s[9] or "rule", rounds[2], 0),
        )
    match = _id()
    c.execute(
        "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
        (match, uids[0], uids[1], rounds[3], "active", None, None, uids[1]),
    )
    msgs = [
        (uids[1], "hello there", 0, rounds[4]),
        (uids[0], "hi!", 0, rounds[4]),
        (uids[1], s[2] or "removed text", 1, rounds[5]),
    ]
    for k, (snd, text, deleted, rid) in enumerate(msgs):
        c.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
            (_id(), match, snd, text, None, rid, k, None, deleted),
        )
    c.execute(
        "INSERT INTO date_proposals VALUES (?,?,?,?,?,?,?,?)",
        (
            _id(),
            match,
            uids[1],
            "coffee?",
            "accepted",
            "NEGATIVE",
            rounds[7],
            rounds[5],
        ),
    )
    c.execute(
        "INSERT INTO blocks VALUES (?,?,?,?)", (_id(), uids[2], uids[0], rounds[6])
    )
    c.execute(
        "INSERT INTO reports VALUES (?,?,?,?,?,?)",
        (_id(), uids[2], uids[0], None, s[10] or "reason", rounds[6]),
    )
    c.execute(
        "INSERT INTO stress_reward VALUES (?,?,?,?,?,?,?)",
        (
            _id(),
            uids[0],
            s[11] or "stress",
            0.171717 if sentinel else 0.0,
            "t",
            "a",
            "x",
        ),
    )
    c.commit()
    c.close()
    return {"users": uids, "rounds": rounds, "match": match, "recs": recs}
