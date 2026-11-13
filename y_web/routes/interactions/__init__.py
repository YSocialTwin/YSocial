"""
Interactions routes sub-package.

Contains the "user_actions" Blueprint which handles all write-side user
actions: follow/unfollow, publishing posts and comments, reactions, shares,
deletions, and notification cancellations.

  _blueprint.py   – Blueprint("user_actions") singleton
  common.py       – follow, share, react, delete, cancel_notification
  microblogging.py – publish_post (microblogging platform)
"""

from . import common, microblogging  # registers all routes
from ._blueprint import user

__all__ = ["user"]
