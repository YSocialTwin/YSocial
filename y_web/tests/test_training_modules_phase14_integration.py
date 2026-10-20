"""Phase 14 (G14) integration: Lesson, External resource and Case study against the real core. Skips without the plugin."""

import re

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
    _participant,
)
from y_web.tests.test_training_modules_phase10_integration import LIB, _count
from y_web.tests.test_training_modules_phase12_integration import _publish

PLATFORM, SIMULATOR = PLATFORMS[0]
LESSON = {
    "title": "Lesson",
    "subtitle": "",
    "button_label": "",
    "blocks": [
        {"id": "b1", "type": "paragraph", "heading": "Intro", "text": "Read this."}
    ],
}
RES = {
    "title": "Video",
    "intro": "",
    "url": "https://www.example.org/v",
    "resource_kind": "video",
    "minimum_seconds": 0,
    "confirm_label": "",
    "button_label": "",
    "check": {"question": "", "options": [], "correct": ""},
}


def _run(admin, app, instances):
    module = _post(admin, f"{API}/modules", {"title": "Content module"}).get_json()[
        "module"
    ]["module_uid"]
    rev, keys = 1, []
    for kind, uid in instances:
        step = _post(
            admin,
            f"{API}/modules/{module}/versions/1/steps",
            {
                "type": "component",
                "component_ref": f"tm_native:{kind}",
                "title": kind,
                "revision": rev,
                "config": {"settings": {"instance_uid": uid, "instance_version": 1}},
            },
        )
        assert step.status_code == 201, step.get_json()
        rev = step.get_json()["revision"]
        keys.append(step.get_json()["step"]["step_key"])
    assert (
        _post(
            admin, f"{API}/modules/{module}/versions/1/publish", {"revision": rev}
        ).status_code
        == 200
    )
    exp = _experiment(app, PLATFORM, SIMULATOR)
    rid = _post(
        admin,
        f"{API}/runs",
        {"module_uid": module, "version_no": 1, "name": "Content run"},
    ).get_json()["run"]["id"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    account, _, email = _participant(app, exp)
    assert (
        _post(
            admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}
        ).status_code
        == 201
    )
    me = app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    token = re.search(
        r'name="csrf_token" value="([^"]+)"',
        me.get(f"/training/runs/{rid}").get_data(as_text=True),
    ).group(1)
    return rid, keys, me, token, email


@requires_plugin
def test_lesson_and_resource_run_through_the_real_core(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    # the domain must be allowed before the resource can be published
    created = _post(
        admin, f"{LIB}/instances", {"kind": "external_resource", "title": "Res"}
    ).get_json()["instance"]
    saved = admin.put(
        f"{LIB}/instances/{created['instance_uid']}/draft",
        json={"revision": 1, "definition": RES},
        headers={"X-CSRF-Token": "tok"},
    )
    refused = _post(
        admin,
        f"{LIB}/instances/{created['instance_uid']}/publish",
        {"revision": saved.get_json()["revision"]},
    )
    assert refused.status_code == 422
    assert (
        admin.patch(
            f"{API}/settings",
            json={"resource_domains": ["example.org"]},
            headers={"X-CSRF-Token": "tok"},
        ).status_code
        == 200
    )
    lesson = _publish(admin, "lesson", LESSON, "Lesson")
    resource = _publish(admin, "external_resource", RES, "Resource")
    rid, keys, me, token, email = _run(
        admin, app, [("lesson", lesson), ("external_resource", resource)]
    )
    url = f"/training/runs/{rid}/steps/{keys[0]}"
    assert me.post(url + "/start", data={"csrf_token": token}).status_code == 303
    page = me.get(url + "/page").get_data(as_text=True)
    assert 'aria-label="In this lesson"' in page and email not in page
    assert me.post(url + "/submit", data={"csrf_token": token}).status_code == 303
    url2 = f"/training/runs/{rid}/steps/{keys[1]}"
    assert me.post(url2 + "/start", data={"csrf_token": token}).status_code == 303
    page = me.get(url2 + "/page").get_data(as_text=True)
    assert 'rel="noopener noreferrer nofollow"' in page and "www.example.org" in page
    assert me.post(url2 + "/submit", data={"csrf_token": token}).status_code == 422
    assert (
        me.post(
            url2 + "/submit", data={"csrf_token": token, "confirmed": "1"}
        ).status_code
        == 303
    )
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='lesson_read'") == 1
    assert (
        _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='resource_confirmed'")
        == 1
    )
