"""Clone and reset of instant messaging experiments (plan, 5.6).

An IM run lives in its own folder: inputs (configuration, population, topic catalog, news snapshot,
events) and run artifacts (database and its SQLite sidecars, state files, logs, exports, reports).
A clone copies the inputs only; a reset removes the artifacts only.
"""

import fnmatch
import json
import os
import shutil
import uuid
from typing import List, Tuple

#: Never copied to a clone and removed by a reset (``logs`` is recreated empty).
RUN_ARTIFACT_DIRS = ("logs", "reports", "exports", "_hpc_population_backups")
RUN_ARTIFACT_PATTERNS = (
    "database_server.db",
    "database_server.db-wal",
    "database_server.db-shm",
    "database_server.db-journal",
    "*.state.json",
    "ray_*.temp",
    "*.log",
    "*.log.*",
)


def is_run_artifact(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in RUN_ARTIFACT_PATTERNS)


def clear_im_run_artifacts(exp_folder: str) -> Tuple[int, List[str]]:
    """Remove what a run left in ``exp_folder`` and keep every input (``news_snapshot.jsonl`` included)."""
    removed, failed = 0, []
    if not exp_folder or not os.path.isdir(exp_folder):
        return removed, failed
    for entry in os.listdir(exp_folder):
        path = os.path.join(exp_folder, entry)
        try:
            if os.path.isdir(path):
                if entry in ("reports", "exports"):
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


def copy_im_folder(source_folder: str, new_folder: str) -> None:
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


def rewrite_server_config(new_folder: str, new_exp_name: str, new_db_uri: str, new_data_path: str) -> None:
    """Point the copied ``server_config.json`` at the new folder; the run configuration is unchanged."""
    path = os.path.join(new_folder, "server_config.json")
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    config["experiment_name"] = new_exp_name
    config["database_uri"] = new_db_uri
    config["data_path"] = new_data_path
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)


def new_uid() -> str:
    return str(uuid.uuid4()).replace("-", "_")
