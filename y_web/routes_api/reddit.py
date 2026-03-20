"""Backward-compatibility shim — delegates to y_web.routes.api.reddit."""
import sys as _sys
import y_web.routes.api.reddit as _real

_sys.modules[__name__] = _real
