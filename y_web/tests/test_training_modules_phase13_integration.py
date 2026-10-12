"""Phase 13 (G13) integration: scored questionnaire, retry and answer export against the real core. Skips without the plugin."""

import csv
import io
import json
import re
import zipfile

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
QUIZ = {
    "title": "Quiz",
    "intro": "",
    "closing_text": "",
    "button_label": "",
    "settings": {
        "one_page_at_a_time": False,
        "progress_bar": True,
        "autosave": True,
        "privacy_notice": False,
    },
    "scoring": {
        "enabled": True,
        "pass_percent": 100,
        "max_attempts": 2,
        "show": "items",
        "reveal_correct": True,
    },
    "pages": [
        {
            "id": "p1",
            "title": "",
            "items": [
                {
                    "id": "q1",
                    "type": "single_choice",
                    "label": "Pick B",
                    "required": True,
                    "correct": "b",
                    "feedback": "Because B.",
                    "options": [
                        {"id": "a", "label": "Alpha"},
                        {"id": "b", "label": "Beta"},
                    ],
                },
                {
                    "id": "q2",
                    "type": "ordering",
                    "label": "Order",
                    "required": True,
                    "options": [
                        {"id": "o1", "label": "One"},
                        {"id": "o2", "label": "Two"},
                    ],
                },
            ],
        }
    ],
}


@requires_plugin
def test_a_scored_questionnaire_is_retried_and_exported_through_the_real_core(
    core_app,
):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    uid = _publish(admin, "questionnaire", QUIZ, "Quiz")
    module = _post(admin, f"{API}/modules", {"title": "Quiz module"}).get_json()[
        "module"
    ]["module_uid"]
    step = _post(
        admin,
        f"{API}/modules/{module}/versions/1/steps",
        {
            "type": "component",
            "component_ref": "tm_native:questionnaire",
            "title": "Quiz",
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
        {"module_uid": module, "version_no": 1, "name": "Quiz run"},
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
        "Alpha" in page
        and "Because B." not in page
        and "correct" not in page.lower().replace("incorrect", "")
    )
    assert (
        me.post(
            url + "/submit",
            data={"csrf_token": token, "q_q1": "a", "q_q2__o1": "2", "q_q2__o2": "1"},
        ).status_code
        == 303
    )
    after = me.get(url + "/page").get_data(as_text=True)
    assert (
        "Not passed" in after
        and "Try again" in after
        and "Because B." in after
        and email not in after
    )
    assert (
        _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='completion_event'") == 0
    )
    assert me.post(url + "/retry", data={"csrf_token": token}).status_code == 303
    assert (
        me.post(
            url + "/submit",
            data={"csrf_token": token, "q_q1": "b", "q_q2__o1": "1", "q_q2__o2": "2"},
        ).status_code
        == 303
    )
    assert (
        _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='completion_event'") == 1
    )
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='form_retry'") == 1

    exported = _post(
        admin, f"{API}/runs/{rid}/exports", {"reason": "integration check"}
    )
    assert exported.status_code == 200
    files = {
        n: zipfile.ZipFile(io.BytesIO(exported.data)).read(n)
        for n in zipfile.ZipFile(io.BytesIO(exported.data)).namelist()
    }
    rows = list(csv.DictReader(io.StringIO(files["form_01_quiz.csv"].decode())))
    assert [(r["attempt_no"], r["status"], r["passed"]) for r in rows] == [
        ("1", "submitted", "false"),
        ("2", "submitted", "true"),
    ]
    assert [r["q_q1"] for r in rows] == ["a", "b"] and rows[1]["percent"] in (
        "100",
        "100.0",
    )
    book = files["form_01_quiz_codebook.csv"].decode()
    assert "Because B." not in book and "correct" not in book.split("\n", 1)[1]
    assert email.encode() not in b"".join(files.values())
    pooled = _post(
        admin, f"{LIB}/instances/{uid}/responses-export", {"reason": "pooled"}
    )
    assert (
        pooled.status_code == 200
        and json.loads(zipfile.ZipFile(io.BytesIO(pooled.data)).read("manifest.json"))[
            "kind"
        ]
        == "form_instance"
    )
