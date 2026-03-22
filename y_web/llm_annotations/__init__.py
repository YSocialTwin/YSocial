"""
Backward-compatibility shim for y_web.llm_annotations.

The canonical location is now ``y_web.src.llm``.
All existing ``from y_web.src.llm import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.llm`` instead.
"""

from y_web.src.llm import *  # noqa: F401,F403
