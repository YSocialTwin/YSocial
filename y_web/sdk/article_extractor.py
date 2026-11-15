"""The article extractor of the core (the very same module)."""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("y_web.src.content.article_extractor")
