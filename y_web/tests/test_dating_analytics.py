"""Dating analytics ETL: idempotence, agreement with the runtime's own reports, field map, failure handling (IR-D-17)."""

import importlib.util
import os
import random
import sqlite3
import uuid
from pathlib import Path

import pytest

from y_web.src.dating import analytics_etl as etl
from y_web.tests.dating_fixture import DDL
from y_web.tests.test_im_admin_pages import im_app  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "external" / "YDating" / "scripts"
needs_runtime = pytest.mark.skipif(
    not (SCRIPTS / "metrics_report.py").exists(), reason="YDating is not present"
)

EXTRA = ""  # the shared fixture already has date_proposals


def _id():
    return str(uuid.uuid4())


def make_run(folder, seed=1, users=30, days=3, slots=4, models=("model_a", "model_b")):
    """A random but coherent run: recommendations, swipes, mutual-like matches, chats, dates, exits."""
    rnd = random.Random(seed)
    os.makedirs(folder, exist_ok=True)
    c = sqlite3.connect(os.path.join(folder, "database_server.db"))
    c.executescript(DDL + EXTRA)
    rounds = []
    for d in range(1, days + 1):
        for h in range(1, slots + 1):
            rid = _id()
            rounds.append((rid, d))
            c.execute("INSERT INTO rounds VALUES (?,?,?)", (rid, d, h))
    uids = [_id() for _ in range(users)]
    left = {}
    for i, u in enumerate(uids):
        status, reason, left_on = "active", None, None
        if i % 7 == 3:
            status, reason, left_on = (
                "left",
                rnd.choice(["paired", "churn"]),
                rnd.choice(rounds)[0],
            )
        elif i % 11 == 5:
            status = "paused"
        left[u] = left_on
        c.execute(
            "INSERT INTO user_mgmt (id, username, user_type, age, gender, joined_on, is_page, status, left_reason, left_on)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                u,
                f"user_{i:02d}",
                "user",
                20 + i % 20,
                "man" if i % 2 else "woman",
                rounds[0][0],
                0,
                status,
                reason,
                left_on,
            ),
        )
        c.execute(
            "INSERT INTO dating_profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (u, "[]", 20, 40, 30.0, 0.0, 0.0, "Pisa", "serious", "", "{}", 2),
        )
        c.execute(
            "INSERT INTO dating_latent VALUES (?,?,?,?,?)",
            (u, rnd.random(), rnd.random(), rnd.random(), 1000.0),
        )
    liked = set()
    seen_pairs = set()
    matches = []
    for rid, _d in rounds:
        for viewer in uids:
            if rnd.random() < 0.5:
                continue
            model = models[uids.index(viewer) % len(models)]
            for pos, cand in enumerate(rnd.sample([x for x in uids if x != viewer], 4)):
                rec = _id()
                c.execute(
                    "INSERT INTO match_recommendations VALUES (?,?,?,?,?,?,?,?)",
                    (rec, viewer, cand, model, rnd.random(), pos, rid, "r"),
                )
                if (viewer, cand) in seen_pairs:
                    continue
                seen_pairs.add((viewer, cand))
                decision = rnd.choice(["LIKE", "LIKE", "PASS", "SUPERLIKE"])
                undone = 1 if rnd.random() < 0.05 else 0
                c.execute(
                    "INSERT INTO swipes VALUES (?,?,?,?,?,?,?,?)",
                    (_id(), viewer, cand, decision, rec, "rule", rid, undone),
                )
                if decision != "PASS" and not undone:
                    liked.add((viewer, cand))
                    if (cand, viewer) in liked:
                        mid = _id()
                        matches.append((mid, viewer, cand, rid))
                        c.execute(
                            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
                            (mid, viewer, cand, rid, "active", None, None, viewer),
                        )
    for mid, a, b, rid in matches:
        if rnd.random() < 0.7:
            for k in range(rnd.randint(1, 6)):
                c.execute(
                    "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        _id(),
                        mid,
                        rnd.choice([a, b]),
                        "hi",
                        None,
                        rid,
                        k,
                        None,
                        1 if rnd.random() < 0.1 else 0,
                    ),
                )
        if rnd.random() < 0.4:
            status = rnd.choice(["pending", "accepted", "declined", "expired"])
            c.execute(
                "INSERT INTO date_proposals VALUES (?,?,?,?,?,?,?,?)",
                (
                    _id(),
                    mid,
                    a,
                    "coffee?",
                    status,
                    rnd.choice([None, "good", "bad"]) if status == "accepted" else None,
                    None,
                    rid,
                ),
            )
    c.execute(
        "INSERT INTO blocks VALUES (?,?,?,?)", (_id(), uids[0], uids[1], rounds[1][0])
    )
    c.execute(
        "INSERT INTO reports VALUES (?,?,?,?,?,?)",
        (_id(), uids[2], uids[1], None, "x", rounds[2][0]),
    )
    c.execute(
        "INSERT INTO profile_events VALUES (?,?,?,?,?,?)",
        (_id(), uids[1], "bio", "a", "b", rounds[3][0]),
    )
    c.commit()
    c.close()
    return uids


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dump(folder):
    with sqlite3.connect(etl.analytics_path(folder)) as conn:
        return {
            t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
            for t in etl.TABLE_ORDER
        }


def test_build_twice_gives_the_same_database(tmp_path):
    folder = str(tmp_path / "exp")
    make_run(folder)
    assert etl.build(folder)["ok"]
    first = _dump(folder)
    assert etl.build(folder)["ok"]
    assert _dump(folder) == first
    assert first["etl_state"][0][0] == etl.SCHEMA_VERSION
    assert etl.read_state(folder)["state"] == "fresh"
    # ensure_derived does not rebuild a current database
    stamp = os.stat(etl.analytics_path(folder)).st_mtime_ns
    etl.ensure_derived(folder)
    assert os.stat(etl.analytics_path(folder)).st_mtime_ns == stamp


@needs_runtime
def test_recommender_and_lifecycle_figures_equal_the_runtime_reports(tmp_path):
    folder = str(tmp_path / "exp")
    make_run(folder, seed=4)
    etl.build(folder)
    db = os.path.join(folder, "database_server.db")
    metrics = _load("metrics_report")
    for per_day in (False, True):
        expected = metrics.report(db, per_day)
        cols, rows = etl.table_rows(folder, "recommender_stats")
        got = [dict(zip(cols, r)) for r in rows if (r[1] is not None) == per_day]
        got = sorted(
            got, key=lambda r: (r["model"], r["day"] if r["day"] is not None else -1)
        )
        assert len(got) == len(expected) > 0
        for e, g in zip(expected, got):
            for key in ("model", "day", "stacks", "swipes", "matches"):
                assert e[key] == g[key], (key, e, g)
            assert e["cards_shown"] == g["cards_shown"]
            for key in (
                "like_rate",
                "gini_exposure",
                "gini_likes_received",
                "match_rate_per_stack",
                "matches_with_message_share",
            ):
                assert e[key] == pytest.approx(g[key], abs=1e-9), (key, e, g)
    life = _load("lifecycle_report").report(db)
    summary = dict(etl.table_rows(folder, "summary")[1])
    assert summary["agents"] == life["agents"]
    assert summary["matches"] == life["matches"]
    assert summary["matches_with_messages"] == life["matches_with_messages"]
    assert summary["date_proposals"] == life["date_proposals"]
    assert summary["accept_rate"] == pytest.approx(life["accept_rate"])
    assert summary["share_of_matches_with_a_date"] == pytest.approx(
        life["share_of_matches_with_a_date"]
    )
    assert summary["exits_paired"] == life["exits"].get("paired", 0)
    assert summary["exits_churn"] == life["exits"].get("churn", 0)
    assert (
        summary["paused_now"] == life["paused_now"]
        and summary["profile_changes"] == life["profile_changes"]
    )
    funnel = {(k, key): n for k, key, n in etl.table_rows(folder, "funnel")[1]}
    for status, n in life["date_status"].items():
        assert funnel[("status", status)] == n
    exits = {}
    for day, reason, n in etl.table_rows(folder, "exits")[1]:
        exits.setdefault(str(day), {})[reason] = n
    assert exits == life["exits_per_day"]


def test_figures_equal_direct_queries_on_the_run(tmp_path):
    folder = str(tmp_path / "exp")
    uids = make_run(folder, seed=9)
    etl.build(folder)
    src = sqlite3.connect(os.path.join(folder, "database_server.db"))
    one = lambda q, *a: src.execute(q, a).fetchone()[0]  # noqa: E731
    cols, stats = etl.table_rows(folder, "agent_stats")
    by = {r[0]: dict(zip(cols, r)) for r in stats}
    for u in uids[:10]:
        assert by[u]["likes_given"] == one(
            "SELECT COUNT(*) FROM swipes WHERE swiper_id=? AND undone=0 AND decision IN ('LIKE','SUPERLIKE')",
            u,
        )
        assert by[u]["matches"] == one(
            "SELECT COUNT(*) FROM matches WHERE user_a=? OR user_b=?", u, u
        )
        assert by[u]["messages_sent"] == one(
            "SELECT COUNT(*) FROM messages WHERE sender_id=?", u
        )
        assert by[u]["cards_seen"] == one(
            "SELECT COUNT(*) FROM match_recommendations WHERE viewer_id=?", u
        )
    dcols, daily = etl.table_rows(folder, "daily")
    assert sum(r[dcols.index("cards_shown")] for r in daily) == one(
        "SELECT COUNT(*) FROM match_recommendations"
    )
    assert sum(r[dcols.index("matches")] for r in daily) == one(
        "SELECT COUNT(*) FROM matches"
    )
    assert sum(r[dcols.index("messages")] for r in daily) == one(
        "SELECT COUNT(*) FROM messages"
    )
    assert sum(r[dcols.index("exits")] for r in daily) == one(
        "SELECT COUNT(*) FROM user_mgmt WHERE status='left'"
    )
    mcols, mstats = etl.table_rows(folder, "match_stats")
    assert len(mstats) == one("SELECT COUNT(*) FROM matches")
    assert sum(r[mcols.index("messages")] for r in mstats) == one(
        "SELECT COUNT(*) FROM messages"
    )


def test_the_field_map_document_is_in_sync_and_describes_every_table(tmp_path):
    folder = str(tmp_path / "exp")
    make_run(folder)
    etl.build(folder)
    with sqlite3.connect(etl.analytics_path(folder)) as conn:
        for table, (_d, _s, columns) in etl.FIELD_MAP.items():
            actual = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            assert actual == [c for c, _t, _m in columns], table
    doc = ROOT / "docs" / "dating-analytics-mapping.md"
    assert doc.exists(), "run render_field_map() into docs/dating-analytics-mapping.md"
    assert doc.read_text(encoding="utf-8").strip() == etl.render_field_map().strip()


def test_a_failed_build_keeps_the_previous_database_and_says_so(tmp_path, monkeypatch):
    folder = str(tmp_path / "exp")
    make_run(folder)
    assert etl.build(folder)["ok"]
    before = _dump(folder)

    def boom(_src):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(etl, "compute", boom)
    result = etl.build(folder)
    assert not result["ok"] and "disk I/O" in result["message"]
    assert _dump(folder) == before
    state = etl.read_state(folder)
    assert state["state"] == "failed" and "disk I/O" in state["message"]
    assert not os.path.exists(etl.analytics_path(folder) + ".part")


def test_a_changed_run_makes_the_database_stale_until_rebuilt(tmp_path):
    folder = str(tmp_path / "exp")
    make_run(folder)
    etl.build(folder)
    src = sqlite3.connect(os.path.join(folder, "database_server.db"))
    src.execute("INSERT INTO rounds VALUES (?,?,?)", (_id(), 9, 1))
    src.commit()
    src.close()
    assert etl.read_state(folder)["state"] == "stale"
    assert etl.ensure_derived(folder)["state"] == "fresh"
    assert etl.table_rows(folder, "rounds")[1][-1][1] == 9


def test_missing_database_and_unknown_table(tmp_path):
    assert not etl.build(str(tmp_path))["ok"]
    assert etl.read_state(str(tmp_path))["state"] == "never"
    with pytest.raises(KeyError):
        etl.table_rows(str(tmp_path), "user_mgmt")


# -- admin pages ---------------------------------------------------------------------------------------
def _exp_with_run(app, tmp_path, name, seed, platform="dating"):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        exp = Exps(
            exp_name=name,
            platform_type=platform,
            simulator_type="HPC",
            db_name=f"experiments/{uuid.uuid4().hex}/database_server.db",
            owner="adm",
            exp_descr="d",
            status=0,
            port=5096,
            server="127.0.0.1",
            prompt_language="en",
        )
        db.session.add(exp)
        db.session.commit()
        folder = tmp_path / "y_web" / "experiments" / exp.db_name.split("/")[1]
        make_run(str(folder), seed=seed)
        return exp.idexp


def test_the_dashboard_renders_exports_and_compares(im_app, tmp_path):  # noqa: F811
    app, client = im_app
    a = _exp_with_run(app, tmp_path, "run A", 1)
    b = _exp_with_run(app, tmp_path, "run B", 2)
    html = client.get(f"/admin/dating_analytics/{a}").data.decode()
    assert (
        "dating-recommenders" in html and "model_a" in html and "dating-summary" in html
    )
    assert "Analytics data as of day 3" in html
    assert "run B" in html  # offered for comparison
    csv_resp = client.get(f"/admin/dating_analytics/{a}/export/daily.csv")
    assert csv_resp.status_code == 200 and csv_resp.data.decode().startswith(
        "day,stacks,cards_shown"
    )
    assert (
        client.get(f"/admin/dating_analytics/{a}/export/user_mgmt.csv").status_code
        == 302
    )  # not a derived table
    import io
    import zipfile

    z = zipfile.ZipFile(
        io.BytesIO(client.get(f"/admin/dating_analytics/{a}/export.zip").data)
    )
    assert "FIELD_MAP.md" in z.namelist() and "recommender_stats.csv" in z.namelist()
    both = client.get(f"/admin/dating_analytics/compare?a={a}&b={b}").data.decode()
    assert "run A" in both and "run B" in both
    assert client.post(f"/admin/dating_analytics/{a}/rebuild").status_code == 302


def test_pages_refuse_experiments_of_other_platforms(im_app, tmp_path):  # noqa: F811
    app, client = im_app
    other = _exp_with_run(app, tmp_path, "not dating", 3, platform="instant_messaging")
    assert client.get(f"/admin/dating_analytics/{other}").status_code == 302
    assert client.get("/admin/dating_analytics/999999").status_code == 302
