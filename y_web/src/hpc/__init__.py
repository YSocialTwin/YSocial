"""y_web.src.hpc — HPC-specific logic package."""

from y_web.src.hpc.client import start_hpc_client, stop_hpc_client
from y_web.src.hpc.log_metrics import (
    check_and_terminate_hpc_experiment,
    check_hpc_client_execution_completion,
    monitor_hpc_client_execution_logs,
    update_client_log_metrics,
    update_server_log_metrics,
)
from y_web.src.hpc.log_offset import (
    _commit_with_retry,
    _ensure_session_clean,
    get_log_file_offset,
    reset_hpc_client_metrics,
    reset_hpc_server_metrics,
    update_log_file_offset,
)
from y_web.src.hpc.log_parser import (
    get_rotating_log_files,
    has_server_log_files,
    parse_client_log_incremental,
    parse_server_log_incremental,
)
from y_web.src.hpc.log_sync_scheduler import (
    LogSyncScheduler,
    get_scheduler,
    init_log_sync_scheduler,
    stop_log_sync_scheduler,
)
from y_web.src.hpc.population_backup import (
    backup_population_for_hpc_client,
    restore_population_for_hpc_client,
)
from y_web.src.hpc.server import (
    start_hpc_server,
    start_server_screen,
    stop_hpc_server,
)
