"""
Auth routes sub-package.

Contains the "auth" Blueprint which handles researcher / admin login,
experiment selection, and logout.

  _blueprint.py – Blueprint("auth") singleton
  routes.py     – login (GET/POST), select_experiment, logout
"""

from . import routes  # registers all routes with the blueprint
from ._blueprint import auth

__all__ = ["auth"]
