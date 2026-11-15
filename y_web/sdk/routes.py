"""The blueprints of the core that a platform adds its views to.

A platform whose pages are served at addresses the application already knows (its participant app, its pages in the
admin) decorates the blueprint of the core that owns them, so that the endpoints keep the names the rest of the
application uses. Views are added in :meth:`PlatformProvider.attach_routes`, which runs before the blueprints are
registered: a blueprint takes no new views afterwards.
"""

from __future__ import annotations

import importlib
from typing import Any

# name -> (module, attribute)
_BLUEPRINTS = {
    "main": ("y_web.routes.social._blueprint", "main"),
    "population": ("y_web.routes.admin.sub.populations", "population"),
    "agents": ("y_web.routes.admin.sub.agents", "agents"),
    "experiments": ("y_web.routes.admin.sub.experiments._blueprint", "experiments"),
    "clients": ("y_web.routes.admin.sub.clients._blueprint", "clientsr"),
    "user": ("y_web.routes.interactions._blueprint", "user"),
}

# blueprints a platform asks for by name and address (every repository of the platform gets the same one), created on
# first use: ``blueprint("name", url_prefix="/api/x")``
_SHARED: dict = {}


def shared_blueprint_names() -> frozenset:
    """Names of the blueprints the installed platforms asked for (they belong to the participant frontend)."""
    return frozenset(_SHARED)


def shared_blueprints() -> list:
    """The blueprints the platforms asked for, for the application to register."""
    return list(_SHARED.values())


def blueprint(name: str, url_prefix: str = "") -> Any:
    """The blueprint of the core called ``name`` (``main``, ``population``, ``agents``, ``experiments``, ``clients``)."""
    from y_web.platforms import dispatch

    if name not in _BLUEPRINTS:
        from flask import Blueprint

        existing = _SHARED.get(name)
        if existing is None:
            if not url_prefix:
                raise KeyError(
                    f"{name}: no such blueprint (give its url_prefix to create one)"
                )
            existing = _SHARED[name] = Blueprint(name, __name__, url_prefix=url_prefix)
        elif url_prefix and existing.url_prefix != url_prefix:
            raise ValueError(f"{name} is already served at {existing.url_prefix}")
        return dispatch.wrap(existing)
    module, attribute = _BLUEPRINTS[name]
    return dispatch.wrap(getattr(importlib.import_module(module), attribute))
