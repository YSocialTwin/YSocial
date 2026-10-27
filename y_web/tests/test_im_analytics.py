"""Derived analytics database of IM experiments: ETL parity, idempotence, failures, and every page (Phase 9)."""

import hashlib
import os
import sqlite3

import pytest

from y_web.tests.im_fixture_db import build_random_db, enrich_db
from y_web.tests.test_im_admin_pages import _make_im_experiment, im_app  # noqa: F401


def _file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        h.update(handle.read())
    return h.hexdigest()


def _dump(path):
    """Every row of every table of the derived database except the build timestamp, in a stable order."""
    conn = sqlite3.connect(path)
    out = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        rows = sorted(conn.execute(f"SELECT * FROM {name}").fetchall(), key=repr)
        if name == "etl_state":
            rows = [tuple(r[:-1]) for r in rows]  # built_at differs between builds
        out[name] = rows
    conn.close()
    return out


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "exp"
    path.mkdir()
    src = str(path / "database_server.db")
    info = build_random_db(src, seed=5, rounds=30, messages=200)
    expected = enrich_db(src, info)
    return str(path), src, info, expected


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _count(path, table, where=""):
    with sqlite3.connect(path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]


# ---- ETL ------------------------------------------------------------------------------------------------
def test_counts_match_the_source(folder):
    from y_web.src.im import analytics_etl as etl

    path, src, info, expected = folder
    result = etl.refresh(path, src)
    assert result["state"] == "fresh" and result["rebuilt"] is True
    target = etl.analytics_path(path)
    for table in ("rounds", "user_mgmt", "post", "reactions", "mentions", "post_topics", "post_hashtags",
                  "post_toxicity", "post_sentiment", "agent_opinion", "stress_reward"):
        assert _count(target, table) == expected[table], table
    assert _count(target, "reactions", "WHERE type = 'like'") == expected["reactions_positive"]
    assert _count(target, "reactions", "WHERE type = 'dislike'") == expected["reactions_negative"]
    with sqlite3.connect(src) as source:
        replies = source.execute("SELECT COUNT(*) FROM messages WHERE reply_to_message_id IS NOT NULL").fetchone()[0]
    assert _count(target, "post", "WHERE comment_to != -1") == replies
    assert _count(target, "post", "WHERE comment_to = -1") == expected["post"] - replies
    # a round keeps its day and its slot (the pages call the slot "hour")
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT day, hour FROM rounds WHERE id = 30").fetchone() == (2, 6)


def test_tables_exist_only_when_their_data_does(tmp_path):
    from y_web.src.im import analytics_etl as etl

    path = tmp_path / "bare"
    path.mkdir()
    src = str(path / "database_server.db")
    build_random_db(src, seed=3, rounds=10, messages=50)  # no annotations, topics, opinions, stress
    etl.refresh(str(path), src)
    tables = _tables(etl.analytics_path(str(path)))
    assert {"rounds", "user_mgmt", "post", "etl_state"} <= tables
    for absent in ("post_toxicity", "post_sentiment", "agent_opinion", "stress_reward", "post_topics",
                   "post_hashtags", "reactions", "mentions", "post_emotions", "emotions", "recommendations", "follow"):
        assert absent not in tables


def test_annotations_with_status_error_are_not_copied(folder):
    from y_web.src.im import analytics_etl as etl

    path, src, info, expected = folder
    etl.refresh(path, src)
    with sqlite3.connect(src) as source:
        total = source.execute("SELECT COUNT(*) FROM annotations WHERE method_ref LIKE 'sentiment%'").fetchone()[0]
    assert expected["post_sentiment"] <= total


def test_idempotent_and_unchanged_source_is_not_rebuilt(folder):
    from y_web.src.im import analytics_etl as etl

    path, src, info, expected = folder
    etl.refresh(path, src)
    first = _dump(etl.analytics_path(path))
    assert etl.refresh(path, src) == {"state": "fresh", "rebuilt": False}
    etl.refresh(path, src, force=True)
    assert _dump(etl.analytics_path(path)) == first


def test_source_change_rebuilds_and_equals_a_fresh_full_build(folder, tmp_path):
    from y_web.src.im import analytics_etl as etl
    from y_web.src.im.engine import im_modules

    path, src, info, expected = folder
    etl.refresh(path, src)
    from sqlalchemy.orm import Session

    from yinstantmessaging.server.db.database import make_engine_from_url

    models = im_modules()[0]
    engine = make_engine_from_url(f"sqlite:///{src}")
    with Session(engine) as s:
        s.add(models.Reaction(account_id=info["accounts"][0], message_id="m0001", emoji="👍", round_id=30))
        s.commit()
    engine.dispose()
    assert etl.is_fresh(path, src) is False
    assert etl.refresh(path, src)["rebuilt"] is True
    incremental = _dump(etl.analytics_path(path))
    other = tmp_path / "fresh"
    other.mkdir()
    etl.refresh(str(other), src)
    assert _dump(etl.analytics_path(str(other))) == incremental


def test_the_source_is_byte_identical_after_every_path(folder):
    from y_web.src.im import analytics_etl as etl

    path, src, info, expected = folder
    before = _file_hash(src)
    etl.refresh(path, src)
    etl.refresh(path, src, force=True)
    etl.read_state(path)
    assert _file_hash(src) == before


def test_failure_is_recorded_and_the_previous_file_stays(folder):
    from y_web.src.im import analytics_etl as etl

    path, src, info, expected = folder
    etl.refresh(path, src)
    good = _dump(etl.analytics_path(path))
    # a schema the installed runtime does not know is refused with a message
    import y_web.src.im.analytics_etl as module

    original = module._build

    def broken(*a, **k):
        raise RuntimeError("source schema is newer than this runtime")

    module._build = broken
    try:
        out = etl.refresh(path, src, force=True)
    finally:
        module._build = original
    assert out["state"] == "failed" and "newer" in out["message"]
    assert etl.read_state(path)["state"] == "failed"
    assert _dump(etl.analytics_path(path)) == good
    assert not os.path.exists(etl.analytics_path(path) + ".part")


def test_no_source_means_never_built(tmp_path):
    from y_web.src.im import analytics_etl as etl

    assert etl.refresh(str(tmp_path), str(tmp_path / "missing.db"))["state"] == "never"
    assert etl.read_state(str(tmp_path))["state"] == "never"


def test_state_reports_the_data_horizon(folder):
    from y_web.src.im import analytics_etl as etl

    path, src, info, expected = folder
    etl.refresh(path, src)
    state = etl.read_state(path)
    assert state["state"] == "fresh" and (state["day"], state["slot"]) == (2, 6)


# ---- pages ----------------------------------------------------------------------------------------------
@pytest.fixture
def pages(im_app, tmp_path, monkeypatch):
    from y_web import db
    from y_web.routes.admin.sub.experiments import _helpers, _opinion
    from y_web.src.models import Exps

    # these modules bound get_writable_path at import time: point them at this test's folder
    for module in (_opinion, _helpers):
        if hasattr(module, "get_writable_path"):
            monkeypatch.setattr(module, "get_writable_path", lambda p="": os.path.join(str(tmp_path), p) if p else str(tmp_path), raising=False)
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path",
        lambda p="": os.path.join(str(tmp_path), p) if p else str(tmp_path),
    )
    app, client = im_app
    exp_id = _make_im_experiment(app)
    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        exp.status = 1
        exp.annotations = ""
        db.session.commit()
        folder = tmp_path / "y_web" / "experiments" / exp.db_name.split("/")[1]
        folder.mkdir(parents=True)
        src = str(folder / "database_server.db")
        info = build_random_db(src, seed=5, rounds=30, messages=200)
        enrich_db(src, info)
    return app, client, exp_id, str(folder), src


AVAILABLE = ("toxicity_evolution", "sentiment_evolution", "opinion_evolution", "stress_reward_evolution",
             "topic_evolution", "hashtag_evolution", "network_analysis")
UNAVAILABLE = ("emotion_statistics", "recsys_evolution")


def test_every_page_with_data_renders_and_the_source_is_untouched(pages):
    app, client, exp_id, folder, src = pages
    before = _file_hash(src)
    for page in AVAILABLE:
        r = client.get(f"/admin/{page}/{exp_id}")
        assert r.status_code == 200, (page, r.status_code, r.headers.get("Location"))
    assert os.path.isfile(os.path.join(folder, "analytics_im.db"))
    assert _file_hash(src) == before
    with app.app_context():
        from y_web import db
        from y_web.src.models import Exps

        annotations = db.session.get(Exps, exp_id).annotations
    assert {"opinions", "sentiment", "toxicity"} <= set(annotations.split(","))
    # IM's own database is never bound as an experiment database; only the derived one is
    assert app.config["SQLALCHEMY_BINDS"].get(f"db_exp_{exp_id}", "").endswith("analytics_im.db")


def test_data_endpoints_answer_json_for_available_pages(pages):
    app, client, exp_id, folder, src = pages
    for page in ("toxicity_evolution_data", "sentiment_evolution_data", "opinion_evolution_data",
                 "stress_reward_evolution_data", "topic_evolution_data", "hashtag_evolution_data",
                 "network_analysis_data"):
        r = client.get(f"/admin/{page}/{exp_id}")
        assert r.status_code == 200 and r.get_json() is not None, (page, r.status_code)


def test_pages_without_their_tables_show_the_normal_unavailable_state(pages):
    app, client, exp_id, folder, src = pages
    for page in UNAVAILABLE:
        r = client.get(f"/admin/{page}/{exp_id}")
        assert r.status_code == 302, page
        assert f"/admin/experiment_details/{exp_id}" in r.headers["Location"]
    for page in ("emotion_statistics_data", "recsys_evolution_data"):
        assert client.get(f"/admin/{page}/{exp_id}").status_code in (400, 404)


def test_details_page_cards_follow_the_derived_tables(pages):
    app, client, exp_id, folder, src = pages
    html = client.get(f"/admin/experiment_details/{exp_id}").data.decode()
    assert "Analytics data as of day 2, slot 6" in html and "Refresh analytics data" in html
    for link in ("toxicity_evolution", "sentiment_evolution", "opinion_evolution", "stress_reward_evolution",
                 "topic_evolution", "hashtag_evolution", "network_analysis"):
        assert f"/admin/{link}/{exp_id}" in html, link
    assert f"/admin/emotion_statistics/{exp_id}" not in html
    assert f"/admin/recsys_evolution/{exp_id}" not in html


def test_refresh_action_rebuilds_and_redirects(pages):
    app, client, exp_id, folder, src = pages
    client.get(f"/admin/experiment_details/{exp_id}")
    target = os.path.join(folder, "analytics_im.db")
    stamp = os.stat(target).st_mtime_ns
    r = client.post(f"/admin/im/analytics/{exp_id}/refresh")
    assert r.status_code == 302 and f"/admin/experiment_details/{exp_id}" in r.headers["Location"]
    assert os.stat(target).st_mtime_ns != stamp  # forced rebuild
    assert client.post("/admin/im/analytics/99999/refresh").status_code == 302


def test_other_platforms_keep_their_resolution(im_app):
    from y_web import db
    from y_web.routes.admin.sub.experiments import _opinion
    from y_web.src.models import Exps

    app, client = im_app
    with app.app_context():
        mb = Exps(exp_name="mb2", platform_type="microblogging", simulator_type="HPC",
                  db_name="experiments/abc/database_server.db", owner="adm", exp_descr="d", status=0, port=5097,
                  server="127.0.0.1", prompt_language="en")
        db.session.add(mb)
        db.session.commit()
        assert _opinion._resolve_opinion_experiment_db_name(mb).endswith("database_server.db")


def test_derived_files_are_run_artifacts_left_out_of_clones_and_downloads(folder, tmp_path):
    from y_web.src.im import analytics_etl as etl
    from y_web.src.im.clone import clear_im_run_artifacts, is_run_artifact, snapshot_for_download

    path, src, info, expected = folder
    etl.refresh(path, src)
    assert is_run_artifact("analytics_im.db") and is_run_artifact("analytics_im.db-wal")
    assert is_run_artifact("analytics_im.status.json")
    staged = snapshot_for_download(path, str(tmp_path / "staging"))
    assert not any(name.startswith("analytics_im.") for name in os.listdir(staged))
    assert os.path.exists(os.path.join(staged, "database_server.db"))
    clear_im_run_artifacts(path)
    assert not os.path.exists(etl.analytics_path(path))


def test_pages_carry_the_note_about_slots_and_messages(pages):
    app, client, exp_id, folder, src = pages
    for page in ("toxicity_evolution", "opinion_evolution", "stress_reward_evolution", "topic_evolution",
                 "network_analysis"):
        html = client.get(f"/admin/{page}/{exp_id}").data.decode()
        assert 'id="im-analytics-note"' in html and "not directly comparable" in html, page
