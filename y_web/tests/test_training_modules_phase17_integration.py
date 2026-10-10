"""Phase 17 (G17) integration: scheduled wait, closing with certificate and progress panel against the real core. Skips without the plugin."""

import re
from datetime import datetime, timedelta

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _participant)
from y_web.tests.test_training_modules_phase10_integration import _count
from y_web.tests.test_training_modules_phase12_integration import _publish

PLATFORM, SIMULATOR = PLATFORMS[0]
WAIT = {"title": "Rest", "intro": "Come back soon.", "mode": "after_days", "days": 1, "at": ""}
CLOSE = {"title": "Well done", "intro": "", "closing_text": "", "button_label": "",
         "certificate": {"enabled": True, "title": "Certificate of participation", "text": "Completed.", "issuer": "The team"}}


@requires_plugin
def test_wait_closing_and_panel_through_the_real_core(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    clock = {"now": datetime(2026, 10, 1, 9, 0)}
    app.config["TM_NOW"] = lambda: clock["now"]
    wait, close = _publish(admin, "scheduled_wait", WAIT, "Wait"), _publish(admin, "closing", CLOSE, "Close")
    module = _post(admin, f"{API}/modules", {"title": "Path module"}).get_json()["module"]["module_uid"]
    rev, keys = 1, []
    for kind, inst in (("scheduled_wait", wait), ("closing", close)):
        step = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
            "type": "component", "component_ref": f"tm_native:{kind}", "title": kind, "revision": rev, "no": 99,
            "config": {"settings": {"instance_uid": inst, "instance_version": 1}}})
        assert step.status_code == 201, step.get_json()
        rev = step.get_json()["revision"]
        keys.append(step.get_json()["step"]["step_key"])
    assert _post(admin, f"{API}/modules/{module}/versions/1/publish", {"revision": rev}).status_code == 200
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Path run"}).get_json()["run"]["id"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    exp = _experiment(app, PLATFORM, SIMULATOR)
    account, _, email = _participant(app, exp)
    assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}).status_code == 201

    me = app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    run_page = me.get(f"/training/runs/{rid}").get_data(as_text=True)
    assert "opens on 2026-10-02 09:00 UTC" in run_page and email not in run_page
    token = re.search(r'name="csrf_token" value="([^"]+)"', run_page).group(1)
    one, two = (f"/training/runs/{rid}/steps/{k}" for k in keys)

    panel = admin.get(f"{API}/runs/{rid}/panel").get_json()
    dumped = str(panel)
    assert panel["enrolled"] == 1 and panel["steps"][0]["counts"]["scheduled"] == 1 and email not in dumped
    assert me.get(f"/admin/training/api/runs/{rid}/panel").status_code in (302, 401, 403)     # a participant is not staff
    assert me.post(one + "/start", data={"csrf_token": token}).status_code == 303
    assert me.post(one + "/submit", data={"csrf_token": token}).status_code == 422             # only the clock opens it
    assert me.get(two + "/certificate").status_code in (403, 404, 409)

    clock["now"] += timedelta(days=1, minutes=1)
    me.get(f"/training/runs/{rid}")
    assert _count(app, "SELECT COUNT(*) FROM tm_step_progress WHERE status='completed'") == 1
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='wait_elapsed'") == 1
    assert me.post(two + "/start", data={"csrf_token": token}).status_code == 303
    assert me.get(two + "/certificate").status_code == 409
    assert me.post(two + "/submit", data={"csrf_token": token}).status_code == 303
    cert = me.get(two + "/certificate")
    body = cert.get_data(as_text=True)
    assert cert.status_code == 200 and "Certificate of participation" in body and email not in body and "attachment" in cert.headers["Content-Disposition"]
    assert admin.get(f"{API}/runs/{rid}/panel").get_json()["finished"] == 1
