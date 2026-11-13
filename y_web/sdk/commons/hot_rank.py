"""``y_web.src.commons.hot_rank`` as the platform API sees it (the very same module)."""

import sys

from y_web.src.commons import hot_rank as _core

sys.modules[__name__] = _core
