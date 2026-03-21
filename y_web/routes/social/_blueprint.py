"""
Blueprint singleton for the "main" (social) routes.

Import this object in every route module inside the social/ sub-package
instead of creating a new Blueprint, to prevent circular imports.

Usage::

    from y_web.routes.social._blueprint import main

    @main.route("/some-path")
    def some_view():
        ...
"""

from flask import Blueprint

main = Blueprint("main", __name__)
