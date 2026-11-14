"""Blueprints that platform repositories fill with their views (each with its own address prefix).

The blueprint belongs to the core, so that two repositories of one platform (the Flask pair and the Ray runtime of the
forum) can serve the same ``/api/reddit/<exp_id>/...`` addresses: their views are dispatched by experiment (see
``y_web.platforms.dispatch``).
"""

from flask import Blueprint

api_reddit = Blueprint("api_reddit", __name__, url_prefix="/api/reddit")
