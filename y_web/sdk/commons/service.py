"""``y_web.src.commons.service`` as the platform API sees it (the very same module)."""

import sys

from y_web.src.commons import service as _core

sys.modules[__name__] = _core
