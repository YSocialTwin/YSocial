"""The derived analytics database of a real 1-day echo run matches IM's own database (Phase 9 gate)."""

import hashlib
import sqlite3
from pathlib import Path

import pytest

from y_web.tests.test_im_client_creation import (  # noqa: F401
    IM_REPO,
    _post,
    _run_client,
    _seed,
    _start_server,
    env,
)


@pytest.mark.external_repo
@pytest.mark.integration
def test_real_run_counts_match_and_the_run_database_is_untouched(app, env, monkeypatch, tmp_path):
    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web.src.hpc import server as hs
    from y_web.src.im import analytics_etl as etl

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="1")
        folder = Path(env.im._experiment_folder(exp))
        db_file = folder / "database_server.db"
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        try:
            # while the server runs: a build from the live WAL database must work and leave it alone
            live = etl.refresh(str(folder), str(db_file))
            assert live["state"] == "fresh", live
            assert _run_client(str(folder), "cl", timeout=150) == 0
        finally:
            hs.stop_hpc_server(exp.idexp)

        before = hashlib.sha256(db_file.read_bytes()).hexdigest()
        result = etl.refresh(str(folder), str(db_file))
        assert result["state"] == "fresh" and result["rebuilt"] is True, result
        assert hashlib.sha256(db_file.read_bytes()).hexdigest() == before

        with sqlite3.connect(f"file:{db_file}?mode=ro", uri=True) as src, sqlite3.connect(
            etl.analytics_path(str(folder))
        ) as dst:
            for source_sql, table in (
                ("SELECT COUNT(*) FROM messages", "post"),
                ("SELECT COUNT(*) FROM accounts", "user_mgmt"),
                ("SELECT COUNT(*) FROM rounds", "rounds"),
            ):
                assert src.execute(source_sql).fetchone()[0] == dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert src.execute("SELECT COUNT(*) FROM messages").fetchone()[0] > 0
            for table in ("reactions", "mentions", "agent_opinion", "stress_reward"):
                names = {r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                source_table = {"reactions": "reactions", "mentions": "mentions", "agent_opinion": "agent_opinions",
                                "stress_reward": "stress_reward"}[table]
                n = src.execute(f"SELECT COUNT(*) FROM {source_table}").fetchone()[0]
                assert (table in names) == (n > 0), table
                if n:
                    assert dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == n
