"""
Social routes sub-package.

Contains the "main" Blueprint which serves both the microblogging and forum
platform views.  The sub-package is assembled from:

  _blueprint.py   – Blueprint("main") singleton
  helpers.py      – shared helper functions (get_safe_profile_pic, is_admin, …)
  common.py       – profile and cross-platform routes
  microblogging.py – Twitter-style feed / thread / hashtag routes
  photo.py         – Instagram-style feed routes
  forum.py        – Reddit-style feed / thread / search routes
"""

from . import common, forum, helpers, microblogging, photo  # side-effect: registers routes
from ._blueprint import main

__all__ = ["main"]
