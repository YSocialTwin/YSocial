"""
vLLM server management utilities.

Provides functions for checking, starting, and querying models available on
the vLLM local LLM server, plus a generic OpenAI-compatible model listing
function that works with any LLM backend.
"""

import subprocess
import time

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

    # Construct models endpoint URL
    models_url = (
        llm_url.replace("/v1", "/v1/models")
        if "/v1" in llm_url
        else f"{llm_url}/models"
    )

    try:
        response = requests.get(models_url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            # OpenAI-compatible format
            models = [model["id"] for model in data.get("data", [])]
            return models
        else:
            print(
                f"Failed to get LLM models from {models_url}. Status: {response.status_code}"
            )
            return []
    except requests.exceptions.RequestException as e:
        print(f"LLM server at {models_url} is not accessible: {e}")
        return []
