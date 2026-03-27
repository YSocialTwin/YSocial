from __future__ import annotations

import os
from pathlib import Path

from flask import Blueprint

api_interview = Blueprint("api_interview", __name__, url_prefix="/api/interview")
_Y_WEB_DIR = Path(__file__).resolve().parents[2]

_MEMORY_MODE_LEGACY = "legacy"
_MEMORY_MODE_SEMANTIC = "semantic"
_MEMORY_MODE_LEGACY_FALLBACK = "legacy_fallback"
_INTERVIEW_MEMORY_MODE_DEFAULT = (
    os.environ.get("INTERVIEW_MEMORY_MODE_DEFAULT", _MEMORY_MODE_SEMANTIC)
    .strip()
    .lower()
)
if _INTERVIEW_MEMORY_MODE_DEFAULT not in {_MEMORY_MODE_LEGACY, _MEMORY_MODE_SEMANTIC}:
    _INTERVIEW_MEMORY_MODE_DEFAULT = _MEMORY_MODE_SEMANTIC
_INTERVIEW_MEMORY_DEFAULT_QUERY = "Most important recent memories, relationships, norms, and ongoing threads for this agent."
