"""Export for analysis with the real core: the real experiment database, the real identity map, consolidated ids."""
import csv
import io
import re
import zipfile

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (_experiment, _module, _participant, _post_as,  # noqa: F401
                                                                  _preexisting_platform_user)


def _rows(archive, name):
    return list(csv.DictReader(io.StringIO(archive.read(name).decode())))


@requires_plugin
def test_the_results_of_a_participant_are_exported_with_consolidated_ids(core_app):  # noqa: F811
    admin = _client_as(core_app, "admin")
    exp = _experiment(core_app, "microblogging", "Standard")
    uid = _module(admin, "microblogging", "Standard")
    rid = _post(admin, f"{API}/runs", {"module_uid": uid, "version_no": 1, "name": "Analysis run"}).get_json()["run"]["id"]
    keys = [b["step_key"] for b in admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"]]
    for key in keys:
        assert admin.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": exp}, headers={"X-CSRF-Token": "tok"}).status_code == 200
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    account, username, email = _participant(core_app, exp)
    platform_id = 700000 + account
    _preexisting_platform_user(core_app, exp, username, email, platform_id)
    assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}).status_code == 201
    me = core_app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    assert me.get("/training").status_code == 302
    me.get(f"/training/runs/{rid}")
    with me.session_transaction() as s:
        csrf = s["tm_csrf"]
    launch = me.post(f"/training/runs/{rid}/steps/{keys[0]}/start", data={"csrf_token": csrf})
    token = re.search(r'name="auth_token" value="([^"]+)"', launch.get_data(as_text=True)).group(1)
    assert me.post("/select_experiment", data={"experiment_id": exp, "auth_token": token}).status_code == 302
    _post_as(core_app, exp, platform_id, 2)

    listing = admin.get(f"{API}/runs/{rid}/analysis-participants").get_json()
    (code,) = [p["participant_code"] for p in listing["participants"]]
    for fmt, expected in (("csv", 200), ("sqlite", 200)):
        r = admin.post(f"{API}/runs/{rid}/analysis-export", json={"reason": "integration", "participants": [code], "format": fmt},
                       headers={"X-CSRF-Token": "tok"})
        assert r.status_code == expected, r.get_data(as_text=True)
        if fmt == "csv":
            archive = zipfile.ZipFile(io.BytesIO(r.data))
            posts = [a for a in _rows(archive, "sim_actions.csv") if a["participant_code"] == code and a["kind"] == "post"]
            assert len(posts) == 2 and {a["exp_id"] for a in posts} == {str(exp)}
            users = _rows(archive, "sim_users.csv")
            assert [u["sim_user_id"] for u in users if u["selected"] == "true"] == [code]
            blob = b"".join(archive.read(n) for n in archive.namelist()).decode()
            for forbidden in (username, email, str(platform_id)):
                assert forbidden not in blob, forbidden
        else:
            assert r.data[:15] == b"SQLite format 3"
    assert admin.post(f"{API}/runs/{rid}/analysis-export", json={"reason": "x", "participants": ["nobody"]},
                      headers={"X-CSRF-Token": "tok"}).status_code == 422
    student = _client_as(core_app, "user")
    assert student.post(f"{API}/runs/{rid}/analysis-export", json={"reason": "integration"}, headers={"X-CSRF-Token": "tok"}).status_code == 403
