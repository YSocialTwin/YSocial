"""Where the runtimes live and how they are started and checked (paths, interpreter, run length, prompt packs).

The functions look the core up when called, so what the core (or a test) replaces is what a platform gets.
"""

from __future__ import annotations

from y_web import prompt_store  # noqa: F401
from y_web.src.system import prompt_packs  # noqa: F401


def build_subprocess_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return a sanitized child-process environment."""
    from y_web.src.simulation.subprocess_env import build_subprocess_env as target

    return target(extra)


def describe_client_failure(
    execution_log_path: Optional[str],
) -> Optional[Dict[str, Any]]:
    """The last ERROR record that carries an exit code, as ``exit_code``, ``error_type``, ``detail``, ``message``."""
    from y_web.src.hpc.failures import describe_client_failure as target

    return target(execution_log_path)


def exit_messages():
    """Message per exit code of the client, in the words an administrator needs (translated)."""
    from y_web.src.hpc.failures import exit_messages as target

    return target()


def detect_env_handler():
    """Detect the active Python environment and return executable path."""
    from y_web.src.simulation.server import detect_env_handler as target

    return target()


def get_external_repo_dir(repo_name):
    """Directory of an external repository: the writable copy when it exists, else the bundled one."""
    from y_web.src.system.path_utils import get_external_repo_dir as target

    return target(repo_name)


def get_hpc_platform(platform_type) -> "HpcPlatform":
    """Return the spec for ``platform_type`` or raise ``NotImplementedError`` naming it."""
    from y_web.src.hpc.platforms import get_hpc_platform as target

    return target(platform_type)


def get_writable_path(relative_path=""):
    """Get absolute path to the writable data folder (see :func:`get_home_path`)."""
    from y_web.src.system.path_utils import get_writable_path as target

    return target(relative_path)


def python_command() -> list:
    """The interpreter (as a command list) the runtimes are started and validated with."""
    from y_web.src.simulation.subprocess_env import python_command as target

    return target()


def remaining_days(
    total_days: int, last_day: int, last_slot: int, slots_per_day: int
) -> int:
    """Days the runtime must run when the client (re)starts so that the client ends after ``total_days`` in all."""
    from y_web.src.hpc.run_length import remaining_days as target

    return target(total_days, last_day, last_slot, slots_per_day)


def rewrite_server_config(
    new_folder: str, new_exp_name: str, new_db_uri: str, new_data_path: str
) -> None:
    """Point the copied ``server_config.json`` at the new folder; the run configuration is unchanged."""
    from y_web.src.hpc.server_config import rewrite_server_config as target

    return target(new_folder, new_exp_name, new_db_uri, new_data_path)


def wait_for_hpc_server_ready(exp_folder: str, timeout_seconds: int = 180) -> None:
    """Wait until the server writes its readiness marker after the orchestrator actor starts."""
    from y_web.src.hpc.client import _wait_for_hpc_server_ready as target

    return target(exp_folder, timeout_seconds)


def build_hpc_runtime_client_id(exp_folder: str, client_name: str) -> str:
    """Build a stable experiment-scoped client identifier for Ray registration."""
    from y_web.src.hpc.client import _build_hpc_runtime_client_id as target

    return target(exp_folder, client_name)


def runtime_installed_and_visible(repo_key: "str", admin_user) -> "bool":
    """True iff *repo_key* is both installed on disk AND visible to"""
    from y_web.src.external_runtime import runtime_installed_and_visible as target

    return target(repo_key, admin_user)


def set_duration(config: Dict[str, Any], days: int) -> Dict[str, Any]:
    """The client configuration with the number of days the runtime runs from now."""
    from y_web.src.hpc.run_length import set_duration as target

    return target(config, days)


def is_vllm_installed():
    """Check if a supported embedded vLLM runtime is installed in the current environment."""
    from y_web.src.llm.vllm_manager import is_vllm_installed as target

    return target()


def dispatch_platform_event(app, exp_id: "int", event: "str", payload: "dict") -> "int":
    """Hand a platform event to every installed suite module that opts in."""
    from y_web.src.external_runtime.plugin_loader import (
        dispatch_platform_event as target,
    )

    return target(app, exp_id, event, payload)


__all__ = [
    "build_hpc_runtime_client_id",
    "build_subprocess_env",
    "describe_client_failure",
    "detect_env_handler",
    "dispatch_platform_event",
    "exit_messages",
    "get_external_repo_dir",
    "get_hpc_platform",
    "get_writable_path",
    "is_vllm_installed",
    "prompt_packs",
    "prompt_store",
    "python_command",
    "remaining_days",
    "rewrite_server_config",
    "runtime_installed_and_visible",
    "set_duration",
    "wait_for_hpc_server_ready",
]
