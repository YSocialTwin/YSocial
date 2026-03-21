"""
REST API routes sub-package.

Contains two Blueprints:

  api_reddit    – image/video upload and forum post-rendering endpoints
                  (moved from routes_api/reddit.py)
  api_interview – interview server management and proxy endpoints
                  (moved from routes_api/interview.py)
"""

from .interview import api_interview
from .reddit import api_reddit

__all__ = ["api_reddit", "api_interview"]
