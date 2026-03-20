"""
Admin sub-blueprint re-exports.

This package re-exports every Blueprint from the existing ``routes_admin``
modules so that the central ``register_blueprints()`` factory can import
them all from a single location without requiring the underlying source
files to be moved.
"""

from y_web.routes_admin.agents_routes import agents
from y_web.routes_admin.clients_routes import clientsr
from y_web.routes_admin.experiments_routes import experiments
from y_web.routes_admin.jupyterlab_routes import lab
from y_web.routes_admin.ollama_routes import ollama
from y_web.routes_admin.pages_routes import pages
from y_web.routes_admin.populations_routes import population
from y_web.routes_admin.tutorial_routes import tutorial
from y_web.routes_admin.users_routes import users

__all__ = [
    "agents", "clientsr", "experiments", "lab",
    "ollama", "pages", "population", "tutorial", "users",
]
