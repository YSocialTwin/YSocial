"""The data access of the core, as ``y_web.src.data_access`` offers it (the very same module)."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("y_web.src.data_access")
