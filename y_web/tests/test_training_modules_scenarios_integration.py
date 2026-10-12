"""Only experiments with a published Scenario Design scenario can be chosen for a slot (real core, real experiment databases)."""

from sqlalchemy import text

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_management_integration import _module_with_slot
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    requires_plugin,
)
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS,
    _exp_session,
    _experiment,
    _experiment_paths_under_tmp,
)

PLATFORM, SIMULATOR = PLATFORMS[0]


def _scenario(app, exp_id, status="published", archived=False, master=None, name="S"):
    """What Scenario Design stores in an experiment's own database: the scenario (``exp_id`` = the master it was
    designed on) and, once published, the publication. A published release is a copy of the master's database.
    """
    with app.app_context():
        session, engine = _exp_session(app, exp_id)
        try:
            session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS sd_scenario (id INTEGER PRIMARY KEY AUTOINCREMENT, exp_id INTEGER NOT NULL,"
                    " name VARCHAR(255) NOT NULL, status VARCHAR(16) NOT NULL, archived_at DATETIME)"
                )
            )
            session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS sd_publication (id INTEGER PRIMARY KEY AUTOINCREMENT, scenario_id INTEGER NOT NULL,"
                    " exp_id INTEGER NOT NULL, status VARCHAR(16) NOT NULL)"
                )
            )
            sid = session.execute(
                text(
                    "INSERT INTO sd_scenario (exp_id, name, status, archived_at) VALUES (:e, :n, :s, :a)"
                ),
                {
                    "e": master or exp_id,
                    "n": name,
                    "s": "archived" if archived else status,
                    "a": "2026-01-01" if archived else None,
                },
            ).lastrowid
            if status == "published":
                session.execute(
                    text(
                        "INSERT INTO sd_publication (scenario_id, exp_id, status) VALUES (:i, :e, 'succeeded')"
                    ),
                    {"i": sid, "e": master or exp_id},
                )
            session.commit()
        finally:
            session.close()
            engine.dispose()


def _offered(admin, rid, key):
    return {
        e["exp_id"]
        for e in admin.get(f"{API}/runs/{rid}/experiments?step_key={key}").get_json()[
            "experiments"
        ]
    }


@requires_plugin
def test_only_releases_of_published_scenarios_can_be_chosen(core_app):  # noqa: F811
    core_app.config.pop(
        "TM_EXPERIMENT_SCENARIO"
    )  # the real check against the experiment databases
    admin = _client_as(core_app, "admin")
    plain, master, archived, draft, release = (
        _experiment(core_app, PLATFORM, SIMULATOR) for _ in range(5)
    )
    _scenario(
        core_app, master
    )  # the master the scenario was designed on and published from
    _scenario(core_app, archived, archived=True)
    _scenario(core_app, draft, status="draft")  # designed but not published
    _scenario(
        core_app, release, master=master, name="Misinformation drill"
    )  # the copy made by publishing carries the row
    module = _module_with_slot(admin, "Needs a published scenario")
    rid = _post(
        admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Run"}
    ).get_json()["run"]["id"]
    key = admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"][0]["step_key"]
    offered = _offered(admin, rid, key)
    assert release in offered and not (
        {plain, master, archived, draft} & offered
    )  # the master is never offered
    refused = admin.put(
        f"{API}/runs/{rid}/bindings/{key}",
        json={"exp_id": master},
        headers={"X-CSRF-Token": "tok"},
    )
    assert (
        refused.status_code == 422 and refused.get_json()["error"] == "scenario_missing"
    )
    ok = admin.put(
        f"{API}/runs/{rid}/bindings/{key}",
        json={"exp_id": release},
        headers={"X-CSRF-Token": "tok"},
    )
    binding = ok.get_json()["binding"]
    assert (
        ok.status_code == 200
        and binding["problems"] == []
        and binding["scenario"]["name"] == "Misinformation drill"
    )
    assert binding["snapshot"]["scenario_id"] == binding["scenario"]["id"]
    listed = {
        e["exp_id"]: e
        for e in admin.get(f"{API}/runs/{rid}/experiments?step_key={key}").get_json()[
            "experiments"
        ]
    }
    assert listed[release]["scenario"]["name"] == "Misinformation drill"
    _scenario(
        core_app, draft, master=plain
    )  # a draft is published later: its release is offered
    assert draft in _offered(admin, rid, key)
