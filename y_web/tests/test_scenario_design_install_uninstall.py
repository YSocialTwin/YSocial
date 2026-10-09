"""Integration test: the "zero impact when not installed" guarantee for the
Scenario Design backend settings suite, end-to-end.

Mirrors the manual install/uninstall round-trip performed during Fase 1
(physically moving external/ScenarioDesign aside and re-running the full
suite: see ScenarioDesign/docs/decisions.md, Fase 1 §F1.7) in automated,
repeatable form -- by pointing the registry spec's path at an empty
directory instead of physically touching the real checkout, so this test
is safe to run regardless of whether ScenarioDesign happens to be
installed in a given environment.

Piano di implementazione, Fase 1, commit #7
("test(integration): installazione/disinstallazione end-to-end del
plugin ... verifica non-regressione run_tests.py con/senza plugin").
"""

from y_web.src.external_runtime import backend_plugins, registry


def test_scenario_design_absent_degrades_safely_everywhere(tmp_path, monkeypatch, app):
    """With the suite "uninstalled" (path pointing nowhere), every layer
    must degrade safely: no exception anywhere, blueprint simply absent,
    sidebar link simply hidden -- never a crash, never a half-registered
    state."""
    empty_dir = tmp_path / "not_installed"
    real_spec = registry.runtime_spec("scenario_design")
    uninstalled_spec = registry.ExternalRuntimeSpec(
        **{**real_spec.__dict__, "path": empty_dir},
    )
    monkeypatch.setitem(
        registry.SUPPORTED_EXTERNAL_REPOS, "scenario_design", uninstalled_spec
    )

    validation = backend_plugins.validate_backend_suite("scenario_design")
    assert validation["installed"] is False
    assert validation["valid"] is False

    availability = backend_plugins.backend_suite_availability()
    assert availability.get("scenario_design") is False

    report = backend_plugins.register_backend_plugin_suites(app)
    assert report["suites"]["scenario_design"]["installed"] is False
    assert "scenario_design" not in app.blueprints

    client = app.test_client()
    resp = client.get("/admin/scenario_design/")
    assert resp.status_code == 404  # route simply doesn't exist -- not a 500


def test_create_app_boots_cleanly_with_suite_absent(tmp_path, monkeypatch):
    """The full create_app() boot sequence (which is what actually runs in
    production) must not raise and must hide the sidebar link, when the
    suite is not installed."""
    empty_dir = tmp_path / "not_installed"
    real_spec = registry.runtime_spec("scenario_design")
    uninstalled_spec = registry.ExternalRuntimeSpec(
        **{**real_spec.__dict__, "path": empty_dir},
    )
    monkeypatch.setitem(
        registry.SUPPORTED_EXTERNAL_REPOS, "scenario_design", uninstalled_spec
    )

    from y_web import create_app

    boot_app = create_app(db_type="sqlite")  # must not raise
    injector = next(
        fn
        for fn in boot_app.template_context_processors[None]
        if fn.__name__ == "inject_backend_plugin_visibility"
    )
    with boot_app.app_context(), boot_app.test_request_context("/"):
        result = injector()
        assert result["backend_suites_available"].get("scenario_design") is False
        assert result["scenario_design_sidebar_url"] is None
