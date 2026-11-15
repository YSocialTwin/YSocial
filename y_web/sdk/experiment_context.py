"""The experiment of the current request, as ``y_web.src.experiment.context`` offers it (the very same module)."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("y_web.src.experiment.context")
