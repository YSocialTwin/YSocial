"""Phase 16 (G16) integration: Guided task, scenario links and Recognition exercise against the real core. Skips without the plugin."""

import re

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _participant)
from y_web.tests.test_training_modules_phase10_integration import LIB, _count
from y_web.tests.test_training_modules_phase12_integration import _publish

PLATFORM, SIMULATOR = PLATFORMS[0]
GUIDED = {"title": "Practice", "intro": "", "button_label": "", "placeholder": "scenario", "placeholder_label": "Scenario", "tasks": [
    {"id": "t1", "label": "Write two posts or comments", "help": "", "criterion": {"type": "min_activity", "posts": 2, "reactions": 0}}]}
BANK = {"title": "Spot it", "intro": "", "closing_text": "", "button_label": "", "prompt": "How would you classify this post?",
        "settings": {"one_page_at_a_time": False, "progress_bar": False, "autosave": False, "privacy_notice": False},
        "scoring": {"enabled": True, "show": "items", "reveal_correct": True, "max_attempts": 1},
        "labels": [{"id": "reliable", "label": "Reliable"}, {"id": "misleading", "label": "Misleading"}], "items": []}
CSV = "id,author_label,text,correct\nc1,invented_a,Share before it is deleted!,misleading\nc2,invented_b,The meeting is on Tuesday.,reliable\n"


@requires_plugin
def test_guided_task_and_recognition_through_the_real_core(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    guided = _publish(admin, "guided_task", GUIDED, "Guided")
    created = _post(admin, f"{LIB}/instances", {"kind": "recognition", "title": "Bank"}).get_json()["instance"]
    uid, rev = created["instance_uid"], created["versions"][0]["revision"]
    saved = admin.put(f"{LIB}/instances/{uid}/draft", json={"revision": rev, "definition": BANK}, headers={"X-CSRF-Token": "tok"})
    assert saved.status_code == 200
    assert _post(admin, f"{LIB}/instances/{uid}/draft/import-items", {"revision": saved.get_json()["revision"], "csv": "bad,file\n1,2\n"}).status_code == 422
    imported = _post(admin, f"{LIB}/instances/{uid}/draft/import-items", {"revision": saved.get_json()["revision"], "csv": CSV})
    assert imported.status_code == 200 and imported.get_json()["imported"] == 2
    assert _post(admin, f"{LIB}/instances/{uid}/publish", {"revision": imported.get_json()["revision"]}).status_code == 200

    module = _post(admin, f"{API}/modules", {"title": "Practice module"}).get_json()["module"]["module_uid"]
    rev, keys = 1, []
    for kind, inst, settings in (("guided_task", guided, {"links": {"scenario": "s1"}}), ("recognition", uid, {})):
        step = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
            "type": "component", "component_ref": f"tm_native:{kind}", "title": kind, "revision": rev,
            "config": {"settings": dict({"instance_uid": inst, "instance_version": 1}, **settings)}})
        assert step.status_code == 201, step.get_json()
        rev = step.get_json()["revision"]
        keys.append(step.get_json()["step"]["step_key"])
    scenario = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
        "type": "scenario", "title": "Feed", "revision": rev,
        "config": {"slot_key": "s1", "hint_name": "Feed", "platform_type": PLATFORM, "simulator_type": SIMULATOR}})
    assert scenario.status_code == 201, scenario.get_json()
    rev = scenario.get_json()["revision"]
    assert _post(admin, f"{API}/modules/{module}/versions/1/publish", {"revision": rev}).status_code == 200

    exp = _experiment(app, PLATFORM, SIMULATOR)
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Practice run"}).get_json()["run"]["id"]
    slot = admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"][0]["step_key"]
    assert admin.put(f"{API}/runs/{rid}/bindings/{slot}", json={"exp_id": exp}, headers={"X-CSRF-Token": "tok"}).status_code == 200
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    account, _, email = _participant(app, exp)
    assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}).status_code == 201

    activity = {"posts": 0, "reactions": 0, "rounds": 1}
    app.config["TM_ACTIVITY_READER"] = lambda e, ext: dict(activity)
    me = app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    token = re.search(r'name="csrf_token" value="([^"]+)"', me.get(f"/training/runs/{rid}").get_data(as_text=True)).group(1)
    one, two = (f"/training/runs/{rid}/steps/{k}" for k in keys)
    assert me.post(one + "/start", data={"csrf_token": token}).status_code == 303
    page = me.get(one + "/page").get_data(as_text=True)
    assert "Write two posts" in page and "Feed" in page and email not in page
    assert me.post(one + "/submit", data={"csrf_token": token}).status_code == 422
    activity["posts"] = 2
    assert me.post(one + "/submit", data={"csrf_token": token}).status_code == 303
    assert me.post(two + "/start", data={"csrf_token": token}).status_code == 303
    quiz = me.get(two + "/page").get_data(as_text=True)
    assert "invented_a" in quiz and "simulated post" in quiz
    assert me.post(two + "/submit", data={"csrf_token": token, "q_c1": "misleading", "q_c2": "reliable"}).status_code == 303
    assert _count(app, "SELECT COUNT(*) FROM tm_step_progress WHERE status='completed'") == 2
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='task_completed'") == 1
