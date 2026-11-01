"""Export, clone and reset of a World Simulation (F7.3).

The mechanisms of a single experiment are reused: the archive of each member is the one of "Download experiment"
(``_build_single_experiment_zip``) and the copy of each member is the one of "Copy experiment"
(``_create_single_experiment_copy``). Both are injected so that the logic can be tested without them.

- ``export_bundle``: a zip with ``world_simulation.json`` (name, seed, granularity, options, members, identity,
  SHA-256 of every other file), ``federation.db`` (a consistent copy, made with the SQLite backup API), the derived
  analytics when they exist, and one archive per member under ``members/``. The token is never exported.
- ``clone``: copies every member experiment and creates a new, stopped World Simulation with the same seed,
  granularity and options. It starts from nothing: no coordinator database is copied.
- ``reset``: only for a stopped, completed or failed World Simulation; removes the coordinator database, the derived
  analytics and the log, and puts it back to *stopped*. The member experiments keep their own reset commands.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from y_web import db
from y_web.src.federation import service
from y_web.src.federation.service import WorldSimulationError

BUNDLE_VERSION = 1
IDLE = ("stopped", "completed", "failed")
RUN_FILES = ("federation.db", "federation.db-wal", "federation.db-shm", "analytics_federation.db",
             "analytics_federation.status.json", "coordinator.log")


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_member_zip(exp_id, path):
    from y_web.routes.admin.sub.experiments._notifications import _build_single_experiment_zip

    return _build_single_experiment_zip(exp_id, path)


def _default_copy(exp, name):
    """Copy one member with the machinery of "Copy experiment"; returns the new experiment."""
    from sqlalchemy import select

    from y_web.src.models import Exps
    from y_web.routes.admin.sub.experiments._crud import _create_single_experiment_copy

    if not _create_single_experiment_copy(exp, name, exp.exp_group or ""):
        raise WorldSimulationError({"code": "copy", "message": f"The experiment '{exp.exp_name}' could not be copied."})
    new = db.session.scalars(select(Exps).filter_by(exp_name=name)).first()
    if new is None:
        raise WorldSimulationError({"code": "copy", "message": f"The copy '{name}' was not found."})
    return new


def manifest(fed) -> dict:
    from y_web.src.models.admin import FederationIdentityLink

    options = json.loads(fed.config_json or "{}")
    links = db.session.query(FederationIdentityLink).filter_by(federation_pk=fed.id).order_by(FederationIdentityLink.id).all()
    return {
        "bundle_version": BUNDLE_VERSION,
        "name": fed.name,
        "seed": fed.seed,
        "granularity": fed.granularity,
        "options": {k: v for k, v in options.items() if k != "exposures"},
        "exposures": bool(options.get("exposures", False)),
        "members": [{"member": row.member, "platform_type": row.platform_type, "exp_name": exp.exp_name,
                     "archive": f"members/{row.member}.zip"} for row, exp in service.members_of(fed)],
        "identity": [{"global_agent_id": l.global_agent_id, "member": l.member, "local_account_id": l.local_account_id}
                     for l in links],
    }


def export_bundle(fed, out_path, member_zip=None) -> str:
    """Write the bundle to ``out_path`` (a .zip); returns the name to offer to the user."""
    member_zip = member_zip or _default_member_zip
    folder = Path(fed.folder)
    with tempfile.TemporaryDirectory() as tmp:
        files = {}
        source = folder / "federation.db"
        if source.is_file():
            dest = Path(tmp) / "federation.db"
            src = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=10)
            try:
                dst = sqlite3.connect(dest)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            files["federation.db"] = dest
        if (folder / "analytics_federation.db").is_file():
            files["analytics_federation.db"] = folder / "analytics_federation.db"
        members = service.members_of(fed)
        for row, exp in members:
            archive = Path(tmp) / f"{row.member}.zip"
            member_zip(exp.idexp, str(archive))
            files[f"members/{row.member}.zip"] = archive
        data = manifest(fed)
        data["files"] = {name: _sha256(path) for name, path in sorted(files.items())}
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("world_simulation.json", json.dumps(data, indent=2, sort_keys=True))
            for name, path in sorted(files.items()):
                bundle.write(path, name)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in fed.name) or f"world_simulation_{fed.id}"
    return f"{safe}.zip"


def clone(fed, new_name, owner="", copy=None):
    """Copy the member experiments and create a new, stopped World Simulation with the same parameters."""
    copy = copy or _default_copy
    new_name = (new_name or "").strip()
    if not new_name:
        raise WorldSimulationError({"code": "name", "message": "The copy needs a name."})
    options = json.loads(fed.config_json or "{}")
    copies = []
    for row, exp in service.members_of(fed):
        copies.append(copy(exp, f"{new_name}_{row.member}"[:50]))
    return service.create_federation(
        new_name, [c.idexp for c in copies], owner=owner or fed.owner, seed=fed.seed, granularity=fed.granularity,
        options={k: v for k, v in options.items() if k != "exposures"}, exposures=bool(options.get("exposures", False)),
    )


def reset(fed) -> list:
    """Back to *stopped* with no run data; returns the files removed."""
    if fed.status not in IDLE:
        raise WorldSimulationError({"code": "running", "message": "Stop the World Simulation before resetting it."})
    removed = []
    for name in RUN_FILES:
        path = os.path.join(fed.folder, name)
        if os.path.exists(path):
            os.remove(path)
            removed.append(name)
    fed.status = "stopped"
    db.session.commit()
    return removed
