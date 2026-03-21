"""
Interactions routes sub-package.

Contains the "user_actions" Blueprint which handles all write-side user
actions: follow/unfollow, publishing posts and comments, reactions, shares,
deletions, and notification cancellations.

  _blueprint.py   – Blueprint("user_actions") singleton
  common.py       – follow, share, react, delete, cancel_notification
  microblogging.py – publish_post (microblogging platform)
  forum.py        – publish_post_reddit, publish_comment (forum platform)
"""

from ._blueprint import user
from . import common, microblogging, forum  # registers all routes

__all__ = ["user"]
