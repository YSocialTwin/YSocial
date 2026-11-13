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
}


def blueprint(name: str) -> Any:
    """The blueprint of the core called ``name`` (``main``, ``population``, ``agents``, ``experiments``, ``clients``)."""
    module, attribute = _BLUEPRINTS[name]
    return getattr(importlib.import_module(module), attribute)
