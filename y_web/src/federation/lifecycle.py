"""Export, clone and reset of a World Simulation (F7.3).

The mechanisms of a single experiment are reused: the archive of each member is the one of "Download experiment"
(``_build_single_experiment_zip``) and the copy of each member is the one of "Copy experiment"
(``_create_single_experiment_copy``). Both are injected so that the logic can be tested without them.

- ``export_bundle``: a zip with ``world_simulation.json`` (name, seed, granularity, options, members, identity,
  SHA-256 of every other file), ``federation.db`` (a consistent copy, made with the SQLite backup API), the derived
  analytics when they exist, and one archive per member under ``members/``. The token is never exported.
- ``import_bundle``: the opposite of the export. Checks the SHA-256 of every file, imports each member archive as a new
  experiment (the machinery of "Upload experiment") and creates the World Simulation with the same seed, granularity,
  options and the same ``federation_id`` when it is free (the id enters the message ids and so the draws of the run).
  When the identity map is the same and that id could be kept, the coordinator database is restored too, so the run
  resumes where it stopped; otherwise the World Simulation starts fresh and the report says why.
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


def _humans_of(fed) -> list:
    """F8: the people enrolled ({user_id, human_id, members, status}); an additive key of the manifest."""
    from y_web.src.federation import humans

    return [{"user_id": h.user_id, "human_id": h.human_id, "members": humans.members_state(h), "status": h.status}
            for h in humans.list_humans(fed)]


def manifest(fed) -> dict:
    from y_web.src.models.admin import FederationIdentityLink

    options = json.loads(fed.config_json or "{}")
    links = db.session.query(FederationIdentityLink).filter_by(federation_pk=fed.id).order_by(FederationIdentityLink.id).all()
    return {
        "bundle_version": BUNDLE_VERSION,
        "name": fed.name,
        "federation_id": fed.federation_id,
        "seed": fed.seed,
        "granularity": fed.granularity,
        "options": {k: v for k, v in options.items() if k != "exposures"},
        "exposures": bool(options.get("exposures", False)),
        "members": [{"member": row.member, "platform_type": row.platform_type, "exp_name": exp.exp_name,
                     "archive": f"members/{row.member}.zip"} for row, exp in service.members_of(fed)],
        "identity": [{"global_agent_id": l.global_agent_id, "member": l.member, "local_account_id": l.local_account_id,
                      "username": l.username} for l in links],
        "humans": _humans_of(fed),
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


# -- import ---------------------------------------------------------------------------------------------------
def _default_member_import(archive_path, name):
    """Import one member archive with the real "Upload experiment" route, as the user who is importing."""
    from flask import current_app
    from flask_login import current_user
    from sqlalchemy import select

    from y_web.src.models import Exps

    client = current_app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = current_user.get_id()
        session["_fresh"] = True
    with open(archive_path, "rb") as handle:
        client.post("/admin/upload_experiment", data={"experiment": (handle, "exp.zip"), "exp_name": name, "exp_group": ""},
                    content_type="multipart/form-data")
    db.session.expire_all()
    exp = db.session.scalars(select(Exps).filter_by(exp_name=name)).first()
    if exp is None:
        raise WorldSimulationError({"code": "upload", "message": f"The experiment '{name}' could not be imported."})
    return exp


def read_bundle(path) -> dict:
    """The manifest of a bundle after checking its structure and the SHA-256 of every file."""
    try:
        with zipfile.ZipFile(path) as bundle:
            data = json.loads(bundle.read("world_simulation.json"))
            if data.get("bundle_version") != BUNDLE_VERSION:
                raise WorldSimulationError({"code": "bundle", "message": "This bundle has a version this release cannot read."})
            for name, digest in data["files"].items():
                if hashlib.sha256(bundle.read(name)).hexdigest() != digest:
                    raise WorldSimulationError({"code": "bundle", "message": f"The file '{name}' of the bundle is damaged."})
            for member in data["members"]:
                if member["archive"] not in data["files"]:
                    raise WorldSimulationError({"code": "bundle", "message": f"The archive of '{member['member']}' is missing."})
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise WorldSimulationError({"code": "bundle", "message": f"This is not a World Simulation bundle ({exc})."})
    return data


def _identity_of_database(path):
    """``{(global_agent_id, member, account)}``; the account of an agent is reported by its runtime (INV-17), so for agents it
    is ``None`` here: only the pairs count. Placeholders without an account (agents that can still discover a platform) are
    not accounts."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {(str(g), m, str(a) if str(g).startswith("human:") else None)
                for g, m, a in conn.execute("SELECT global_agent_id, member, local_account_id FROM federation_identity")
                if a is not None}
    finally:
        conn.close()


def _restore_humans(fed, data) -> None:
    """F8: the people enrolled in the exported World Simulation, with the accounts the member databases already hold
    (the archives carry them), so the identity map is the same and the coordinator database can be restored."""
    from y_web.src.federation.humans import is_human_id
    from y_web.src.models.admin import FederationHuman, FederationIdentityLink

    for h in data.get("humans") or []:
        db.session.add(FederationHuman(federation_pk=fed.id, user_id=int(h["user_id"]), human_id=h["human_id"],
                                       members_json=json.dumps(h["members"], sort_keys=True), status=h.get("status", "active")))
    for link in data.get("identity") or []:
        if is_human_id(link["global_agent_id"]):
            db.session.add(FederationIdentityLink(federation_pk=fed.id, global_agent_id=link["global_agent_id"],
                                                  member=link["member"], local_account_id=link["local_account_id"]))
    db.session.commit()
    if data.get("humans"):
        service.write_federation_files(fed)


def import_bundle(path, owner="", name=None, member_import=None):
    """Create a World Simulation from a bundle; returns ``(fed, report)``."""
    from y_web.src.models.admin import Federation, FederationIdentityLink

    member_import = member_import or _default_member_import
    data = read_bundle(path)
    new_name = (name or data["name"]).strip()
    if not new_name:
        raise WorldSimulationError({"code": "name", "message": "The World Simulation needs a name."})
    report = {"restored_database": False, "federation_id_kept": False, "notes": []}
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(path) as bundle:
        imported = []
        for member in data["members"]:
            archive = bundle.extract(member["archive"], tmp)
            exp = member_import(archive, f"{new_name}_{member['member']}"[:50])
            if exp.platform_type != member["platform_type"]:
                raise WorldSimulationError({"code": "platform", "message": f"'{exp.exp_name}' is {exp.platform_type}, not {member['platform_type']}."})
            imported.append(exp)
        fed = service.create_federation(new_name, [e.idexp for e in imported], owner=owner, seed=data["seed"],
                                        granularity=data["granularity"], options=data["options"], exposures=data["exposures"])
        wanted = str(data.get("federation_id") or "")
        if wanted and fed.federation_id != wanted:
            if db.session.query(Federation).filter_by(federation_id=wanted).first() is None:
                fed.federation_id = wanted
                service.write_federation_files(fed)
                db.session.commit()
        _restore_humans(fed, data)
        report["federation_id_kept"] = fed.federation_id == wanted
        if not report["federation_id_kept"]:
            report["notes"].append("The identifier of the bundle is already in use: the World Simulation starts fresh.")
        elif "federation.db" in data["files"]:
            stored = bundle.extract("federation.db", tmp)
            links = {(l.global_agent_id, l.member, l.local_account_id if l.global_agent_id.startswith("human:") else None)
                     for l in db.session.query(FederationIdentityLink).filter_by(federation_pk=fed.id).all()}
            if not _identity_of_database(stored) <= links:  # the pairs that were bound are a subset of the declared ones
                report["notes"].append("The agents of the imported experiments differ from those of the bundle: the World Simulation starts fresh.")
            else:
                conn = sqlite3.connect(stored, isolation_level=None)
                try:
                    for row, exp in service.members_of(fed):
                        conn.execute("UPDATE federation_member SET exp_id=? WHERE member=?", (str(exp.idexp), row.member))
                    conn.execute("PRAGMA journal_mode=DELETE")
                finally:
                    conn.close()
                shutil.copyfile(stored, os.path.join(fed.folder, "federation.db"))
                report["restored_database"] = True
        if "analytics_federation.db" in data["files"] and report["restored_database"]:
            shutil.copyfile(bundle.extract("analytics_federation.db", tmp), os.path.join(fed.folder, "analytics_federation.db"))
    return fed, report
