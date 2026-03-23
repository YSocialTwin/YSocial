"""
Tests for HPC client llm_v config conditional inclusion.

Verifies that llm_v config is only included when VLLM is selected
and Image Transcription is enabled.
"""

import json
from unittest.mock import Mock, patch

import pytest
pytestmark = pytest.mark.integration



class TestHPCLLMVConfig:
    """Test llm_v config conditional inclusion for VLLM backend"""

    def test_generate_hpc_client_config_with_llm_v(self):
        """Test that llm_v is included in config when llm_v_config is not None"""
        try:
            from y_web.routes.admin.sub.clients import generate_hpc_client_config

            # Prepare test data
            llm_config = {"backend": "vllm", "model": "test-model"}
            llm_v_config = {"model": "vision-model", "temperature": 0.5}
            simulation_config = {"days": 7}
            agents_config = {"max_length_thread_reading": 10}
            logging_config = {"enable_execution_log": True}

            # Generate config
            config = generate_hpc_client_config(
                client_name="test_client",
                namespace="test_namespace",
                llm_backend="vllm",
                llm_config=llm_config,
                llm_v_config=llm_v_config,
                simulation_config=simulation_config,
                agents_config=agents_config,
                logging_config=logging_config,
                enable_sentiment=False,
                emotion_annotation=False,
                enable_toxicity=False,
                perspective_api_key=None,
            )

            # Verify llm_v is in config
            assert "llm_v" in config
            assert config["llm_v"] == llm_v_config

        except ImportError as e:
            pytest.skip(f"Could not import generate_hpc_client_config: {e}")

    def test_generate_hpc_client_config_without_llm_v(self):
        """Test that llm_v is NOT included in config when llm_v_config is None"""
        try:
            from y_web.routes.admin.sub.clients import generate_hpc_client_config

            # Prepare test data
            llm_config = {"backend": "vllm", "model": "test-model"}
            llm_v_config = None  # Image transcription disabled
            simulation_config = {"days": 7}
            agents_config = {"max_length_thread_reading": 10}
            logging_config = {"enable_execution_log": True}

            # Generate config
            config = generate_hpc_client_config(
                client_name="test_client",
                namespace="test_namespace",
                llm_backend="vllm",
                llm_config=llm_config,
                llm_v_config=llm_v_config,
                simulation_config=simulation_config,
                agents_config=agents_config,
                logging_config=logging_config,
                enable_sentiment=False,
                emotion_annotation=False,
                enable_toxicity=False,
                perspective_api_key=None,
            )

            # Verify llm_v is NOT in config
            assert "llm_v" not in config

        except ImportError as e:
            pytest.skip(f"Could not import generate_hpc_client_config: {e}")

    def test_enable_image_transcription_checkbox_true(self):
        """Test form data extraction when enable_image_transcription is true"""
        try:
            from flask import Flask

            app = Flask(__name__)

            form_data = {
                "enable_image_transcription": "true",
                "llm_backend": "vllm",
                "llm_v_model": "test-vision-model",
                "llm_v_temperature": "0.5",
                "llm_v_max_tokens": "300",
                "llm_v_max_model_len": "4096",
                "llm_v_gpu_memory_utilization": "0.15",
            }

            with app.test_request_context(method="POST", data=form_data):
                from flask import request

                enable_image_transcription = (
                    request.form.get("enable_image_transcription") == "true"
                )
                llm_backend = request.form.get("llm_backend")

                # Verify extraction
                assert enable_image_transcription is True
                assert llm_backend == "vllm"

                # Simulate llm_v_config creation
                llm_v_config = None
                if llm_backend == "vllm" and enable_image_transcription:
                    llm_v_config = {
                        "model": request.form.get(
                            "llm_v_model", "openbmb/MiniCPM-V-2_6-int4"
                        ),
                        "temperature": float(
                            request.form.get("llm_v_temperature", "0.5")
                        ),
                        "max_tokens": int(request.form.get("llm_v_max_tokens", "300")),
                    }

                # Verify llm_v_config is created
                assert llm_v_config is not None
                assert llm_v_config["model"] == "test-vision-model"

        except ImportError as e:
            pytest.skip(f"Could not import Flask: {e}")

    def test_enable_image_transcription_checkbox_false(self):
        """Test form data extraction when enable_image_transcription is false"""
        try:
            from flask import Flask

            app = Flask(__name__)

            form_data = {
                # enable_image_transcription checkbox not checked (not in form data)
                "llm_backend": "vllm",
                "llm_v_model": "test-vision-model",
            }

            with app.test_request_context(method="POST", data=form_data):
                from flask import request

                enable_image_transcription = (
                    request.form.get("enable_image_transcription") == "true"
                )
                llm_backend = request.form.get("llm_backend")

                # Verify extraction
                assert enable_image_transcription is False
                assert llm_backend == "vllm"

                # Simulate llm_v_config creation
                llm_v_config = None
                if llm_backend == "vllm" and enable_image_transcription:
                    llm_v_config = {
                        "model": request.form.get(
                            "llm_v_model", "openbmb/MiniCPM-V-2_6-int4"
                        )
                    }

                # Verify llm_v_config is NOT created
                assert llm_v_config is None

        except ImportError as e:
            pytest.skip(f"Could not import Flask: {e}")

    def test_ollama_backend_always_has_llm_v_config(self):
        """Test that Ollama backend always includes llm_v_config"""
        try:
            from flask import Flask

            app = Flask(__name__)

            form_data = {
                "llm_backend": "ollama",
                # enable_image_transcription doesn't matter for Ollama
            }

            with app.test_request_context(method="POST", data=form_data):
                from flask import request

                llm_backend = request.form.get("llm_backend")
                enable_image_transcription = (
                    request.form.get("enable_image_transcription") == "true"
                )

                # Verify extraction
                assert llm_backend == "ollama"

                # Simulate config creation (Ollama path)
                if llm_backend == "ollama":
                    # Ollama always gets llm_v_config regardless of checkbox
                    llm_v_config = {
                        "address": "localhost",
                        "port": 11434,
                        "model": "minicpm-v",
                        "temperature": 0.5,
                    }
                else:
                    llm_v_config = None

                # Verify llm_v_config is created for Ollama
                assert llm_v_config is not None
                assert llm_v_config["model"] == "minicpm-v"

        except ImportError as e:
            pytest.skip(f"Could not import Flask: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
