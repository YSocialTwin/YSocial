"""``y_web.src.commons.ordering`` as the platform API sees it (the very same module)."""

import sys

from y_web.src.commons import ordering as _core

sys.modules[__name__] = _core
