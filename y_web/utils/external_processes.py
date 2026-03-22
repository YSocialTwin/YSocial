"""
External process management utilities.

Shim module: all logic has been extracted to y_web.src.simulation.* submodules.
This file re-exports every public name so that existing callers continue to work
without modification.
"""

import sys  # noqa: F401 — kept so tests can monkeypatch y_web.utils.external_processes.sys

# ---------------------------------------------------------------------------
# Process registry (shared state)
# ---------------------------------------------------------------------------
from y_web.src.simulation.process_registry import (  # noqa: F401
    WATCHDOG_ENABLED,
    _process_registry,
    _PROCESS_REGISTRY,
    _register_process,
    _unregister_process,
    cleanup_server_processes_from_db,
    cleanup_client_processes_from_db,
    stop_all_exps,
)

# ---------------------------------------------------------------------------
# Server helpers (environment detection, screen commands, server lifecycle)
# ---------------------------------------------------------------------------
# fmt: off
from y_web.src.simulation.server import (  # noqa: F401
    _resolve_server_runtime_paths,
    _register_server_with_watchdog,
    _update_server_port_in_configs,
    build_screen_command,
    build_screen_command_old,
    detect_env_handler,
    detect_env_handler_old,
    get_server_process_status,
    start_server,
    terminate_server_process,
)
# fmt: on

# ---------------------------------------------------------------------------
# Port management / process-termination helpers
# ---------------------------------------------------------------------------
# fmt: off
from y_web.src.simulation.port_manager import (  # noqa: F401
    SERVER_PORT_MAX,
    SERVER_PORT_MIN,
    _find_available_port,
    _find_new_available_port,
    _find_processes_with_open_file,
    _force_terminate_process_tree,
    _get_ports_allocated_to_experiments,
    _is_port_available,
    _terminate_process,
    _terminate_processes_holding_database,
    _terminate_processes_holding_experiment_database,
    _terminate_processes_on_port,
    terminate_process_on_port,
)
# fmt: on

# ---------------------------------------------------------------------------
# Client process management
# ---------------------------------------------------------------------------
# fmt: off
from y_web.src.simulation.client import (  # noqa: F401
    _is_client_process,
    _register_client_with_watchdog,
    start_client,
    terminate_client,
)
# fmt: on

# ---------------------------------------------------------------------------
# HPC Server/Client — delegated to y_web.src.hpc.*
# ---------------------------------------------------------------------------
# fmt: off
from y_web.src.hpc.server import (  # noqa: F401
    start_hpc_server,
    start_server_screen,
    stop_hpc_server,
)
from y_web.src.hpc.client import (  # noqa: F401
    start_hpc_client,
    stop_hpc_client,
)
# fmt: on

# ---------------------------------------------------------------------------
# Ollama / vLLM — delegated to y_web.src.llm.*
# ---------------------------------------------------------------------------
# fmt: off
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
# fmt: on
