"""Dispatch to the view a platform provider registered for a client mode.

Providers living in their own repository register views such as
``create_forum_client`` on the ``clients`` blueprint; the core resolves them by
naming convention instead of importing them.
"""

from flask import current_app


def mode_view(pattern, mode):
    """Return the ``clientsr`` view ``pattern.format(mode=mode)`` or ``None``."""
    return current_app.view_functions.get("clientsr." + pattern.format(mode=mode))
