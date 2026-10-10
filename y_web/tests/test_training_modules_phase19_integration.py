"""Phase 19 (G19) integration: group work with a shared answer sheet against the real core. Skips without the plugin."""

import re

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _participant)
from y_web.tests.test_training_modules_phase10_integration import _count
from y_web.tests.test_training_modules_phase12_integration import _publish

PLATFORM, SIMULATOR = PLATFORMS[0]
TASK = {
    "title": "Together", "intro": "", "closing_text": "", "button_label": "", "min_members": 2,
    "settings": {"one_page_at_a_time": False, "progress_bar": False, "autosave": False, "privacy_notice": False},
    "pages": [{"id": "p1", "title": "", "items": [{"id": "plan", "type": "long_text", "label": "Your plan", "required": True}]}],
}


@requires_plugin
def test_group_work_through_the_real_core(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    inst = _publish(admin, "group_work", TASK, "Task")
    module = _post(admin, f"{API}/modules", {"title": "Group module"}).get_json()["module"]["module_uid"]
    step = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
        "type": "component", "component_ref": "tm_native:group_work", "title": "Together", "revision": 1,
        "config": {"settings": {"instance_uid": inst, "instance_version": 1}}, "completion_policy": {"signal_mode": "verified", "criteria": []}})
    assert step.status_code == 201, step.get_json()
    key = step.get_json()["step"]["step_key"]
    assert _post(admin, f"{API}/modules/{module}/versions/1/publish", {"revision": step.get_json()["revision"]}).status_code == 200
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Group run"}).get_json()["run"]["id"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    exp = _experiment(app, PLATFORM, SIMULATOR)
    (one, _, mail1), (two, _, mail2) = _participant(app, exp), _participant(app, exp)
    for account in (one, two):
        assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account], "group_label": "red"}).status_code == 201

    def login(mail):
        client = app.test_client()
        assert client.post("/login", data={"email": mail, "password": "x"}).status_code == 302
        return client, re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/training/runs/{rid}").get_data(as_text=True)).group(1)

    (c1, t1), (c2, t2) = login(mail1), login(mail2)
    url = f"/training/runs/{rid}/steps/{key}"
    assert c1.post(url + "/start", data={"csrf_token": t1}).status_code == 303
    assert c2.post(url + "/start", data={"csrf_token": t2}).status_code == 303
    assert "red" in c1.get(url + "/page").get_data(as_text=True) and mail2 not in c1.get(url + "/page").get_data(as_text=True)
    assert c1.post(url + "/submit", data={"csrf_token": t1, "q_plan": "Meet on Monday"}).status_code == 303
    assert _count(app, "SELECT COUNT(*) FROM tm_group_response WHERE status='submitted'") == 1
    assert _count(app, "SELECT COUNT(*) FROM tm_step_progress WHERE status='completed'") == 2          # one submission completes it for both
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='group_submitted'") == 2
    assert "Meet on Monday" in c2.get(url + "/page").get_data(as_text=True)
