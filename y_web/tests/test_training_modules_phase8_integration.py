"""Phase 8 (G8) integration: the activity export against the real core.

Real login/select_experiment, real experiment databases (one pass per platform), a participant whose
id inside the experiment differs from the account id, and rows under the account id as noise. The
package must be traceable to its manifest by hash, hold no username or e-mail, rebuild the activity
only through the identity map and be written to ``tm_export_log``. Skips without the plugin.
"""

import csv
import hashlib
import io
import json
import re
import zipfile

import pytest

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    requires_plugin,
)
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS,
    _experiment,
    _experiment_paths_under_tmp,
    _module,
    _participant,
    _post_as,
    _preexisting_platform_user,
)


def _rows(files, name):
    return list(csv.DictReader(io.StringIO(files[name].decode())))


@requires_plugin
@pytest.mark.parametrize(
    "platform,simulator", PLATFORMS, ids=[f"{p}-{s}" for p, s in PLATFORMS]
)
def test_export_through_the_real_core(core_app, platform, simulator):
    from sqlalchemy import text

    from y_web import db

    admin = _client_as(core_app, "admin")
    exp = _experiment(core_app, platform, simulator)
    uid = _module(admin, platform, simulator)
    rid = _post(
        admin, f"{API}/runs", {"module_uid": uid, "version_no": 1, "name": "G8 run"}
    ).get_json()["run"]["id"]
    keys = [
        b["step_key"]
        for b in admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"]
    ]
    for key in keys:
        assert (
            admin.put(
                f"{API}/runs/{rid}/bindings/{key}",
                json={"exp_id": exp},
                headers={"X-CSRF-Token": "tok"},
            ).status_code
            == 200
        )
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    account, username, email = _participant(core_app, exp)
    platform_id = 700000 + account
    _preexisting_platform_user(core_app, exp, username, email, platform_id)
    assert (
        _post(
            admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}
        ).status_code
        == 201
    )

    me = core_app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    me.get(f"/training/runs/{rid}")
    with me.session_transaction() as s:
        csrf = s["tm_csrf"]
    launch = me.post(
        f"/training/runs/{rid}/steps/{keys[0]}/start", data={"csrf_token": csrf}
    )
    token = re.search(
        r'name="auth_token" value="([^"]+)"', launch.get_data(as_text=True)
    ).group(1)
    assert (
        me.post(
            "/select_experiment", data={"experiment_id": exp, "auth_token": token}
        ).status_code
        == 302
    )
    _post_as(core_app, exp, account, 5, platform)  # noise under the account id
    _post_as(core_app, exp, platform_id, 2, platform)
    me.get(f"/training/runs/{rid}")

    # an export needs a reason, then comes back as a zip whose files match the manifest
    assert _post(admin, f"{API}/runs/{rid}/exports", {"reason": ""}).status_code == 422
    r = _post(
        admin,
        f"{API}/runs/{rid}/exports",
        {"reason": "integration check", "include_identity_map": True},
    )
    assert r.status_code == 200 and r.mimetype == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(r.data))
    files = {n: archive.read(n) for n in archive.namelist()}
    manifest = json.loads(files["manifest.json"])
    assert manifest["partial"] is False and r.headers["X-TM-Partial"] == "false"
    assert {f["name"] for f in manifest["files"]} == set(files) - {"manifest.json"}
    for entry in manifest["files"]:
        assert (
            hashlib.sha256(files[entry["name"]]).hexdigest() == entry["sha256"]
        ), entry["name"]
    first = _rows(files, "activity_s1.csv")
    assert len(first) == 2 and {x["external_user_id"] for x in first} == {
        str(platform_id)
    }  # not the 5 noise rows
    assert (
        _rows(files, "activity_s2.csv") and len(_rows(files, "participants.csv")) == 1
    )
    assert [
        (x["system_kind"], x["external_user_id"])
        for x in _rows(files, "identity_map.csv")
    ] == [("experiment", str(platform_id))]
    for name, content in files.items():
        blob = content.decode()
        assert username not in blob and email not in blob, name
    codes = {x["participant_code"] for x in _rows(files, "participants.csv")}
    assert {x["participant_code"] for x in _rows(files, "events.csv")} == codes

    with core_app.app_context():
        with db.engines["db_admin"].connect() as c:
            log = c.execute(
                text(
                    "SELECT file_sha256, reason, requested_by FROM tm_export_log WHERE export_uid = :u"
                ),
                {"u": manifest["export_uid"]},
            ).one()
    assert (
        log[0] == hashlib.sha256(r.data).hexdigest() and log[1] == "integration check"
    )

    # an experiment that cannot be read is reported, and the rest of the package is still delivered
    with core_app.app_context():
        with db.engines["db_admin"].begin() as c:
            c.execute(
                text("UPDATE exps SET db_name = :n WHERE idexp = :i"),
                {"n": "experiments/does_not_exist/x.db", "i": exp},
            )
    r = _post(
        admin, f"{API}/runs/{rid}/exports", {"reason": "after the database vanished"}
    )
    files = {
        n: zipfile.ZipFile(io.BytesIO(r.data)).read(n)
        for n in zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    }
    assert (
        r.status_code == 200 and json.loads(files["manifest.json"])["partial"] is True
    )
    assert (
        _rows(files, "source_errors.csv") and len(_rows(files, "participants.csv")) == 1
    )
