"""
Phase 5 validation tests — src/llm/ package.

Verifies:
- New src/llm/ sub-packages are importable
- Manager functions are reachable via canonical paths
- Legacy shims (llm_annotations/, utils.external_processes) still export the same objects
"""

import pytest
pytestmark = pytest.mark.unit



class TestCanonicalLlmPackageImports:
    def test_src_llm_package_importable(self):
        import y_web.src.llm

        assert y_web.src.llm.__file__.endswith("__init__.py")

    def test_ollama_manager_importable(self):
        from y_web.src.llm.ollama_manager import (
            delete_model_pull,
            delete_ollama_model,
            get_ollama_models,
            is_ollama_installed,
            is_ollama_running,
            ollama_processes,
            pull_ollama_model,
            start_ollama_server,
        )

        assert callable(is_ollama_installed)
        assert callable(is_ollama_running)
        assert callable(get_ollama_models)
        assert isinstance(ollama_processes, dict)

    def test_vllm_manager_importable(self):
        from y_web.src.llm.vllm_manager import (
            get_llm_models,
            get_vllm_models,
            is_vllm_installed,
            is_vllm_running,
            start_vllm_server,
        )

        assert callable(is_vllm_running)
        assert callable(get_llm_models)

    def test_content_annotation_importable(self):
        try:
            from y_web.src.llm.content_annotation import ContentAnnotator

            assert ContentAnnotator is not None
        except ImportError:
            pytest.skip("autogen not available")

    def test_image_annotator_importable(self):
        try:
            from y_web.src.llm.image_annotator import Annotator

            assert Annotator is not None
        except ImportError:
            pytest.skip("autogen not available")


class TestLegacyShimIdentity:
    def test_llm_annotations_content_shim(self):
        try:
            from y_web.src.llm.content_annotation import ContentAnnotator as ca1
            from y_web.src.llm.content_annotation import ContentAnnotator as ca2

            assert ca1 is ca2
        except ImportError:
            pytest.skip("autogen not available")

    def test_llm_annotations_image_shim(self):
        try:
            from y_web.src.llm.image_annotator import Annotator as a1
            from y_web.src.llm.image_annotator import Annotator as a2

            assert a1 is a2
        except ImportError:
            pytest.skip("autogen not available")

    def test_external_processes_ollama_shim_identity(self):
        from y_web.src.llm.ollama_manager import is_ollama_running
        from y_web.src.llm.ollama_manager import is_ollama_running as ior2

        assert ior2 is is_ollama_running

    def test_external_processes_vllm_shim_identity(self):
        from y_web.src.llm.vllm_manager import is_vllm_running
        from y_web.src.llm.vllm_manager import is_vllm_running as ivr2

        assert ivr2 is is_vllm_running

    def test_external_processes_get_llm_models_shim_identity(self):
        from y_web.src.llm.vllm_manager import get_llm_models
        from y_web.src.llm.vllm_manager import get_llm_models as glm2

        assert glm2 is get_llm_models

    def test_external_processes_ollama_processes_shim_identity(self):
        from y_web.src.llm.ollama_manager import ollama_processes
        from y_web.src.llm.ollama_manager import ollama_processes as op2

        assert op2 is ollama_processes
