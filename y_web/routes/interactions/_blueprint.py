"""
Blueprint singleton for the "user_actions" (interactions) routes.

Import this object in every route module inside the interactions/ sub-package
instead of creating a new Blueprint, to prevent circular imports.

Usage::

    from y_web.routes.interactions._blueprint import user

    @user.route("/some-path")
    def some_view():
        ...
"""

from flask import Blueprint

user = Blueprint("user_actions", __name__)
