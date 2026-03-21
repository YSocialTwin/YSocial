"""
y_web.src.llm — LLM integration package.

Sub-modules
-----------
content_annotation — ContentAnnotator: text emotion/topic annotation via LLM
image_annotator    — Annotator: image description via vision LLMs
ollama_manager     — Ollama server management (install check, start, model ops)
vllm_manager       — vLLM server management and generic model listing
"""

# Annotation classes require the autogen framework; guard so that importing
# manager functions (which don't need autogen) still works in environments
# where autogen is not installed.
try:
    from y_web.src.llm.content_annotation import ContentAnnotator  # noqa: F401
    from y_web.src.llm.image_annotator import Annotator  # noqa: F401
except ImportError:
    pass

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
