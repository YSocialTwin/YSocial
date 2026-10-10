"""Only experiments with a Scenario Design scenario can be chosen for a slot (real core, real experiment databases)."""

from sqlalchemy import text

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _exp_session)
from y_web.tests.test_training_modules_management_integration import _module_with_slot

PLATFORM, SIMULATOR = PLATFORMS[0]


def _scenario(app, exp_id, status="draft", archived=False):
    """What Scenario Design stores in the experiment's own database (``sd_scenario``)."""
    with app.app_context():
        session, engine = _exp_session(app, exp_id)
        try:
            session.execute(text(
                "CREATE TABLE IF NOT EXISTS sd_scenario (id INTEGER PRIMARY KEY AUTOINCREMENT, exp_id INTEGER NOT NULL,"
                " name VARCHAR(255) NOT NULL, status VARCHAR(16) NOT NULL, archived_at DATETIME)"))
            session.execute(text("INSERT INTO sd_scenario (exp_id, name, status, archived_at) VALUES (:e, 'S', :s, :a)"),
                            {"e": exp_id, "s": "archived" if archived else status, "a": "2026-01-01" if archived else None})
            session.commit()
        finally:
            session.close()
            engine.dispose()


def _offered(admin, rid, key):
    return {e["exp_id"] for e in admin.get(f"{API}/runs/{rid}/experiments?step_key={key}").get_json()["experiments"]}


@requires_plugin
def test_only_experiments_with_a_scenario_can_be_chosen(core_app):  # noqa: F811
    core_app.config.pop("TM_EXPERIMENT_HAS_SCENARIO")     # the real check against the experiment databases
    admin = _client_as(core_app, "admin")
    plain, designed, archived = (_experiment(core_app, PLATFORM, SIMULATOR) for _ in range(3))
    _scenario(core_app, designed)
    _scenario(core_app, archived, archived=True)
    module = _module_with_slot(admin, "Needs a scenario")
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Run"}).get_json()["run"]["id"]
    key = admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"][0]["step_key"]
    offered = _offered(admin, rid, key)
    assert designed in offered and plain not in offered and archived not in offered
    refused = admin.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": plain}, headers={"X-CSRF-Token": "tok"})
    assert refused.status_code == 422 and refused.get_json()["error"] == "scenario_missing"
    ok = admin.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": designed}, headers={"X-CSRF-Token": "tok"})
    assert ok.status_code == 200 and ok.get_json()["binding"]["problems"] == []
    _scenario(core_app, plain)                                      # designed afterwards: it is offered from then on
    assert plain in _offered(admin, rid, key)
