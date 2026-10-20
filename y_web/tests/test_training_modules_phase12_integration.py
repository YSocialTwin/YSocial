"""Phase 12 (G12) integration: questionnaire logic and portable files against the real core. Skips without the plugin."""

import json
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

PLATFORM, SIMULATOR = PLATFORMS[0]
LOGIC = {
    "title": "Branching check",
    "intro": "",
    "closing_text": "",
    "button_label": "",
    "settings": {
        "one_page_at_a_time": False,
        "progress_bar": True,
        "autosave": True,
        "privacy_notice": False,
    },
    "pages": [
        {
            "id": "p1",
            "title": "",
            "items": [
                {
                    "id": "use",
                    "type": "yes_no",
                    "label": "Do you use it?",
                    "required": True,
                },
                {
                    "id": "tool",
                    "type": "single_choice",
                    "label": "Which one?",
                    "required": True,
                    "random_order": True,
                    "options": [
                        {"id": "a", "label": "Alpha"},
                        {"id": "b", "label": "Beta"},
                        {"id": "c", "label": "Gamma"},
                    ],
                    "visible_if": {"q": "use", "op": "eq", "value": "yes"},
                },
            ],
        }
    ],
}


def _publish(admin, kind, definition, title):
    created = _post(
        admin, f"{LIB}/instances", {"kind": kind, "title": title}
    ).get_json()["instance"]
    uid = created["instance_uid"]
    saved = admin.put(
        f"{LIB}/instances/{uid}/draft",
        json={"revision": 1, "definition": definition},
        headers={"X-CSRF-Token": "tok"},
    )
    assert saved.status_code == 200 and saved.get_json()["problems"] == []
    assert (
        _post(admin, f"{LIB}/instances/{uid}/publish", {"revision": 2}).status_code
        == 200
    )
    return uid


@requires_plugin
def test_hidden_questions_are_not_required_and_their_answers_are_dropped(
    core_app,
):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    uid = _publish(admin, "questionnaire", LOGIC, "Branching")
    module = _post(admin, f"{API}/modules", {"title": "Branching module"}).get_json()[
        "module"
    ]["module_uid"]
    step = _post(
        admin,
        f"{API}/modules/{module}/versions/1/steps",
        {
            "type": "component",
            "component_ref": "tm_native:questionnaire",
            "title": "Branch",
            "revision": 1,
            "config": {"settings": {"instance_uid": uid, "instance_version": 1}},
        },
    )
    assert step.status_code == 201, step.get_json()
    key = step.get_json()["step"]["step_key"]
    assert (
        _post(
            admin,
            f"{API}/modules/{module}/versions/1/publish",
            {"revision": step.get_json()["revision"]},
        ).status_code
        == 200
    )
    exp = _experiment(app, PLATFORM, SIMULATOR)
    rid = _post(
        admin,
        f"{API}/runs",
        {"module_uid": module, "version_no": 1, "name": "Branch run"},
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
    assert (
        me.post(
            f"/training/runs/{rid}/steps/{key}/start", data={"csrf_token": token}
        ).status_code
        == 303
    )
    url = f"/training/runs/{rid}/steps/{key}"
    page = me.get(url + "/page").get_data(as_text=True)
    assert (
        "data-cond" in page and "Alpha" in page and email not in page
    )  # the rule travels with the page
    # "yes" makes the follow-up mandatory
    assert (
        me.post(url + "/submit", data={"csrf_token": token, "q_use": "yes"}).status_code
        == 422
    )
    # "no" hides it: not required, and a smuggled answer is discarded
    assert (
        me.post(
            url + "/submit", data={"csrf_token": token, "q_use": "no", "q_tool": "a"}
        ).status_code
        == 303
    )
    with app.app_context():
        from sqlalchemy import text

        from y_web import db

        with db.engines["db_admin"].connect() as c:
            raw = c.execute(
                text(
                    "SELECT answers_json FROM tm_component_response WHERE status='submitted'"
                )
            ).scalar()
    assert json.loads(raw) == {"use": "no"}
    assert (
        _count(
            app,
            "SELECT COUNT(*) FROM tm_event WHERE type='form_submitted' AND source='native'",
        )
        == 1
    )


@requires_plugin
def test_component_and_module_files_round_trip_through_the_real_core(
    core_app,
):  # noqa: F811
    admin = _client_as(core_app, "admin")
    uid = _publish(admin, "questionnaire", LOGIC, "Portable")
    exported = admin.get(f"{LIB}/instances/{uid}/export")
    assert exported.status_code == 200
    doc = json.loads(exported.get_data(as_text=True))
    assert doc["schema"] == "ysocial.training_component" and "owner_id" not in doc
    before = _count(core_app, "SELECT COUNT(*) FROM tm_component_instance")
    imported = admin.post(
        f"{LIB}/import",
        data=json.dumps(doc),
        content_type="application/json",
        headers={"X-CSRF-Token": "tok"},
    )
    assert (
        imported.status_code == 201
        and imported.get_json()["instance"]["versions"][0]["status"] == "draft"
    )
    assert _count(core_app, "SELECT COUNT(*) FROM tm_component_instance") == before + 1
    doc["definition"]["title"] = "Tampered"
    bad = admin.post(
        f"{LIB}/import",
        data=json.dumps(doc),
        content_type="application/json",
        headers={"X-CSRF-Token": "tok"},
    )
    assert bad.status_code == 422 and bad.get_json()["error"] == "hash_mismatch"
    assert _count(core_app, "SELECT COUNT(*) FROM tm_component_instance") == before + 1

    module = _post(admin, f"{API}/modules", {"title": "Portable module"}).get_json()[
        "module"
    ]["module_uid"]
    step = _post(
        admin,
        f"{API}/modules/{module}/versions/1/steps",
        {
            "type": "component",
            "component_ref": "tm_native:questionnaire",
            "title": "Q",
            "revision": 1,
            "config": {"settings": {"instance_uid": uid, "instance_version": 1}},
        },
    )
    assert (
        _post(
            admin,
            f"{API}/modules/{module}/versions/1/publish",
            {"revision": step.get_json()["revision"]},
        ).status_code
        == 200
    )
    mdoc = json.loads(
        admin.get(f"{API}/modules/{module}/versions/1/export").get_data(as_text=True)
    )
    assert mdoc["schema_version"] == "1.1.0" and [
        c["instance_uid"] for c in mdoc["components"]
    ] == [uid]
    copy = admin.post(
        f"{API}/import?as_copy=1",
        data=json.dumps(mdoc),
        content_type="application/json",
        headers={"X-CSRF-Token": "tok"},
    )
    assert copy.status_code == 201, copy.get_json()
    assert [c["action"] for c in copy.get_json()["components"]] == ["reused"]
    assert copy.get_json()["unresolved_instances"] == []
