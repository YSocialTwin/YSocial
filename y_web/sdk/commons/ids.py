"""``y_web.src.commons.ids`` as the platform API sees it (the very same module)."""

import sys

from y_web.src.commons import ids as _core

sys.modules[__name__] = _core
