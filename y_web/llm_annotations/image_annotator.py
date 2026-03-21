"""
Backward-compatibility shim for y_web.llm_annotations.image_annotator.

The canonical location is now ``y_web.src.llm.image_annotator``.
All existing ``from y_web.llm_annotations.image_annotator import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.llm.image_annotator`` instead.
"""

from y_web.src.llm.image_annotator import *  # noqa: F401,F403
