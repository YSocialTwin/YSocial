"""Template globals that give the pages what the platforms declare (labels, badges, form fields, menu)."""

from __future__ import annotations

from flask import Flask

from y_web.platforms import registry


def register_platform_globals(app: Flask) -> None:
    globals_ = app.jinja_env.globals
    globals_["platform_catalog"] = registry.catalog
    globals_["default_platform_key"] = registry.default_key
    globals_["client_form_field"] = registry.client_form_field
    globals_["stress_reward_family"] = registry.stress_reward_family
    globals_["platform_badge_label"] = registry.badge_label
    globals_["platform_badge_text"] = registry.badge_text
