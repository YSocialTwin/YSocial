"""
Utility modules for YSocial application.

Contains helper functions and utilities for agent generation, feed parsing,
external process management, and miscellaneous operations.
"""

import warnings

warnings.warn(
    "y_web.utils is deprecated; import from y_web.src.* modules instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .agents import *
from .external_processes import *
from .feeds import *
from .miscellanea import *
