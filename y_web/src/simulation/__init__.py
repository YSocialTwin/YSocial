"""
y_web.src.simulation — canonical package for simulation process management.

Submodules
----------
process_registry : shared _process_registry dict, WATCHDOG_ENABLED flag,
                   _register_process, _unregister_process, cleanup_*, stop_all_exps
port_manager     : port availability checking and process-termination helpers
server           : server lifecycle (start_server, terminate_server_process,
                   detect_env_handler, …)
client           : client lifecycle (start_client, terminate_client, …)
watchdog         : ProcessWatchdog, get_watchdog, …
execution_backend: routing between standard and HPC backends
process_runner   : merged y_client_process_runner + y_server_process_runner

Re-exports
----------
The most-commonly-used public names are available via lazy import to avoid
circular-import issues caused by y_web.utils.__init__ star-importing
external_processes.py, which itself imports from this package:

    from y_web.src.simulation import start_server, start_client
    from y_web.src.simulation import terminate_server_process, terminate_client
    from y_web.src.simulation import stop_all_exps
"""

_LAZY = {
    "start_server": "y_web.src.simulation.server",
    "terminate_server_process": "y_web.src.simulation.server",
    "start_client": "y_web.src.simulation.client",
    "terminate_client": "y_web.src.simulation.client",
    "stop_all_exps": "y_web.src.simulation.process_registry",
}


def __getattr__(name):
    if name in _LAZY:
        import importlib

        mod = importlib.import_module(_LAZY[name])
        value = getattr(mod, name)
        globals()[name] = value  # cache to avoid repeated lookups
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
