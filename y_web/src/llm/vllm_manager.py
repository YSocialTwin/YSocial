"""
vLLM server management utilities.

Provides functions for checking, starting, and querying models available on
the vLLM local LLM server, plus a generic OpenAI-compatible model listing
function that works with any LLM backend.
"""

import importlib.util
import shutil
import subprocess
import time
from urllib.parse import urlparse

import requests

_MODELS_DOWN_CACHE = {}
_MODELS_DOWN_TTL = 10.0  # seconds

# Values the forms and the client configs use for "no key".
_NO_API_KEY = {"", "NULL", "NONE", "EMPTY"}


class LLMAuthenticationError(Exception):
    """The LLM server rejected the request because of a missing or wrong API key."""

    def __init__(self, url, status_code):
        self.url = url
        self.status_code = status_code
        super().__init__(f"HTTP {status_code} from {url}")


def llm_auth_headers(api_key=None):
    """HTTP headers for an OpenAI-compatible server: a Bearer token, or none.

    The key is never put in a URL: it would end up in server logs and in the
    browser history.
    """
    key = str(api_key or "").strip()
    if key.upper() in _NO_API_KEY:
        return {}
    return {"Authorization": f"Bearer {key}"}


def _same_endpoint(a, b):
    return (
        str(a or "").strip().rstrip("/").lower()
        == str(b or "").strip().rstrip("/").lower()
    )


def _ambient_api_key(llm_url):
    """The key to use for *llm_url* when the caller did not pass one (``None``), or ``None``.

    Admin pages list the models of the default server without knowing which key it needs. The key comes from the
    ``LLM_API_KEY`` environment variable (the companion of ``LLM_URL``) or, inside a request, from the logged-in
    administrator's own LLM configuration when that configuration points at the same server. A key is never
    guessed for another server.
    """
    import os

    env_key = (os.getenv("LLM_API_KEY") or "").strip()
    if env_key and env_key.upper() not in _NO_API_KEY:
        return env_key
    try:
        from flask import has_request_context
        from flask_login import current_user
        from sqlalchemy import select

        if not has_request_context() or not getattr(
            current_user, "is_authenticated", False
        ):
            return None
        from y_web import db
        from y_web.src.models import Admin_users

        user = db.session.scalars(
            select(Admin_users).filter_by(username=current_user.username)
        ).first()
        key = str(getattr(user, "llm_api_key", "") or "").strip()
        if (
            key
            and key.upper() not in _NO_API_KEY
            and _same_endpoint(getattr(user, "llm_url", ""), llm_url)
        ):
            return key
    except Exception:  # noqa: BLE001 - a listing must never fail because of this lookup
        return None
    return None


def is_vllm_installed():
    """Check if a supported embedded vLLM runtime is installed in the current environment."""
    for module_name in ("vllm", "vllm_mlx", "vllm_metal"):
        try:
            if importlib.util.find_spec(module_name) is not None:
                print(f"{module_name} is installed.")
                return True
        except (ImportError, ValueError):
            pass

    if shutil.which("vllm"):
        print("vLLM CLI is installed.")
        return True

    try:
        subprocess.run(
            ["vllm", "--version"],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
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


def get_llm_models(llm_url=None, api_key=None, raise_on_auth_error=False):
    """
    Get list of models from any OpenAI-compatible LLM server.

    Args:
        llm_url: Base URL of the LLM server (e.g., 'http://localhost:8000/v1').
                 If None, uses LLM_URL from environment or falls back to ollama.
        api_key: API key sent as ``Authorization: Bearer <key>``; "NULL" or "" sends
                 no header (local Ollama and vLLM need none). None means "the key
                 configured for this server, if any" (``LLM_API_KEY`` or the logged-in
                 administrator's own configuration for the same URL).
        raise_on_auth_error: when the server answers 401 or 403, raise
                 LLMAuthenticationError instead of returning an empty list.

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

    if api_key is None:
        api_key = _ambient_api_key(llm_url)

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

        if (
            path.endswith("/v1/models")
            or path.endswith("/models")
            or path.endswith("/api/tags")
        ):
            add(base_url)
            return candidates

        if path.endswith("/v1"):
            trimmed = base_url[: -len("/v1")]
            add(f"{base_url}/models")
            add(f"{trimmed}/models")
            add(f"{trimmed}/api/tags")
        else:
            add(f"{base_url}/v1/models")
            add(f"{base_url}/models")
            add(f"{base_url}/api/tags")

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
                            model.get("name")
                            or model.get("model")
                            or model.get("id")
                            or ""
                        ).strip()
                    else:
                        name = str(model).strip()
                    if name:
                        normalized.append(name)
                return normalized
        return []

    # Negative cache: when the server is down every admin page would otherwise
    # retry (on Windows a refused connection alone takes ~2 s).
    now = time.monotonic()
    cached = _MODELS_DOWN_CACHE.get(llm_url)
    if cached and now - cached < _MODELS_DOWN_TTL:
        return []

    headers = llm_auth_headers(api_key)
    last_error = None
    for models_url in _candidate_model_endpoints(llm_url):
        try:
            response = requests.get(models_url, headers=headers, timeout=15)
            if response.status_code in (401, 403):
                # Another path on the same host will not accept the same key.
                print(
                    f"LLM server at {models_url} refused the request "
                    f"(HTTP {response.status_code}): check the API key."
                )
                if raise_on_auth_error:
                    raise LLMAuthenticationError(models_url, response.status_code)
                return []
            response.raise_for_status()
            data = response.json()
            models = _models_from_payload(data)
            if models:
                _MODELS_DOWN_CACHE.pop(llm_url, None)
                return models
            print(f"No models found in payload from {models_url}.")
        except requests.exceptions.ConnectionError as e:
            # Nothing is listening on host:port: the other candidate paths
            # point to the same socket, so stop here.
            last_error = e
            _MODELS_DOWN_CACHE[llm_url] = time.monotonic()
            print(f"LLM server at {llm_url} is not reachable (is it running?)")
            return []
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"LLM server at {models_url} is not accessible: {e}")
        except ValueError as e:
            last_error = e
            print(f"Invalid JSON payload from {models_url}: {e}")

    if last_error:
        print(f"Failed to discover models from {llm_url}: {last_error}")
    return []
