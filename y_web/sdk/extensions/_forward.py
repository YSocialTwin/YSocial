"""Forwarders: a service of the core that an extension calls, resolved when it is called.

The core modules are not loaded when ``y_web.sdk.extensions`` is imported (importing them at once would be circular and
would start parts of the application), and a test that replaces the function in the core still reaches it.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable


def forward(module: str, attr: str, *, name: str, doc: str) -> Callable[..., Any]:
    """A function that calls ``module.attr`` with the same arguments, looked up at call time."""

    def call(*args: Any, **kwargs: Any) -> Any:
        return getattr(importlib.import_module(module), attr)(*args, **kwargs)

    call.__name__ = name
    call.__qualname__ = name
    call.__doc__ = doc
    call.__forward__ = (module, attr)  # type: ignore[attr-defined]
    return call
