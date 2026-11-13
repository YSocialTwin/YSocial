"""Clone, reset, download and upload of dating experiments (plan S4, IR-D-12).

A dating run lives in its own folder: inputs (server and client configuration, populations) and run
artifacts (database and SQLite sidecars, run lock, Ray markers, client summaries, logs, exports,
derived analytics). A clone copies the inputs only; a reset removes the artifacts only. The clone starts
without a run lock, so its settings are editable again, and keeps the seed: the same seed gives the same run.
"""

import fnmatch
import json
import os
import shutil
import sqlite3
import uuid
from typing import List, Tuple

from y_web.src.dating import DATING_MARKER_TABLE
from y_web.src.im.clone import rewrite_server_config  # noqa: F401  (same host keys)

RUN_ARTIFACT_DIRS = ("logs", "reports", "exports", "_hpc_population_backups")
RUN_ARTIFACT_PATTERNS = (
    "database_server.db",
    "database_server.db-wal",
    "database_server.db-shm",
    "database_server.db-journal",
    "analytics_dating.db*",
    "analytics_dating.status.json",
    "run_lock.json",
    "run_lock.json.tmp",
    "ray_*.temp",
    "client_summary_*.json",
    "human_gateway.*",
    "*.log",
    "*.log.*",
)


def is_run_artifact(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in RUN_ARTIFACT_PATTERNS)


def clear_dating_run_artifacts(exp_folder: str) -> Tuple[int, List[str]]:
    """Remove what a run left in ``exp_folder`` and keep every input; ``logs`` is emptied, not removed."""
    removed, failed = 0, []
    if not exp_folder or not os.path.isdir(exp_folder):
        return removed, failed
    for entry in os.listdir(exp_folder):
        path = os.path.join(exp_folder, entry)
        try:
            if os.path.isdir(path):
                if entry in ("reports", "exports", "_hpc_population_backups"):
                    shutil.rmtree(path)
                    removed += 1
                elif entry == "logs":
                    for name in os.listdir(path):
                        target = os.path.join(path, name)
                        if os.path.isdir(target):
                            shutil.rmtree(target)
                        else:
                            os.remove(target)
                        removed += 1
            elif is_run_artifact(entry):
                os.remove(path)
                removed += 1
        except OSError:
            failed.append(path)
    return removed, failed


def copy_dating_folder(source_folder: str, new_folder: str) -> None:
    """Copy the inputs of ``source_folder`` into the new ``new_folder`` (created here)."""
    os.makedirs(new_folder)
    for entry in os.listdir(source_folder):
        if entry in RUN_ARTIFACT_DIRS or is_run_artifact(entry):
            continue
        source = os.path.join(source_folder, entry)
        target = os.path.join(new_folder, entry)
        if os.path.isdir(source):
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    os.makedirs(os.path.join(new_folder, "logs"), exist_ok=True)


def new_uid() -> str:
    return str(uuid.uuid4()).replace("-", "_")


def snapshot_for_download(folder: str, staging_dir: str) -> str:
    """A consistent copy of a (possibly running) dating experiment folder in ``staging_dir``.

    The database is copied with SQLite's online backup API, so ``-wal``/``-shm`` of a running server are
    neither needed nor included; the derived analytics database is left out (it is rebuilt on demand).
    """
    os.makedirs(staging_dir, exist_ok=True)
    for entry in os.listdir(folder):
        if entry.startswith(("database_server.db", "analytics_dating.")):
            continue
        source = os.path.join(folder, entry)
        target = os.path.join(staging_dir, entry)
        if os.path.isdir(source):
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    db_file = os.path.join(folder, "database_server.db")
    if os.path.exists(db_file):
        source_conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True, timeout=30)
        target_conn = sqlite3.connect(os.path.join(staging_dir, "database_server.db"))
        try:
            source_conn.backup(target_conn)
        finally:
            target_conn.close()
            source_conn.close()
    return staging_dir


def is_dating_folder(folder: str) -> bool:
    """True when an unpacked experiment folder is a dating one.

    Checked before YWeb touches an uploaded folder: the YSocial schema must never reach a dating database.
    The server configuration names the platform; the marker table settles a folder that only has a database.
    """
    config_path = os.path.join(folder, "server_config.json")
    if not os.path.isfile(config_path):
        return False
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            if json.load(handle).get("platform_type") == "dating":
                return True
    except (OSError, ValueError, AttributeError):
        pass
    db_path = os.path.join(folder, "database_server.db")
    if not os.path.isfile(db_path):
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (DATING_MARKER_TABLE,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return row is not None


def slots_per_day(folder: str, default: int = 24) -> int:
    """Rounds per simulated day of the experiment (``simulation.num_slots_per_day``)."""
    try:
        with open(os.path.join(folder, "server_config.json"), encoding="utf-8") as fh:
            return int(json.load(fh)["simulation"]["num_slots_per_day"])
    except (OSError, ValueError, KeyError, TypeError):
        return default
