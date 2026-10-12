"""Phase 7 (G7) integration: component launch, signed callback and pull against the real core.

The component is played by a small fake behind ``app.config["TM_HTTP"]``; the
signatures are computed here with plain ``hmac``/``hashlib`` so the test also
checks the contract as documented, not the plugin's own helper. Skips without
the plugin.
"""

import base64
import hashlib
import hmac
import json
import re
import time
import urllib.parse
import uuid

from werkzeug.security import generate_password_hash

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    requires_plugin,
)

SECRET = "integration-secret-" + uuid.uuid4().hex
DESCRIPTORS = [
    {
        "type_key": "quiz",
        "component_ref": "survey_plugin:quiz",
        "repo_key": "survey_plugin",
        "label": "Quiz",
        "icon": "x",
        "category": "Quiz",
        "contract_version": "1",
        "config_schema": {"type": "object", "properties": {}},
        "launch": {"endpoint": "/q/launch"},
        "health": {"endpoint": "/q/health"},
        "signals": {"declared": True, "verified": True, "advance_button": True},
    },
]


def _sign(ts, body: bytes) -> str:
    return (
        "sha256="
        + hmac.new(
            SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256
        ).hexdigest()
    )


class Fake:
    """The component: health, and signed pull answers for launches it was told are finished."""

    def __init__(self):
        self.offline = False
        self.finished = {}

    def __call__(self, method, url, headers, timeout):
        if self.offline:
            raise ConnectionError("down")
        path = urllib.parse.urlsplit(url).path
        if path == "/q/health":
            return 200, b"{}", {}
        match = re.match(r"^/tm/v1/launches/(.+)$", path)
        if match and match.group(1) in self.finished:
            body = json.dumps(
                {
                    "launch_id": match.group(1),
                    "status": "completed",
                    "external_user_id": "Q-int-1",
                    "completed_at": "2026-10-09T10:00:00Z",
                }
            ).encode()
            ts = str(int(time.time()))
            return 200, body, {"X-TM-Timestamp": ts, "X-TM-Signature": _sign(ts, body)}
        return 404, b"{}", {}


def _participant(app):
    from y_web import db
    from y_web.src.models import Admin_users

    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        row = Admin_users(
            username=f"s{tag}",
            email=f"s{tag}@example.test",
            password=generate_password_hash("x"),
            last_seen="2026-01-01",
            role="user",
        )
        db.session.add(row)
        db.session.commit()
        return row.id, row.username, row.email


def _claims(token):
    payload, _ = token.split(".")
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _callback(
    client, launch_id, *, nonce, signature=None, ts=None, component="survey_plugin"
):
    body = json.dumps(
        {
            "launch_id": launch_id,
            "external_user_id": "Q-int-1",
            "status": "completed",
            "nonce": nonce,
            "completed_at": "2026-10-09T10:00:00Z",
        }
    ).encode()
    ts = str(int(time.time()) if ts is None else ts)
    return client.post(
        "/training/api/v1/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-TM-Component": component,
            "X-TM-Timestamp": ts,
            "X-TM-Signature": signature or _sign(ts, body),
        },
    )


@requires_plugin
def test_component_path_through_the_real_core(core_app):
    fake = Fake()
    core_app.config.update(
        TM_COMPONENT_CATALOG=DESCRIPTORS,
        TM_HEALTH_CHECKER=None,
        TM_HTTP=fake,
        TM_COMPONENT_SECRETS={"survey": SECRET},
    )
    admin = _client_as(core_app, "admin")
    assert (
        _post(
            admin,
            f"{API}/registry",
            {
                "component_key": "survey_plugin",
                "display_name": "Survey",
                "base_url": "http://survey.test",
                "secret_ref": "survey",
            },
        ).status_code
        == 201
    )

    uid = _post(admin, f"{API}/modules", {"title": "G7 module"}).get_json()["module"][
        "module_uid"
    ]
    rev = 1
    for i in (1, 2):
        r = _post(
            admin,
            f"{API}/modules/{uid}/versions/1/steps",
            {
                "revision": rev,
                "type": "component",
                "component_ref": "survey_plugin:quiz",
                "title": f"Quiz {i}",
                "config": {
                    "component_ref": "survey_plugin:quiz",
                    "contract_version": "1",
                    "settings": {},
                },
                "completion_policy": {"signal_mode": "verified", "criteria": []},
            },
        )
        assert r.status_code == 201, r.get_json()
        rev = r.get_json()["revision"]
    assert (
        _post(
            admin, f"{API}/modules/{uid}/versions/1/publish", {"revision": rev}
        ).status_code
        == 200
    )
    rid = _post(
        admin, f"{API}/runs", {"module_uid": uid, "version_no": 1, "name": "G7 run"}
    ).get_json()["run"]["id"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    account, username, email = _participant(core_app)
    assert (
        _post(
            admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}
        ).status_code
        == 201
    )

    me = core_app.test_client()
    assert (
        me.post("/login", data={"email": email, "password": "x"})
        .headers["Location"]
        .endswith("/training")
    )
    me.get(f"/training/runs/{rid}")
    with me.session_transaction() as s:
        csrf = s["tm_csrf"]
    keys = re.findall(
        r'data-step="([0-9a-f-]{36})"',
        me.get(f"/training/runs/{rid}").get_data(as_text=True),
    )
    assert len(keys) == 2

    # component down: refused, nothing consumed
    fake.offline = True
    r = me.post(
        f"/training/runs/{rid}/steps/{keys[0]}/start", data={"csrf_token": csrf}
    )
    assert r.status_code == 503 and 'data-code="component_unavailable"' in r.get_data(
        as_text=True
    )
    fake.offline = False

    r = me.post(
        f"/training/runs/{rid}/steps/{keys[0]}/start", data={"csrf_token": csrf}
    )
    assert r.status_code == 303
    url = urllib.parse.urlsplit(r.headers["Location"])
    assert url.netloc == "survey.test" and url.path == "/q/launch"
    token = urllib.parse.parse_qs(url.query)["launch_token"][0]
    claims = _claims(token)
    assert (
        username not in json.dumps(claims)
        and email not in json.dumps(claims)
        and "account" not in json.dumps(claims)
    )
    payload = token.split(".")[0]
    assert hmac.compare_digest(
        base64.urlsafe_b64decode(
            token.split(".")[1] + "=" * (-len(token.split(".")[1]) % 4)
        ),
        hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest(),
    )
    launch_id = claims["launch_id"]

    anonymous = (
        core_app.test_client()
    )  # callbacks carry no session: the signature is the only credential
    assert (
        _callback(
            anonymous, launch_id, nonce="nonce-int-0001", signature="sha256=" + "0" * 64
        ).status_code
        == 401
    )
    assert (
        _callback(
            anonymous, launch_id, nonce="nonce-int-0002", ts=int(time.time()) - 3600
        ).status_code
        == 401
    )
    page = me.get(f"/training/runs/{rid}").get_data(as_text=True)
    assert page.count('data-status="completed"') == 0
    ok = _callback(anonymous, launch_id, nonce="nonce-int-0003")
    assert ok.status_code == 200 and ok.get_json() == {"status": "accepted"}
    replay = _callback(anonymous, launch_id, nonce="nonce-int-0003")
    assert replay.status_code == 200 and replay.get_json() == {"status": "duplicate"}
    assert (
        _callback(anonymous, launch_id, nonce="nonce-int-0004").status_code == 409
    )  # launch already consumed
    page = me.get(f"/training/runs/{rid}").get_data(as_text=True)
    assert page.count('data-status="completed"') == 1

    # second step: the callback is lost, the signed pull recovers it
    r = me.post(
        f"/training/runs/{rid}/steps/{keys[1]}/start", data={"csrf_token": csrf}
    )
    assert r.status_code == 303
    second = _claims(
        urllib.parse.parse_qs(urllib.parse.urlsplit(r.headers["Location"]).query)[
            "launch_token"
        ][0]
    )["launch_id"]
    fake.finished[second] = True
    page = me.get(f"/training/runs/{rid}").get_data(as_text=True)
    assert (
        page.count('data-status="completed"') == 2
        and "completed all the required steps" in page
    )

    # the identity map learnt the component's own id; staff see pseudonyms only
    from sqlalchemy import text

    from y_web import db

    with core_app.app_context():
        with db.engines["db_admin"].connect() as c:
            assert c.execute(
                text(
                    "SELECT system_kind, external_user_id FROM tm_identity_map WHERE status='active'"
                )
            ).all() == [("component", "Q-int-1")]
    body = admin.get(f"{API}/runs/{rid}/progress").get_data(as_text=True)
    assert (
        username not in body
        and email not in body
        and "Q-int-1" not in body
        and SECRET not in body
    )
