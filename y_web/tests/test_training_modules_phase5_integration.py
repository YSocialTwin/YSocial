"""Phase 5 (G5) integration: runs, bindings and enrollments of the real plugin
against the real core tables (``exps``, ``admin_users``). Skips without the plugin."""

import json
import re
import uuid

import pytest
from werkzeug.security import generate_password_hash

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    _scenario_step,
    requires_plugin,
)


def _experiment(app, owner, *, status=1, platform="microblogging", simulator="Standard"):
    from y_web import db
    from y_web.src.models import Exps

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        row = Exps(
            platform_type=platform, exp_name=f"exp{tag}", db_name=f"db{tag}", owner=owner, exp_descr="d",
            status=status, running=0, port=5000 + int(tag[:3], 16) % 1000, simulator_type=simulator,
        )
        db.session.add(row)
        db.session.commit()
        return row.idexp


def _participant(app, role="user"):
    from y_web import db
    from y_web.src.models import Admin_users

    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        row = Admin_users(username=f"s{tag}", email=f"s{tag}@example.test", password=generate_password_hash("x"),
                          last_seen="2026-01-01", role=role)
        db.session.add(row)
        db.session.commit()
        return row.username, row.email


def _exp_rows(app):
    from y_web import db
    from y_web.src.models import Admin_users, Exps

    with app.app_context():
        return (
            [(e.idexp, e.exp_name, e.status, e.running, e.exp_status, e.platform_type) for e in Exps.query.order_by(Exps.idexp)],
            [(u.id, u.username, u.email, u.role) for u in Admin_users.query.order_by(Admin_users.id)],
        )


def _published_module(client, slots=1):
    uid = _post(client, f"{API}/modules", {"title": "Run module"}).get_json()["module"]["module_uid"]
    rev = 1
    for i in range(slots):
        rev = _scenario_step(client, uid, rev, f"s{i + 1}").get_json()["revision"]
    r = _post(client, f"{API}/modules/{uid}/versions/1/publish", {"revision": rev})
    assert r.status_code == 200, r.get_json()
    return uid


@requires_plugin
def test_run_lifecycle_with_real_experiments_and_pseudonymous_enrollment(core_app):
    admin = _client_as(core_app, "admin")
    uid = _published_module(admin)
    exp = _experiment(core_app, "someone")
    stopped = _experiment(core_app, "someone", status=0)
    forum = _experiment(core_app, "someone", platform="forum")
    user_name, user_mail = _participant(core_app, "user")
    student_name, _ = _participant(core_app, "student")
    researcher_name, _ = _participant(core_app, "researcher")

    run = _post(admin, f"{API}/runs", {"module_uid": uid, "version_no": 1, "name": "Real run"}).get_json()["run"]
    rid = run["id"]
    key = admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"][0]["step_key"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 409  # slot not bound
    r = admin.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": forum}, headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 422 and r.get_json()["error"] == "platform_mismatch"
    # a stopped experiment can be chosen (the run page offers to switch it on); the run cannot start with it
    r = admin.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": stopped}, headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 200 and r.get_json()["binding"]["problems"] == ["experiment_not_activated"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 409
    assert admin.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": exp}, headers={"X-CSRF-Token": "tok"}).status_code == 200

    before = _exp_rows(core_app)
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    csv_text = f"{user_name}\n{student_name}\n{user_mail.upper()}\n{researcher_name}\nnobody-here\n"
    r = _post(admin, f"{API}/runs/{rid}/enrollments/import", {"csv": csv_text})
    assert r.status_code == 201
    assert r.get_json()["summary"] == {"enrolled": 2, "duplicate": 1, "role_not_allowed": 1, "not_found": 1}
    blob = json.dumps(r.get_json()) + admin.get(f"/admin/training/runs/{rid}").get_data(as_text=True)
    for secret in (user_name, student_name, user_mail, researcher_name):
        assert secret not in blob
    assert re.findall(r"<code>(P[A-Z0-9]{8})</code>", blob)

    code = admin.get(f"{API}/runs/{rid}/enrollments").get_json()["enrollments"][0]["participant_code"]
    assert _post(admin, f"{API}/runs/{rid}/enrollments/{code}/withdraw").status_code == 200
    assert _post(admin, f"{API}/runs/{rid}/enrollments/{code}/readmit").status_code == 200
    assert _post(admin, f"{API}/runs/{rid}/pause").status_code == 200
    assert _post(admin, f"{API}/runs/{rid}/close").status_code == 200
    assert _exp_rows(core_app) == before  # nothing in the core changed


@requires_plugin
def test_researcher_sees_only_visible_experiments_and_own_runs(core_app):
    researcher = _client_as(core_app, "researcher")
    other = _client_as(core_app, "researcher")
    admin = _client_as(core_app, "admin")
    uid = _published_module(researcher)
    rid = _post(researcher, f"{API}/runs", {"module_uid": uid, "version_no": 1, "name": "Mine"}).get_json()["run"]["id"]
    foreign = _experiment(core_app, "an-unrelated-owner")
    key = researcher.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"][0]["step_key"]
    r = researcher.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": foreign}, headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 404 and r.get_json()["error"] == "experiment_not_found"
    ids = {e["exp_id"] for e in researcher.get(f"{API}/runs/{rid}/experiments").get_json()["experiments"]}
    assert foreign not in ids
    assert admin.get(f"{API}/runs/{rid}").status_code == 200
    assert other.get(f"{API}/runs/{rid}").status_code == 404
