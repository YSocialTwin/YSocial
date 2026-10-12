"""Phase 15 (G15) integration: Quick poll and written reflection with review against the real core. Skips without the plugin."""

import json

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    requires_plugin,
)
from y_web.tests.test_training_modules_phase10_integration import _count
from y_web.tests.test_training_modules_phase12_integration import _publish
from y_web.tests.test_training_modules_phase14_integration import _run

BASE = {
    "title": "",
    "intro": "",
    "closing_text": "",
    "button_label": "",
    "settings": {
        "one_page_at_a_time": False,
        "progress_bar": False,
        "autosave": False,
        "privacy_notice": False,
    },
    "scoring": {
        "enabled": False,
        "show": "items",
        "reveal_correct": False,
        "max_attempts": 1,
    },
}
POLL = dict(
    BASE,
    title="Mood",
    pages=[
        {
            "id": "p1",
            "title": "",
            "items": [
                {
                    "id": "m1",
                    "type": "likert",
                    "label": "How do you feel?",
                    "required": True,
                    "points": 5,
                }
            ],
        }
    ],
)
TEXT = (
    "I will always check the source of a post before sharing it with the people I know "
    * 2
)
REFLECTION = dict(
    BASE,
    title="What I learned",
    min_words=10,
    requires_review=True,
    pages=[
        {
            "id": "p1",
            "title": "",
            "items": [
                {
                    "id": "reflection",
                    "type": "long_text",
                    "label": "Write your reflection",
                    "required": True,
                    "counter": True,
                }
            ],
        }
    ],
)


@requires_plugin
def test_poll_then_reflection_with_review_through_the_real_core(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    poll = _publish(admin, "quick_poll", POLL, "Poll")
    reflection = _publish(admin, "reflection", REFLECTION, "Reflection")
    rid, keys, me, token, email = _run(
        admin, app, [("quick_poll", poll), ("reflection", reflection)]
    )
    one, two = (f"/training/runs/{rid}/steps/{k}" for k in keys)
    assert me.post(one + "/start", data={"csrf_token": token}).status_code == 303
    assert (
        me.post(one + "/submit", data={"csrf_token": token, "q_m1": "4"}).status_code
        == 303
    )
    assert me.post(two + "/start", data={"csrf_token": token}).status_code == 303
    assert me.get(two + "/page").status_code == 200
    assert (
        me.post(
            two + "/submit", data={"csrf_token": token, "q_reflection": "too short"}
        ).status_code
        == 422
    )
    assert (
        me.post(
            two + "/submit", data={"csrf_token": token, "q_reflection": TEXT}
        ).status_code
        == 303
    )
    assert (
        _count(app, "SELECT COUNT(*) FROM tm_step_progress WHERE status='completed'")
        == 1
    )  # only the poll
    queue = admin.get(f"{API}/runs/{rid}/reviews")
    assert queue.status_code == 200
    rows = queue.get_json()["submissions"]
    assert (
        len(rows) == 1
        and rows[0]["status"] == "pending"
        and email not in json.dumps(rows)
    )
    sid = rows[0]["response_id"]
    assert (
        _post(
            admin,
            f"{API}/runs/{rid}/reviews/{sid}",
            {"decision": "comment", "comment": "Nice, add an example"},
        ).status_code
        == 201
    )
    assert "Nice, add an example" in me.get(two + "/page").get_data(as_text=True)
    assert (
        _post(
            admin,
            f"{API}/runs/{rid}/reviews/{sid}",
            {"decision": "approved", "comment": ""},
        ).status_code
        == 201
    )
    assert (
        _count(app, "SELECT COUNT(*) FROM tm_step_progress WHERE status='completed'")
        == 2
    )
    assert _count(app, "SELECT COUNT(*) FROM tm_component_review") == 2
    assert me.get(f"{API}/runs/{rid}/reviews").status_code in (
        302,
        401,
        403,
    )  # a participant never
