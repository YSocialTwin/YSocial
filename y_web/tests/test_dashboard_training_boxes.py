"""Admin dashboard: Simulations / Training separation and the Training boxes."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates/admin/dashboard.html").read_text(encoding="utf-8")


def test_sections_are_separated():
    assert 'id="section-simulations"' in TEMPLATE
    assert 'id="section-training"' in TEMPLATE
    assert TEMPLATE.index("section-simulations") < TEMPLATE.index(
        "box-running-experiments"
    )
    assert TEMPLATE.index("end Simulations section") < TEMPLATE.index(
        "section-training"
    )


def test_training_section_only_when_plugin_active():
    start = TEMPLATE.index("{% if training_overview %}")
    assert start < TEMPLATE.index('id="section-training"')
    assert "box-active-modules" in TEMPLATE and "box-inactive-modules" in TEMPLATE


def test_overview_is_none_when_plugin_missing(monkeypatch):
    from y_web.src.external_runtime import backend_plugins as bp

    monkeypatch.setattr(bp, "plugin_enabled", lambda key: False)
    assert bp.training_dashboard_overview(object()) is None
    monkeypatch.setattr(bp, "plugin_enabled", lambda key: True)
    monkeypatch.setattr(bp, "validate_backend_suite", lambda key: {"valid": False})
    assert bp.training_dashboard_overview(object()) is None


def test_italian_labels():
    import babel.messages.pofile as pofile

    cat = pofile.read_po(open(ROOT / "translations/it/LC_MESSAGES/messages.po", "rb"))
    for msgid in (
        "Active modules",
        "Inactive modules",
        "Activate",
        "Deactivate",
        "Simulations",
    ):
        assert cat.get(msgid).string, msgid


def test_experiments_of_a_module_sit_under_it_and_not_in_the_status_boxes():
    assert "module.experiments" in TEMPLATE and "dash-module-exps" in TEMPLATE
    from y_web.routes.admin import dashboard as dash

    class Exp:
        def __init__(self, idexp, name, exp_status=None, running=0):
            self.idexp, self.exp_name, self.exp_status, self.running = (
                idexp,
                name,
                exp_status,
                running,
            )

    overview = {
        "active": [{"uid": "a", "experiment_ids": [1, 2, 9]}],
        "inactive": [{"uid": "b", "experiment_ids": [2]}],
        "experiment_ids": [1, 2, 9],
    }
    dash._attach_training_experiments(
        overview, [Exp(1, "One", "active"), Exp(2, "Two", "completed"), Exp(3, "Three")]
    )
    assert overview["active"][0]["experiments"] == [
        {"id": 1, "name": "One", "status": "running"},
        {"id": 2, "name": "Two", "status": "completed"},
    ]  # 9 is not visible to this person: not listed
    assert [e["id"] for e in overview["inactive"][0]["experiments"]] == [2]
    assert dash._dashboard_hidden_ids(None, overview) >= {1, 2, 9}
    assert dash._dashboard_hidden_ids(None, {}) == set(
        dash._world_simulation_member_ids()
    )
