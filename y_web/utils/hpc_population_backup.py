"""Helpers for backing up/restoring HPC client population JSON files."""

import os
import re
import shutil

from y_web.utils.path_utils import get_writable_path


def _experiment_uid(experiment):
    """Return experiment UID from db_name for both sqlite and postgresql layouts."""
    db_name = getattr(experiment, "db_name", "") or ""
    if db_name.startswith("experiments_"):
        return db_name.removeprefix("experiments_")
    parts = re.split(r"[/\\]", db_name)
    if len(parts) >= 2:
        return parts[1]
    return None


def _experiment_dir(experiment):
    """Return absolute experiment directory or None."""
    uid = _experiment_uid(experiment)
    if not uid:
        return None
    base_dir = get_writable_path()
    return os.path.join(base_dir, "y_web", "experiments", uid)


def _population_json_candidates(exp_dir, population_name):
    """Return candidate population JSON paths used by different flows."""
    if not exp_dir or not population_name:
        return []
    compact = population_name.replace(" ", "")
    candidates = [
        os.path.join(exp_dir, f"{population_name}.json"),
        os.path.join(exp_dir, f"{compact}.json"),
    ]
    # Preserve order while removing duplicates.
    seen = set()
    unique = []
    for path in candidates:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def _backup_file_path(exp_dir, client, population):
    """Return deterministic backup path for a client/population pair."""
    backup_dir = os.path.join(exp_dir, "_hpc_population_backups")
    safe_pop = (
        re.sub(r"[^A-Za-z0-9_.-]+", "_", population.name or "population").strip("_")
        or "population"
    )
    filename = f"client_{client.id}_{safe_pop}.json"
    return backup_dir, os.path.join(backup_dir, filename)


def backup_population_for_hpc_client(experiment, client, population):
    """Create one-time backup of a client's population JSON before first start."""
    if getattr(experiment, "simulator_type", "") != "HPC":
        return None
    exp_dir = _experiment_dir(experiment)
    if not exp_dir or not population:
        return None

    source = None
    for candidate in _population_json_candidates(exp_dir, population.name):
        if os.path.exists(candidate):
            source = candidate
            break
    if not source:
        return None

    backup_dir, backup_file = _backup_file_path(exp_dir, client, population)
    if os.path.exists(backup_file):
        return backup_file

    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(source, backup_file)
    return backup_file


def restore_population_for_hpc_client(experiment, client, population):
    """Restore backed up population JSON for a client. Returns True if restored."""
    if getattr(experiment, "simulator_type", "") != "HPC":
        return False
    exp_dir = _experiment_dir(experiment)
    if not exp_dir or not population:
        return False

    _, backup_file = _backup_file_path(exp_dir, client, population)
    if not os.path.exists(backup_file):
        return False

    candidates = _population_json_candidates(exp_dir, population.name)
    target = None
    for candidate in candidates:
        if os.path.exists(candidate):
            target = candidate
            break
    if not target:
        target = candidates[0] if candidates else None
    if not target:
        return False

    shutil.copy2(backup_file, target)
    return True
