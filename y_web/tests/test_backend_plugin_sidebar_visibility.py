"""
Tests for the sidebar-visibility context processor
(inject_backend_plugin_visibility, in y_web/__init__.py) that gates the
"Scenario Design" admin sidebar entry on the suite's installed+valid
status.

Split out from test_backend_plugins_registry.py so each atomic commit in
the Scenario Design Fase 1 sequence carries exactly the tests for what it
changes (piano di implementazione, Fase 1, commit #3: feat(core-sidebar)).
"""


# ---------------------------------------------------------------------------
# Sidebar visibility: "zero impact when invalid" via the real create_app()
# context processor (mirrors test_memory_enabled_detection.py's pattern of
# pulling a named context processor out of a real create_app() instance).
# ---------------------------------------------------------------------------
def test_inject_backend_plugin_visibility_exposes_url_when_valid():
    from y_web import create_app

    app = create_app(db_type="sqlite")
    injector = next(
        fn
        for fn in app.template_context_processors[None]
        if fn.__name__ == "inject_backend_plugin_visibility"
    )

    with app.app_context(), app.test_request_context("/"):
        result = injector()
        assert result["backend_suites_available"].get("scenario_design") is True
        assert result["scenario_design_sidebar_url"] == "/admin/scenario_design/"


def test_inject_backend_plugin_visibility_hides_link_if_manifest_valid_but_blueprint_missing(monkeypatch):
    """Regression guard for the exact edge case this mechanism was written to
    avoid: validate_backend_suite() says "valid" (manifest-only check) but
    the blueprint's endpoint doesn't actually resolve on *this* app (e.g. an
    import error at startup caught upstream, so the blueprint was never
    registered even though the manifest is fine). url_for() must not raise
    out of the context processor and must instead degrade to hiding the
    sidebar link.

    werkzeug.routing.BuildError is forced here (rather than genuinely
    failing blueprint registration) because it is the one observable
    surface this guarantee depends on: whatever the upstream cause,
    url_for() raising BuildError for this endpoint is exactly the failure
    mode the try/except in inject_backend_plugin_visibility must absorb.
    """
    from y_web import create_app
    import flask

    app = create_app(db_type="sqlite")

    monkeypatch.setattr(
        "y_web.src.external_runtime.backend_plugins.backend_suite_availability",
        lambda: {"scenario_design": True},
    )

    real_url_for = flask.url_for

    def _fake_url_for(endpoint, *args, **kwargs):
        if endpoint == "scenario_design.index":
            from werkzeug.routing import BuildError

            raise BuildError(endpoint, kwargs, "GET")
        return real_url_for(endpoint, *args, **kwargs)

    monkeypatch.setattr(flask, "url_for", _fake_url_for)

    injector = next(
        fn
        for fn in app.template_context_processors[None]
        if fn.__name__ == "inject_backend_plugin_visibility"
    )

    with app.app_context(), app.test_request_context("/"):
        result = injector()
        assert result["backend_suites_available"].get("scenario_design") is True
        # The unsafe path would have raised werkzeug.routing.BuildError here;
        # the safe path degrades to None instead of crashing page rendering.
        assert result["scenario_design_sidebar_url"] is None
