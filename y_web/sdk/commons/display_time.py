"""The display time of a post, as ``y_web.src.commons.display_time`` offers it (the very same module)."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("y_web.src.commons.display_time")
