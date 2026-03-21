"""
Backward-compatibility shim for y_web.llm_annotations.content_annotation.

The canonical location is now ``y_web.src.llm.content_annotation``.
All existing ``from y_web.llm_annotations.content_annotation import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.llm.content_annotation`` instead.
"""

from y_web.src.llm.content_annotation import *  # noqa: F401,F403
