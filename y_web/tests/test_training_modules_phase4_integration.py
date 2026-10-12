"""Phase 4 (G4) integration: export/import of module definitions with the real
plugin inside the real core. Skips when the plugin is not checked out."""

import json

import pytest

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    _scenario_step,
    requires_plugin,
)


def _import(client, payload, as_copy=False):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return client.post(
        f"{API}/import" + ("?as_copy=1" if as_copy else ""),
        data=raw,
        headers={"X-CSRF-Token": "tok"},
        content_type="application/json",
    )


def _module_with_two_steps(client, title):
    uid = _post(client, f"{API}/modules", {"title": title}).get_json()["module"][
        "module_uid"
    ]
    rev = _scenario_step(client, uid, 1, "s1").get_json()["revision"]
    assert _scenario_step(client, uid, rev, "s2").status_code == 201
    return uid


@requires_plugin
def test_export_has_no_ids_urls_or_student_data_and_round_trips(core_app):
    admin = _client_as(core_app, "admin")
    uid = _module_with_two_steps(admin, "Portable")
    resp = admin.get(f"{API}/modules/{uid}/versions/1/export")
    assert (
        resp.status_code == 200 and "attachment" in resp.headers["Content-Disposition"]
    )
    doc = json.loads(resp.get_data(as_text=True))
    text = json.dumps(doc)
    for banned in ("exp_id", "http://", "https://", "secret", "participant"):
        assert banned not in text
    assert doc["schema"] == "ysocial.training_module" and len(doc["steps"]) == 2

    # same installation, same hash: nothing to do
    noop = _import(admin, doc)
    assert noop.status_code == 200 and noop.get_json()["result"] == "noop"
    # as a copy: a new module whose re-export is internally consistent
    copy = _import(admin, doc, as_copy=True)
    assert copy.status_code == 201
    new_uid = copy.get_json()["module_uid"]
    again = json.loads(
        admin.get(f"{API}/modules/{new_uid}/versions/1/export").get_data(as_text=True)
    )
    assert again["content_hash"] == copy.get_json()["content_hash"]
    assert [s["config"] for s in again["steps"]] == [s["config"] for s in doc["steps"]]


@requires_plugin
def test_tampered_import_is_rejected_without_writes(core_app):
    admin = _client_as(core_app, "admin")
    uid = _module_with_two_steps(admin, "Tamper")
    doc = json.loads(
        admin.get(f"{API}/modules/{uid}/versions/1/export").get_data(as_text=True)
    )
    before = admin.get(f"{API}/modules").get_json()["modules"]
    bad = json.loads(json.dumps(doc))
    bad["steps"][0]["title"] = "edited"
    r = _import(admin, bad, as_copy=True)
    assert r.status_code == 422 and r.get_json()["error"] == "hash_mismatch"
    r = _import(admin, dict(doc, schema_version="2.0.0"), as_copy=True)
    assert (
        r.status_code == 422 and r.get_json()["error"] == "unsupported_schema_version"
    )
    assert admin.get(f"{API}/modules").get_json()["modules"] == before


@requires_plugin
def test_import_is_staff_only(core_app):
    admin = _client_as(core_app, "admin")
    uid = _module_with_two_steps(admin, "Staff only")
    doc = json.loads(
        admin.get(f"{API}/modules/{uid}/versions/1/export").get_data(as_text=True)
    )
    anonymous = core_app.test_client()
    assert anonymous.get(f"{API}/modules/{uid}/versions/1/export").status_code in (
        302,
        401,
        403,
    )
    assert anonymous.post(
        f"{API}/import", data=b"{}", content_type="application/json"
    ).status_code in (302, 401, 403)
    other = _client_as(core_app, "researcher")
    assert other.get(f"{API}/modules/{uid}/versions/1/export").status_code == 404
    assert _import(other, doc).status_code == 409  # module_uid_taken
