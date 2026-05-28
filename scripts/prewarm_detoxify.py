#!/usr/bin/env python3
"""
Download and cache the Detoxify model once for offline reuse by YSocial runtimes.
"""

import os
import time
from pathlib import Path


def get_model_cache_root() -> Path:
    configured = os.environ.get("YSOCIAL_MODEL_CACHE_DIR")
    if configured:
        root = Path(configured).expanduser()
    else:
        root = Path.home() / ".cache" / "ysocial_models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_model_cache_env():
    root = get_model_cache_root()
    hf_home = root / "huggingface"
    transformers_cache = hf_home / "transformers"
    hub_cache = hf_home / "hub"
    torch_home = root / "torch"

    for path in (root, hf_home, transformers_cache, hub_cache, torch_home):
        path.mkdir(parents=True, exist_ok=True)

    return {
        "YSOCIAL_MODEL_CACHE_DIR": str(root),
        "HF_HOME": str(hf_home),
        "TRANSFORMERS_CACHE": str(transformers_cache),
        "HUGGINGFACE_HUB_CACHE": str(hub_cache),
        "TORCH_HOME": str(torch_home),
    }


def main():
    env = get_model_cache_env()
    for key, value in env.items():
        os.environ[key] = value

    from detoxify import Detoxify

    last_error = None
    model = None
    for attempt in range(1, 4):
        try:
            model = Detoxify("original")
            break
        except Exception as exc:
            last_error = exc
            print(f"Detoxify prewarm attempt {attempt}/3 failed: {exc}")
            time.sleep(2)

    if model is None:
        raise SystemExit(f"Detoxify prewarm failed after 3 attempts: {last_error}")

    print(f"Detoxify model ready: {type(model).__name__}")
    print(f"Shared model cache: {get_model_cache_root()}")


if __name__ == "__main__":
    main()
