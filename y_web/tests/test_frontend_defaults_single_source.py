"""The admin panel and the participant pages share one table of frontend-setting defaults (plan, 7.2, G16)."""


def test_admin_panel_and_participant_pages_read_the_same_table():
    from y_web.routes.admin.sub.experiments._frontend_settings import DEFAULT_SETTINGS
    from y_web.routes.social.helpers import _UI_DEFAULTS
    from y_web.src.experiment.frontend_defaults import DEFAULT_SETTINGS as CANONICAL

    assert DEFAULT_SETTINGS is CANONICAL and _UI_DEFAULTS is CANONICAL


def test_loaders_return_copies_so_a_request_cannot_change_the_defaults(monkeypatch):
    from y_web.routes.social import helpers
    from y_web.src.experiment.frontend_defaults import DEFAULT_SETTINGS

    snapshot = dict(DEFAULT_SETTINGS)
    loaded = helpers._load_ui_settings(-1)  # no row for this experiment: defaults
    loaded["posts_per_page"] = 99
    loaded["interaction_like"] = False
    assert DEFAULT_SETTINGS == snapshot
