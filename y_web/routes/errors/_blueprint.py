"""
Blueprint singleton for the "errors" (error handler) routes.

Import this object in every route module inside the errors/ sub-package
instead of creating a new Blueprint, to prevent circular imports.

Usage::

    from y_web.routes.errors._blueprint import errors

    @errors.app_errorhandler(404)
    def not_found(e):
        ...
"""

from flask import Blueprint

errors = Blueprint("errors", __name__)
