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
