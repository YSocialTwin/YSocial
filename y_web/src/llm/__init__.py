"""
y_web.src.llm — LLM integration package.

Sub-modules
-----------
content_annotation — ContentAnnotator: text emotion/topic annotation via LLM
image_annotator    — Annotator: image description via vision LLMs
ollama_manager     — Ollama server management (install check, start, model ops)
vllm_manager       — vLLM server management and generic model listing
"""

# Annotation classes may have different optional dependencies. Import them
# independently so one missing dependency does not hide the other export.
try:
    from y_web.src.llm.content_annotation import ContentAnnotator  # noqa: F401
except ImportError:
    class ContentAnnotator:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "ContentAnnotator requires optional LLM dependencies that are "
                "not available in this environment."
            )

try:
    from y_web.src.llm.image_annotator import Annotator  # noqa: F401
except ImportError:
    class Annotator:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Annotator requires optional multimodal LLM dependencies that "
                "are not available in this environment."
            )

from y_web.src.llm.ollama_manager import (  # noqa: F401
    delete_model_pull,
    delete_ollama_model,
    get_ollama_models,
    is_ollama_installed,
    is_ollama_running,
    ollama_processes,
    pull_ollama_model,
    start_ollama_pull,
    start_ollama_server,
)
from y_web.src.llm.vllm_manager import (  # noqa: F401
    get_llm_models,
    get_vllm_models,
    is_vllm_installed,
    is_vllm_running,
    start_vllm_server,
)
