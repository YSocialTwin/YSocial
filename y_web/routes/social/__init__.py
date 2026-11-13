"""
Social routes sub-package.

Contains the "main" Blueprint which serves the microblogging views (the other platforms
register theirs on it from their own repositories).  The sub-package is assembled from:

  _blueprint.py   – Blueprint("main") singleton
  helpers.py      – shared helper functions (get_safe_profile_pic, is_admin, …)
  common.py       – profile and cross-platform routes
  microblogging.py – Twitter-style feed / thread / hashtag routes
"""

from . import (  # side-effect: registers routes
    common,
    helpers,
    microblogging,
)
from ._blueprint import main

__all__ = ["main"]
