"""
Persistent shared model-cache helpers for offline local models.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from y_web.src.system.path_utils import get_resource_path, get_writable_path

_DEFAULT_ROOT = Path.home() / ".cache" / "ysocial_models"
_CHECKPOINT_RELATIVE_PATH = Path("torch/hub/checkpoints/toxic_original-c1212f89.ckpt")
_CHECKPOINT_EXPECTED_BYTES = 418 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _system_dir() -> Path:
    base = Path(get_writable_path()) / "y_web" / "system"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _settings_path() -> Path:
    return _system_dir() / "model_cache_settings.json"


def _state_path() -> Path:
    return _system_dir() / "detoxify_download_state.json"


def _stdout_log_path() -> Path:
    return _system_dir() / "detoxify_download_stdout.log"


def _stderr_log_path() -> Path:
    return _system_dir() / "detoxify_download_stderr.log"


def _default_state() -> Dict[str, object]:
    return {
        "status": "idle",
        "progress": 0,
        "path": str(get_model_cache_root()),
        "pid": None,
        "notification_id": None,
        "message": "",
        "started_at": None,
        "finished_at": None,
        "stdout_log": str(_stdout_log_path()),
        "stderr_log": str(_stderr_log_path()),
    }


def _read_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _normalize_root(path: Optional[str | Path]) -> Path:
    if path:
        root = Path(path).expanduser()
    else:
        root = _DEFAULT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def load_model_cache_settings() -> Dict[str, object]:
    return _read_json(_settings_path())


def save_model_cache_path(path: str | Path) -> Path:
    root = _normalize_root(path)
    _write_json(
        _settings_path(),
        {
            "model_cache_dir": str(root),
            "updated_at": _utc_now(),
        },
    )
    return root


def get_model_cache_root() -> Path:
    explicit = os.environ.get("YSOCIAL_MODEL_CACHE_DIR")
    if explicit:
        return _normalize_root(explicit)
    settings = load_model_cache_settings()
    configured = settings.get("model_cache_dir")
    if configured:
        return _normalize_root(str(configured))
    return _normalize_root(None)


def get_model_cache_env(root: Optional[str | Path] = None) -> Dict[str, str]:
    cache_root = _normalize_root(root or get_model_cache_root())
    hf_home = cache_root / "huggingface"
    transformers_cache = hf_home / "transformers"
    hub_cache = hf_home / "hub"
    torch_home = cache_root / "torch"

    for path in (cache_root, hf_home, transformers_cache, hub_cache, torch_home):
        path.mkdir(parents=True, exist_ok=True)

    return {
        "YSOCIAL_MODEL_CACHE_DIR": str(cache_root),
        "HF_HOME": str(hf_home),
        "TRANSFORMERS_CACHE": str(transformers_cache),
        "HUGGINGFACE_HUB_CACHE": str(hub_cache),
        "TORCH_HOME": str(torch_home),
    }


def _tail_file(path: Path, max_chars: int = 500) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return text[-max_chars:].strip()


def _pid_is_running(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _detoxify_cache_ready(root: Path) -> bool:
    checkpoint = root / _CHECKPOINT_RELATIVE_PATH
    if not checkpoint.exists() or checkpoint.stat().st_size <= 0:
        return False
    hf_root = root / "huggingface"
    vocab_present = any(hf_root.rglob("vocab.txt"))
    tokenizer_present = any(hf_root.rglob("tokenizer_config.json"))
    return vocab_present and tokenizer_present


def _estimate_download_progress(root: Path) -> int:
    checkpoint = root / _CHECKPOINT_RELATIVE_PATH
    if checkpoint.exists():
        size = max(0, checkpoint.stat().st_size)
        checkpoint_progress = min(90, int((size / _CHECKPOINT_EXPECTED_BYTES) * 90))
        if _detoxify_cache_ready(root):
            return 100
        return max(5, checkpoint_progress)
    return 1


def load_detoxify_download_state() -> Dict[str, object]:
    state = _default_state()
    state.update(_read_json(_state_path()))
    return state


def _persist_download_state(payload: Dict[str, object]) -> Dict[str, object]:
    state = _default_state()
    state.update(payload)
    _write_json(_state_path(), state)
    return state


def refresh_detoxify_download_state() -> Dict[str, object]:
    state = load_detoxify_download_state()
    root = _normalize_root(state.get("path") or get_model_cache_root())
    state["path"] = str(root)

    if state.get("status") == "running":
        pid = state.get("pid")
        running = _pid_is_running(pid)
        progress = _estimate_download_progress(root)
        state["progress"] = progress
        if running:
            if progress >= 100:
                state["message"] = "Finalizing downloaded model assets..."
                state["progress"] = 99
            else:
                state["message"] = "Downloading Detoxify model files..."
        else:
            if _detoxify_cache_ready(root):
                state["status"] = "ready"
                state["progress"] = 100
                state["message"] = "Detoxify model is ready."
                state["finished_at"] = state.get("finished_at") or _utc_now()
                state["pid"] = None
            else:
                state["status"] = "error"
                state["message"] = (
                    _tail_file(_stderr_log_path()) or "Model download failed."
                )
                state["finished_at"] = state.get("finished_at") or _utc_now()
                state["pid"] = None

        _persist_download_state(state)

    elif state.get("status") in {"idle", "error"} and _detoxify_cache_ready(root):
        state["status"] = "ready"
        state["progress"] = 100
        state["message"] = "Detoxify model is ready."
        state["pid"] = None
        state["finished_at"] = state.get("finished_at") or _utc_now()
        _persist_download_state(state)

    return state


def start_detoxify_download(
    target_dir: str | Path, notification_id: Optional[int] = None
) -> Dict[str, object]:
    root = save_model_cache_path(target_dir)
    current = refresh_detoxify_download_state()
    if current.get("status") == "running" and _pid_is_running(current.get("pid")):
        return current

    env = os.environ.copy()
    env.update(get_model_cache_env(root))
    script_path = get_resource_path(os.path.join("scripts", "prewarm_detoxify.py"))

    stdout_path = _stdout_log_path()
    stderr_path = _stderr_log_path()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    stdout_handle = open(stdout_path, "w", encoding="utf-8", buffering=1)
    stderr_handle = open(stderr_path, "w", encoding="utf-8", buffering=1)

    try:
        if sys.platform.startswith("win"):
            try:
                creationflags = subprocess.CREATE_NO_WINDOW
            except AttributeError:
                creationflags = 0x08000000
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=stdout_handle,
                stderr=stderr_handle,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                env=env,
            )
        else:
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=stdout_handle,
                stderr=stderr_handle,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
    finally:
        stdout_handle.close()
        stderr_handle.close()

    return _persist_download_state(
        {
            "status": "running",
            "progress": max(1, _estimate_download_progress(root)),
            "path": str(root),
            "pid": process.pid,
            "notification_id": notification_id,
            "message": "Preparing Detoxify model download...",
            "started_at": _utc_now(),
            "finished_at": None,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
        }
    )
