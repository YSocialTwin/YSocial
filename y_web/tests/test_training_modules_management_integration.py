"""Management of modules and runs against the real core: activating the bound experiments, copies, students, deletion."""

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _participant)
from y_web.tests.test_training_modules_phase10_integration import _count

PLATFORM, SIMULATOR = PLATFORMS[0]


def _module_with_slot(admin, title):
    module = _post(admin, f"{API}/modules", {"title": title}).get_json()["module"]["module_uid"]
    step = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
        "type": "scenario", "title": "Scenario", "revision": 1,
        "config": {"slot_key": "s1", "hint_name": "Main", "platform_type": PLATFORM}})
    assert step.status_code == 201, step.get_json()
    assert _post(admin, f"{API}/modules/{module}/versions/1/publish", {"revision": step.get_json()["revision"]}).status_code == 200
    return module


def _status(app, exp_id):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        return db.session.get(Exps, exp_id).status


@requires_plugin
def test_the_run_switches_on_its_experiment_through_the_core(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    exp = _experiment(app, PLATFORM, SIMULATOR)
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        db.session.get(Exps, exp).status = 0
        db.session.commit()
    module = _module_with_slot(admin, "Needs an experiment")
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Run"}).get_json()["run"]["id"]
    step_key = admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"][0]["step_key"]
    bound = admin.put(f"{API}/runs/{rid}/bindings/{step_key}", json={"exp_id": exp}, headers={"X-CSRF-Token": "tok"})
    assert bound.status_code == 200 and bound.get_json()["binding"]["problems"] == ["experiment_not_activated"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 409
    page = admin.get(f"/admin/training/runs/{rid}").get_data(as_text=True)
    assert f'data-activate="{exp}"' in page
    r = _post(admin, f"{API}/runs/{rid}/experiments/{exp}/activate")
    assert r.status_code == 200, r.get_json()
    assert _status(app, exp) == 1
    assert _post(admin, f"{API}/runs/{rid}/experiments/{exp}/activate").status_code == 200     # already on: it stays on
    assert _status(app, exp) == 1
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200


@requires_plugin
def test_copies_students_and_deletion_through_the_real_core(core_app):  # noqa: F811
    app, admin = core_app, _client_as(core_app, "admin")
    exp = _experiment(app, PLATFORM, SIMULATOR)
    account, username, _ = _participant(app, exp)
    module = _module_with_slot(admin, "Source")
    copy = _post(admin, f"{API}/modules/{module}/duplicate").get_json()
    assert copy["published"] is True
    run = _post(admin, f"{API}/modules/{copy['module']['module_uid']}/enroll", {"csv": username})
    assert run.status_code == 201 and run.get_json()["created_run"] is True and run.get_json()["summary"]["enrolled"] == 1
    rid = run.get_json()["run"]["id"]
    assert _count(app, f"SELECT COUNT(*) FROM tm_enrollment WHERE run_id={rid}") == 1
    assert _post(admin, f"{API}/modules/{module}/archive").status_code == 200
    assert _post(admin, f"{API}/modules/{module}/enroll", {"csv": username}).get_json()["error"] == "module_archived"
    assert admin.delete(f"{API}/runs/{rid}", headers={"X-CSRF-Token": "tok"}).status_code == 200
    assert _count(app, f"SELECT COUNT(*) FROM tm_enrollment WHERE run_id={rid}") == 0
    assert _count(app, f"SELECT COUNT(*) FROM tm_run WHERE id={rid}") == 0
    assert admin.delete(f"{API}/modules/{copy['module']['module_uid']}", headers={"X-CSRF-Token": "tok"}).status_code == 200
    assert _count(app, f"SELECT COUNT(*) FROM tm_module WHERE module_uid='{copy['module']['module_uid']}'") == 0
    assert _count(app, f"SELECT COUNT(*) FROM tm_module WHERE module_uid='{module}'") == 1   # the source is untouched
