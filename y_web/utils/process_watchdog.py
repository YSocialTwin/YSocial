"""
Shim: process_watchdog — all logic lives in y_web.src.simulation.watchdog.

This module is kept for backward compatibility. All imports from here are
delegated to the canonical location.
"""
import warnings

warnings.warn(
    "y_web.utils.process_watchdog is deprecated; use y_web.src.simulation.watchdog instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.simulation.watchdog import (  # noqa: F401
    ProcessInfo,
    ProcessWatchdog,
    _watchdog,
    check_server_status,
    get_watchdog,
    get_watchdog_status,
    run_watchdog_once,
    set_watchdog_interval,
    stop_watchdog,
    wait_for_servers_ready,
    _load_watchdog_settings,
    _save_watchdog_last_run,
    _save_watchdog_settings,
)
