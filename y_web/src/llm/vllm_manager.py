"""
vLLM server management utilities.

Provides functions for checking, starting, and querying models available on
the vLLM local LLM server, plus a generic OpenAI-compatible model listing
function that works with any LLM backend.
"""

import subprocess
import time
from urllib.parse import urlparse

import requests


def is_vllm_installed():
    """Check if vLLM is installed."""
    try:
        subprocess.run(
            ["vllm", "--version"], capture_output=True, text=True, check=True
        )
        print("vLLM is installed.")
        return True
    except FileNotFoundError:
        print("vLLM is not installed.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking vLLM installation: {e}")
        return False


def is_vllm_running():
    """Check if vLLM server is running."""
    try:
        response = requests.get("http://127.0.0.1:8000/health")
        if response.status_code == 200:
            print("vLLM is running.")
            return True
        else:
            print(
                f"vLLM responded but not running correctly. Status: {response.status_code}"
            )
            return False
    except requests.ConnectionError:
        print("vLLM is not running or cannot be reached.")
        return False


def start_vllm_server(model_name=None):
    """
    Start vLLM server.

    Args:
        model_name: Name of model to serve (optional, if None, server must be started manually)
    """
    if is_vllm_installed():
        if not is_vllm_running():
            if model_name:
                screen_command = f"screen -dmS vllm vllm serve {model_name} --host 0.0.0.0 --port 8000"
                print(f"Starting vLLM server with model {model_name}...")
                subprocess.run(screen_command, shell=True, check=True)
                # Wait for the server to start
                time.sleep(10)
            else:
                print(
                    "vLLM is installed but not running. Please start manually with a model."
                )
        else:
            print("vLLM is already running.")
    else:
        print("vLLM is not installed.")


def get_vllm_models():
    """
    Get list of models available on vLLM server.

    Returns:
        List of model names available on vLLM server
    """
    if not is_vllm_running():
        return []

    try:
        response = requests.get("http://127.0.0.1:8000/v1/models")
        if response.status_code == 200:
            data = response.json()
            # vLLM returns models in OpenAI-compatible format
            models = [model["id"] for model in data.get("data", [])]
            return models
        else:
            print(f"Failed to get vLLM models. Status: {response.status_code}")
            return []
    except requests.ConnectionError:
        print("vLLM server is not accessible.")
        return []


def get_llm_models(llm_url=None):
    """
    Get list of models from any OpenAI-compatible LLM server.

    Args:
        llm_url: Base URL of the LLM server (e.g., 'http://localhost:8000/v1').
                 If None, uses LLM_URL from environment or falls back to ollama.

    Returns:
        List of model names available on the LLM server
    """
    import os

    # Determine URL
    if llm_url is None:
        llm_url = os.getenv("LLM_URL")
        if not llm_url:
            backend = os.getenv("LLM_BACKEND", "ollama")
            if backend == "vllm":
                llm_url = "http://127.0.0.1:8000/v1"
            else:
                llm_url = "http://127.0.0.1:11434/v1"

    def _candidate_model_endpoints(raw_url):
        base_url = str(raw_url or "").rstrip("/")
        if not base_url:
            return []

        parsed = urlparse(base_url)
        path = parsed.path.rstrip("/")
        root_url = f"{parsed.scheme}://{parsed.netloc}"
        candidates = []

        def add(endpoint):
            if endpoint and endpoint not in candidates:
                candidates.append(endpoint)

        if path.endswith("/v1/models") or path.endswith("/models") or path.endswith(
            "/api/tags"
        ):
            add(base_url)
            return candidates

        add(f"{base_url}/v1/models")
        add(f"{base_url}/models")
        add(f"{base_url}/api/tags")

        if path.endswith("/v1"):
            trimmed = base_url[: -len("/v1")]
            add(f"{base_url}/models")
            add(f"{trimmed}/models")
            add(f"{trimmed}/api/tags")

        if path:
            add(f"{root_url}/v1/models")
            add(f"{root_url}/models")
            add(f"{root_url}/api/tags")

        return candidates

    def _models_from_payload(payload):
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                return [
                    str(model.get("id", "")).strip()
                    for model in payload.get("data", [])
                    if str(model.get("id", "")).strip()
                ]
            if isinstance(payload.get("models"), list):
                normalized = []
                for model in payload.get("models", []):
                    if isinstance(model, dict):
                        name = str(
                            model.get("name") or model.get("model") or model.get("id") or ""
                        ).strip()
                    else:
                        name = str(model).strip()
                    if name:
                        normalized.append(name)
                return normalized
        return []

    last_error = None
    for models_url in _candidate_model_endpoints(llm_url):
        try:
            response = requests.get(models_url, timeout=15)
            response.raise_for_status()
            data = response.json()
            models = _models_from_payload(data)
            if models:
                return models
            print(f"No models found in payload from {models_url}.")
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"LLM server at {models_url} is not accessible: {e}")
        except ValueError as e:
            last_error = e
            print(f"Invalid JSON payload from {models_url}: {e}")

    if last_error:
        print(f"Failed to discover models from {llm_url}: {last_error}")
    return []
