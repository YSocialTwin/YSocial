"""Template globals that give the pages what the platforms declare (labels, badges, form fields, menu)."""

from __future__ import annotations

from flask import Flask

from y_web.platforms import registry


def platform_stylesheets() -> list:
    """Addresses of the stylesheets the installed platforms ask the admin pages to load."""
    from flask import url_for
    from werkzeug.routing import BuildError

    found = []
    for provider in registry.providers():
        for filename in provider.admin_css:
            try:
                found.append(
                    url_for(
                        f"platform_static_{provider.provider_id}", filename=filename
                    )
                )
            except BuildError:
                continue
    return found


def platform_tutorial_scripts() -> list:
    """Addresses of the guided-tour scripts the installed platforms add to the generic admin tutorial."""
    from flask import url_for
    from werkzeug.routing import BuildError

    found = []
    for provider in registry.providers():
        for filename in provider.tutorial_scripts():
            try:
                found.append(
                    url_for(
                        f"platform_static_{provider.provider_id}", filename=filename
                    )
                )
            except BuildError:
                continue
    return found


def register_platform_globals(app: Flask) -> None:
    globals_ = app.jinja_env.globals
    globals_["platform_stylesheets"] = platform_stylesheets
    globals_["platform_tutorial_scripts"] = platform_tutorial_scripts
    globals_["platform_catalog"] = registry.catalog
    globals_["default_platform_key"] = registry.default_key
    globals_["client_form_field"] = registry.client_form_field
    globals_["stress_reward_family"] = registry.stress_reward_family
    globals_["platform_badge_label"] = registry.badge_label
    globals_["platform_badge_text"] = registry.badge_text
