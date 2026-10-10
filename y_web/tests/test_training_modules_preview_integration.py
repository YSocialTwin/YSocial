"""The author's module preview with the real core: its own user in the real experiment, no loss of the admin session."""

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import _experiment, _experiment_paths_under_tmp, _exp_session, _post_as  # noqa: F401
from y_web.tests.test_training_modules_phase10_integration import _count


def _preview_of(app, module):
    """``(preview run id, its only step key)``: the test database is shared with other tests, so look it up by module."""
    rid = _count(app, "SELECT r.id FROM tm_run r JOIN tm_module_version v ON v.id = r.version_id JOIN tm_module m ON m.id = v.module_id"
                      " WHERE m.module_uid = :u AND r.is_preview = 1", u=module)
    key = _count(app, "SELECT s.step_key FROM tm_step s JOIN tm_run r ON r.version_id = s.version_id WHERE r.id = :r", r=rid)
    return rid, key


def _draft(admin, slots=1):
    module = _post(admin, f"{API}/modules", {"title": "Rehearsal"}).get_json()["module"]["module_uid"]
    rev = 1
    for i in range(1, slots + 1):
        r = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
            "type": "scenario", "title": f"Simulation {i}", "revision": rev, "completion_policy": {"signal_mode": "declared", "criteria": []},
            "config": {"slot_key": f"s{i}", "hint_name": "Sim", "platform_type": "microblogging", "simulator_type": "Standard"}})
        assert r.status_code == 201, r.get_json()
        rev = r.get_json()["revision"]
    return module


def _in_experiment(app, exp_id, user_id):
    """``(posts of the user, rows of the user)`` in the real experiment database."""
    from y_web.src.models import Post, User_mgmt

    with app.app_context():
        session, engine = _exp_session(app, exp_id)
        try:
            return (session.query(Post).filter_by(user_id=user_id).count(), session.query(User_mgmt).filter_by(id=user_id).count())
        finally:
            session.close()
            engine.dispose()


@requires_plugin
def test_the_author_rehearses_a_draft_in_the_real_experiment_with_their_own_user(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    exp = _experiment(app, "microblogging", "Standard")
    other = _experiment(app, "microblogging", "Standard")
    module = _draft(admin)                                       # never published

    panel = admin.get(f"/admin/training/preview/{module}/1")
    assert panel.status_code == 200 and b"tm-preview-start" in panel.data
    rid, key = _preview_of(app, module)
    assert _post(admin, f"/admin/training/api/preview/{rid}/bindings/{key}", {"exp_id": exp}, method="put").status_code == 200

    before = _count(app, "SELECT COUNT(*) FROM user_experiment")   # nothing runs at the same time in this process
    start = admin.post(f"/training/runs/{rid}/steps/{key}/start", data={"csrf_token": "tok"})
    assert start.status_code == 303 and start.headers["Location"].endswith(f"/admin/join_experiment/{exp}")
    assert _count(app, "SELECT COUNT(*) FROM user_experiment") == before          # the core's assignments are not touched

    joined = admin.get(start.headers["Location"])                                 # the core's own page: the author's user in the experiment
    assert joined.status_code == 302 and f"/{exp}/feed/" in joined.headers["Location"]
    assert admin.get("/admin/training/modules").status_code == 200                # still the administration session
    assert _count(app, "SELECT COUNT(*) FROM tm_identity_map i JOIN tm_enrollment e ON e.id = i.enrollment_id WHERE e.run_id = :r", r=rid) == 1
    assert _count(app, "SELECT COUNT(*) FROM tm_launch l JOIN tm_enrollment e ON e.id = l.enrollment_id"
                       " WHERE e.run_id = :r AND l.consumed_at IS NOT NULL", r=rid) == 1

    # what the author does in the experiment is theirs to try, and it is gone when the rehearsal ends
    author = int(_count(app, "SELECT i.external_user_id FROM tm_identity_map i JOIN tm_enrollment e ON e.id = i.enrollment_id WHERE e.run_id = :r", r=rid))
    _post_as(app, exp, author, 2)
    assert _in_experiment(app, exp, author) == (2, 1)

    # the author can open any other experiment: the rehearsal never turns into the participant access guard
    page = admin.get(f"/admin/join_experiment/{other}")
    assert page.status_code == 302 and "/training" not in page.headers["Location"]

    # leaving the rehearsal: the session is the author's only again
    assert admin.get(f"/training/runs/{rid}/preview/exit").status_code == 303
    with admin.session_transaction() as s:
        assert "platform_account_id" not in s and "tm_preview_run" not in s
    assert _in_experiment(app, exp, author) == (0, 0)                             # posts and the user the preview created
    assert _count(app, "SELECT COUNT(*) FROM tm_preview_trace WHERE run_id = :r", r=rid) == 0


@requires_plugin
def test_the_preview_is_not_a_run_for_the_core_pages(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    module = _draft(admin)
    assert admin.get(f"/admin/training/preview/{module}/1").status_code == 200
    rid, _ = _preview_of(app, module)
    assert rid not in [r["id"] for r in admin.get(f"{API}/runs").get_json()["runs"]]
    assert admin.get(f"/admin/training/runs/{rid}").status_code == 404
    student = _client_as(core_app, "user")
    assert student.get(f"/admin/training/preview/{module}/1").status_code == 403
    assert _post(student, f"{API}/preview/{rid}/reset").status_code == 403
