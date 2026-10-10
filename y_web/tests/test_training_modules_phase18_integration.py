"""Phase 18 (G18) integration: branching by answer and the "skipped" state against the real core. Skips without the plugin."""

import re

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _participant)
from y_web.tests.test_training_modules_phase10_integration import LIB, _count
from y_web.tests.test_training_modules_phase12_integration import _publish

PLATFORM, SIMULATOR = PLATFORMS[0]
ROUTE = {
    "title": "Route", "intro": "", "closing_text": "", "button_label": "",
    "settings": {"one_page_at_a_time": False, "progress_bar": False, "autosave": False, "privacy_notice": False},
    "pages": [{"id": "p1", "title": "", "items": [
        {"id": "route", "type": "single_choice", "label": "Pick one", "required": True,
         "options": [{"id": "a", "label": "Route A"}, {"id": "b", "label": "Route B"}]}]}],
}
ONB = {"title": "Welcome", "subtitle": "", "button_label": "", "blocks": [
    {"id": "ok", "type": "confirmations", "items": [{"id": "read", "label": "I have read this page", "required": True}]}]}


@requires_plugin
def test_branching_through_the_real_core(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    route, onb = _publish(admin, "questionnaire", ROUTE, "Route"), _publish(admin, "onboarding", ONB, "Welcome")
    module = _post(admin, f"{API}/modules", {"title": "Branching"}).get_json()["module"]["module_uid"]
    rev, keys = 1, []
    for title, kind, inst, rule in (("route", "questionnaire", route, None), ("a", "onboarding", onb, "a"), ("b", "onboarding", onb, "b"), ("end", "onboarding", onb, None)):
        config = {"settings": {"instance_uid": inst, "instance_version": 1}}
        if rule:
            config["visibility"] = {"type": "answer", "step": keys[0], "cond": {"q": "route", "op": "eq", "value": rule}}
        step = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
            "type": "component", "component_ref": f"tm_native:{kind}", "title": title, "revision": rev, "config": config,
            "completion_policy": {"signal_mode": "verified", "criteria": []}})
        assert step.status_code == 201, step.get_json()
        rev = step.get_json()["revision"]
        keys.append(step.get_json()["step"]["step_key"])
    assert _post(admin, f"{API}/modules/{module}/versions/1/publish", {"revision": rev}).status_code == 200
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Branching run"}).get_json()["run"]["id"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    exp = _experiment(app, PLATFORM, SIMULATOR)
    account, _, email = _participant(app, exp)
    assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}).status_code == 201

    me = app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    token = re.search(r'name="csrf_token" value="([^"]+)"', me.get(f"/training/runs/{rid}").get_data(as_text=True)).group(1)
    url = lambda i: f"/training/runs/{rid}/steps/{keys[i]}"
    assert me.post(url(0) + "/start", data={"csrf_token": token}).status_code == 303
    assert me.post(url(0) + "/submit", data={"csrf_token": token, "q_route": "a"}).status_code == 303
    assert me.post(url(1) + "/start", data={"csrf_token": token}).status_code == 303
    assert me.post(url(1) + "/submit", data={"csrf_token": token, "ack": "read"}).status_code == 303
    assert _count(app, "SELECT COUNT(*) FROM tm_step_progress WHERE status='skipped'") == 1
    page = me.get(f"/training/runs/{rid}").get_data(as_text=True)
    assert keys[2] not in page and email not in page                                       # a skipped step is not shown
    assert me.post(url(2) + "/start", data={"csrf_token": token}).status_code == 403       # and cannot be reached
    assert me.get(url(2) + "/page").status_code == 403
    assert me.post(url(3) + "/start", data={"csrf_token": token}).status_code == 303
    assert me.post(url(3) + "/submit", data={"csrf_token": token, "ack": "read"}).status_code == 303
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='module_completed'") == 1
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='step_skipped'") == 1
