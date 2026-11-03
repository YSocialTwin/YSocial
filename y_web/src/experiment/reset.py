"""Back to the initial state: an experiment as if it had never been started.

Used by the reset of a World Simulation, which must bring *every* member back, whatever its backend:

* HPC (Ray) experiments: the population files are restored from their backups, the run artifacts and the database the
  server creates at start are removed;
* Standard experiments (microblogging, forum): the database is replaced by the clean schema a new experiment starts
  from, the logs, the run-state snapshots and the client's own content database are removed.

In both cases the clients are marked stopped with no elapsed time, the counters, the log offsets and the metrics
caches of the experiment are cleared and the experiment is *stopped* with its web interface off. The experiment
itself, its clients, its populations and its settings stay. An experiment that is still running is refused.
"""

from __future__ import annotations

import os
import shutil
from typing import Dict, List

from sqlalchemy import select

from y_web import db


class ResetError(ValueError):
    """The experiment cannot be reset (running, or a backend the reset does not cover)."""


# files of a Standard experiment that a run creates beside the database (state snapshots, the client's content cache)
_RUN_STATE_SUFFIXES = (".state.json",)
_CLIENT_CONTENT = "client_content.db"


def _remove(path: str, failed: List[str]) -> bool:
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        failed.append(path)
        return False


def _sqlite_sidecars(path: str):
    return (path, path + "-wal", path + "-shm", path + "-journal")


def _clean_database(exp_folder: str, failed: List[str]) -> str:
    """Replace the database of a Standard experiment by the clean schema; returns what was done."""
    from y_web.src.system.path_utils import get_resource_path

    target = os.path.join(exp_folder, "database_server.db")
    for name in _sqlite_sidecars(target):
        _remove(name, failed)
    clean = get_resource_path(os.path.join("data_schema", "database_clean_server.db"))
    if os.path.exists(clean):
        shutil.copy2(clean, target)
        return "clean schema"
    import sqlite3

    sqlite3.connect(target).close()  # as "Copy experiment" does when the clean schema is missing
    return "empty database"


def reset_experiment(exp, *, logger=None) -> Dict[str, object]:
    """Reset one experiment to its initial state; returns ``{"restored", "removed", "database", "failed"}``.

    Raises :class:`ResetError` when the experiment is running or is not a SQLite Standard / HPC experiment.
    """
    from y_web.routes.admin.sub.experiments._helpers import (
        _get_database_type,
        _get_experiment_folder,
        clear_experiment_log_files,
    )
    from y_web.src.dating import is_dating_experiment
    from y_web.src.hpc.population_backup import restore_population_for_hpc_client
    from y_web.src.im import is_im_experiment
    from y_web.src.models import (
        Client,
        Client_Execution,
        ClientLogMetrics,
        Exp_stats,
        LogFileOffset,
        OpinionEvolutionCache,
        OpinionEvolutionSampledAgents,
        Population,
        ServerLogMetrics,
    )
    from y_web.src.simulation.execution_backend import stop_client_for_experiment
    from y_web.src.system.path_utils import get_writable_path

    if exp.running == 1:
        raise ResetError(f"'{exp.exp_name}' is running: stop it before resetting it.")
    hpc = exp.simulator_type == "HPC"
    db_type = _get_database_type()
    if not hpc and db_type != "sqlite":
        raise ResetError(
            f"'{exp.exp_name}': the reset of a Standard experiment on {db_type} is not supported."
        )

    clients = db.session.scalars(select(Client).filter_by(id_exp=exp.idexp)).all()
    for client in clients:
        if client.status == 1 and (client.pid or hpc):
            try:
                stop_client_for_experiment(exp, client, pause=False)
            except Exception:
                if logger:
                    logger.warning("could not stop client %s during reset", client.id, exc_info=True)
        client.status = 0
        client.pid = None

    restored = 0
    if hpc:
        for client in clients:
            population = db.session.scalars(
                select(Population).filter_by(id=client.population_id)
            ).first()
            if restore_population_for_hpc_client(exp, client, population):
                restored += 1

    exp_folder = _get_experiment_folder(get_writable_path(), exp, db_type)
    failed: List[str] = []
    removed = 0
    if is_im_experiment(exp):
        from y_web.src.im.clone import clear_im_run_artifacts

        removed, failed = clear_im_run_artifacts(exp_folder)
    elif is_dating_experiment(exp):
        from y_web.src.dating.clone import clear_dating_run_artifacts

        removed, failed = clear_dating_run_artifacts(exp_folder)
    else:
        removed, failed = clear_experiment_log_files(exp_folder)
    failed = list(failed)

    database = "removed (the server creates it at start)"
    if hpc:
        for name in ("database_server.db", "simulation.db"):
            for path in _sqlite_sidecars(os.path.join(exp_folder, name)):
                _remove(path, failed)
    else:
        database = _clean_database(exp_folder, failed)
        for item in os.listdir(exp_folder):
            if item.endswith(_RUN_STATE_SUFFIXES):
                removed += _remove(os.path.join(exp_folder, item), failed)
        for path in _sqlite_sidecars(os.path.join(exp_folder, _CLIENT_CONTENT)):
            removed += _remove(path, failed)
    if failed and logger:
        for path in failed:
            logger.warning("could not delete %s during reset", path)

    from y_web.routes.admin.sub.experiments._data import _reset_slots_per_day

    for client in clients:
        expected = (
            -1
            if client.days == -1
            else max(int(client.days), 0) * _reset_slots_per_day(exp, exp_folder)
        )
        execution = db.session.scalars(
            select(Client_Execution).filter_by(client_id=client.id)
        ).first()
        if execution:
            execution.elapsed_time = 0
            execution.last_active_day = -1
            execution.last_active_hour = -1
            execution.expected_duration_rounds = expected
        else:
            db.session.add(
                Client_Execution(
                    client_id=client.id,
                    elapsed_time=0,
                    last_active_day=-1,
                    last_active_hour=-1,
                    expected_duration_rounds=expected,
                )
            )

    exp.running = 0
    exp.status = 0
    exp.exp_status = "stopped"
    stats = db.session.scalars(select(Exp_stats).filter_by(exp_id=exp.idexp)).first()
    if stats is None:
        db.session.add(Exp_stats(exp_id=exp.idexp, rounds=0, agents=0, posts=0, reactions=0, mentions=0))
    else:
        stats.rounds = stats.agents = stats.posts = stats.reactions = stats.mentions = 0
    for model in (LogFileOffset, ServerLogMetrics, ClientLogMetrics, OpinionEvolutionCache, OpinionEvolutionSampledAgents):
        db.session.query(model).filter_by(exp_id=exp.idexp).delete()
    db.session.commit()
    return {"restored": restored, "removed": removed, "database": database, "failed": failed}
