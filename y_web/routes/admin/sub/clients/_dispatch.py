"""Dispatch to the view a platform provider registered for a client mode.

Providers living in their own repository register views such as
``create_forum_client`` on the ``clients`` blueprint; the core resolves them by
naming convention instead of importing them.
"""

from flask import current_app, flash, redirect, url_for

from y_web.i18n import gettext as _


def mode_view(pattern, mode):
    """Return the ``clientsr`` view ``pattern.format(mode=mode)`` or ``None``."""
    return current_app.view_functions.get("clientsr." + pattern.format(mode=mode))


def missing_view_response():
    """What a client page answers when no installed platform repository provides the view of the experiment."""
    flash(_("No platform repository provides this page for the experiment."), "error")
    return redirect(url_for("experiments.settings"))
