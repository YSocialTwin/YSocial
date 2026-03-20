"""
Blueprint singleton for the "auth" routes.

Import this object in every route module inside the auth/ sub-package
instead of creating a new Blueprint, to prevent circular imports.

Usage::

    from y_web.routes.auth._blueprint import auth

    @auth.route("/some-path")
    def some_view():
        ...
"""

from flask import Blueprint

auth = Blueprint("auth", __name__)
