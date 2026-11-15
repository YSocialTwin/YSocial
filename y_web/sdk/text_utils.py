"""Text helpers of the core, as ``y_web.src.content.text_utils`` offers them (the very same module)."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("y_web.src.content.text_utils")
