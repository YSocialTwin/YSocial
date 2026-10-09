"""Phase 11 (G11) integration: the native Questionnaire against the real core. Skips without the plugin."""

import io
import re
import zipfile

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _participant)
from y_web.tests.test_training_modules_phase10_integration import LIB, _count

PLATFORM, SIMULATOR = PLATFORMS[0]
QUESTIONNAIRE = {
    "title": "Core check", "intro": "Answer **freely**.", "closing_text": "", "button_label": "",
    "settings": {"one_page_at_a_time": False, "progress_bar": True, "autosave": True, "privacy_notice": True},
    "pages": [{"id": "p1", "title": "", "items": [
        {"id": "agree", "type": "consent", "label": "I agree to take part", "required": True},
        {"id": "mood", "type": "likert", "label": "How was it?", "points": 5, "required": True},
        {"id": "note", "type": "long_text", "label": "Anything to add?", "max_length": 200},
    ]}],
}


@requires_plugin
def test_native_questionnaire_end_to_end_through_the_real_core(core_app):
    app, admin = core_app, _client_as(core_app, "admin")
    created = _post(admin, f"{LIB}/instances", {"kind": "questionnaire", "title": "Core check"}).get_json()["instance"]
    uid = created["instance_uid"]
    saved = admin.put(f"{LIB}/instances/{uid}/draft", json={"revision": 1, "definition": QUESTIONNAIRE}, headers={"X-CSRF-Token": "tok"})
    assert saved.status_code == 200 and saved.get_json()["problems"] == []
    assert _post(admin, f"{LIB}/instances/{uid}/publish", {"revision": 2}).status_code == 200
    module = _post(admin, f"{API}/modules", {"title": "Survey only"}).get_json()["module"]["module_uid"]
    step = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
        "type": "component", "component_ref": "tm_native:questionnaire", "title": "Check", "revision": 1,
        "config": {"settings": {"instance_uid": uid, "instance_version": 1}}})
    assert step.status_code == 201, step.get_json()
    key = step.get_json()["step"]["step_key"]
    assert _post(admin, f"{API}/modules/{module}/versions/1/publish", {"revision": step.get_json()["revision"]}).status_code == 200
    exp = _experiment(app, PLATFORM, SIMULATOR)
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Survey run"}).get_json()["run"]["id"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    account, username, email = _participant(app, exp)
    assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}).status_code == 201

    me = app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    token = re.search(r'name="csrf_token" value="([^"]+)"', me.get(f"/training/runs/{rid}").get_data(as_text=True)).group(1)
    assert me.post(f"/training/runs/{rid}/steps/{key}/start", data={"csrf_token": token}).status_code == 303
    page = me.get(f"/training/runs/{rid}/steps/{key}/page").get_data(as_text=True)
    assert "Core check" in page and "<strong>freely</strong>" in page and "<fieldset" in page and "I agree to take part" in page
    assert username not in page and email not in page
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='form_started'") == 1
    url = f"/training/runs/{rid}/steps/{key}"
    assert me.post(url + "/submit", data={"csrf_token": token, "q_agree": "1"}).status_code == 422          # the scale is required
    assert me.post(url + "/submit", data={"q_agree": "1", "q_mood": "4"}).status_code == 403                 # no CSRF token
    assert _count(app, "SELECT COUNT(*) FROM tm_component_response WHERE status='submitted'") == 0
    sentinel = "CORE-SENTINEL-NOTE"
    ok = me.post(url + "/submit", data={"csrf_token": token, "q_agree": "1", "q_mood": "4", "q_note": sentinel})
    assert ok.status_code == 303
    assert me.post(url + "/submit", data={"csrf_token": token, "q_agree": "1", "q_mood": "1"}).status_code == 303   # replay
    assert _count(app, "SELECT COUNT(*) FROM tm_component_response WHERE status='submitted'") == 1
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='form_submitted' AND source='native'") == 1
    assert _count(app, "SELECT COUNT(*) FROM tm_step_progress WHERE status='completed' AND step_key=:k", k=key) == 1

    export = _post(admin, f"{API}/runs/{rid}/exports", {"reason": "native questionnaire check"})
    assert export.status_code == 200
    events = zipfile.ZipFile(io.BytesIO(export.data)).read("events.csv").decode()
    assert "form_submitted" in events and "verified" in events
    assert sentinel not in events and username not in events and email not in events     # answers never travel in events
