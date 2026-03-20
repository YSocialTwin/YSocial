"""Backward-compatibility shim — delegates to y_web.routes.api.interview."""
import sys as _sys
import y_web.routes.api.interview as _real

# Make "from y_web.routes_api import interview" return the real module,
# so that monkeypatch.setattr(interview, '_func', ...) affects the module
# where the functions actually live.
_sys.modules[__name__] = _real
