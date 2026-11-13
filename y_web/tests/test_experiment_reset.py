"""Reset of one experiment to its initial state (used by the reset of a World Simulation)."""

import os
import sqlite3
from datetime import datetime

import pytest

from y_web import db
from y_web.src.experiment import reset as xr


@pytest.fixture
def exp_dir(app, tmp_path, monkeypatch):
    """A Standard experiment that has run: database with content, logs, run state, content cache, one client."""
    from y_web.src.models import (
        Client,
        Client_Execution,
        Exp_stats,
        Exps,
        LogFileOffset,
    )

    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path",
        lambda rel="": str(tmp_path / rel) if rel else str(tmp_path),
    )
    folder = tmp_path / "y_web" / "experiments" / "abc"
    folder.mkdir(parents=True)
    conn = sqlite3.connect(folder / "database_server.db")
    conn.execute("create table post (id integer)")
    conn.execute("insert into post values (1)")
    conn.commit()
    conn.close()
    for name in (
        "_server.log",
        "client.log",
        "x.state.json",
        "client_content.db",
        "client_content.db-wal",
        "prompts.json",
    ):
        (folder / name).write_text("x")
    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            exp_name="E",
            db_name=f"experiments{os.sep}abc{os.sep}database_server.db",
            owner="admin",
            exp_descr="",
            status=1,
            running=0,
            port=5001,
            simulator_type="Standard",
            exp_status="running",
        )
        db.session.add(exp)
        db.session.flush()
        client = Client(
            name="c",
            descr="",
            days=3,
            id_exp=exp.idexp,
            population_id=1,
            status=1,
            pid=123,
        )
        db.session.add(client)
        db.session.flush()
        db.session.add_all(
            [
                Client_Execution(
                    client_id=client.id,
                    elapsed_time=99,
                    last_active_day=5,
                    last_active_hour=7,
                    expected_duration_rounds=72,
                ),
                Exp_stats(
                    exp_id=exp.idexp,
                    rounds=50,
                    agents=10,
                    posts=40,
                    reactions=9,
                    mentions=1,
                ),
                LogFileOffset(
                    exp_id=exp.idexp,
                    log_file_type="server",
                    file_path="x",
                    last_offset=5,
                    last_updated=datetime.now(),
                ),
            ]
        )
        db.session.commit()
        yield exp, client, folder


def test_a_standard_experiment_goes_back_to_the_state_of_a_new_one(
    app, exp_dir, monkeypatch
):
    from y_web.src.models import Client, Client_Execution, Exp_stats, LogFileOffset

    exp, client, folder = exp_dir
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.stop_client_for_experiment",
        lambda *a, **k: True,
    )
    result = xr.reset_experiment(exp)
    assert result["database"] in ("clean schema", "empty database")
    # the database no longer holds the content of the run
    conn = sqlite3.connect(folder / "database_server.db")
    tables = {
        r[0] for r in conn.execute("select name from sqlite_master where type='table'")
    }
    conn.close()
    assert (
        "post" not in tables
        or sqlite3.connect(folder / "database_server.db")
        .execute("select count(*) from post")
        .fetchone()[0]
        == 0
    )
    # logs, run state and the client's content cache are gone; the settings stay
    left = {p.name for p in folder.iterdir()}
    assert left >= {"prompts.json", "database_server.db"}
    assert not left & {
        "_server.log",
        "client.log",
        "x.state.json",
        "client_content.db",
        "client_content.db-wal",
    }
    db.session.expire_all()
    assert (exp.running, exp.status, exp.exp_status) == (0, 0, "stopped")
    cl = db.session.get(Client, client.id)
    assert cl.status == 0 and cl.pid is None
    ex = db.session.query(Client_Execution).filter_by(client_id=client.id).one()
    assert (ex.elapsed_time, ex.last_active_day, ex.last_active_hour) == (
        0,
        -1,
        -1,
    ) and ex.expected_duration_rounds == 72
    stats = db.session.query(Exp_stats).filter_by(exp_id=exp.idexp).one()
    assert (stats.rounds, stats.posts, stats.agents) == (0, 0, 0)
    assert db.session.query(LogFileOffset).filter_by(exp_id=exp.idexp).count() == 0


def test_a_running_experiment_is_refused_and_left_untouched(app, exp_dir):
    exp, client, folder = exp_dir
    exp.running = 1
    with pytest.raises(xr.ResetError):
        xr.reset_experiment(exp)
    assert (folder / "_server.log").exists() and (folder / "client_content.db").exists()
