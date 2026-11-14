"""
Social routes sub-package.

Contains the "main" Blueprint (every platform registers its pages on it from its own repository).  The sub-package is assembled from:

  _blueprint.py   – Blueprint("main") singleton
  helpers.py      – shared helper functions (get_safe_profile_pic, is_admin, …)
  common.py       – profile and cross-platform routes
"""

from . import (  # side-effect: registers routes
    common,
    helpers,
)
from ._blueprint import main

__all__ = ["main"]
