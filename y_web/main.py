"""
Backward-compatibility shim. Do not delete until all consumers are updated.
"""
import os  # noqa: F401 – keep for patch target y_web.main.os

from y_web.routes.social import main  # noqa: F401  (re-registers all routes)
from y_web.routes.social.helpers import (  # noqa: F401
    _experiment_memory_enabled,
    get_safe_profile_pic,
    is_admin,
)
# Re-export the models that the tests patch so their patch paths keep working.
from y_web.models import Exps  # noqa: F401
