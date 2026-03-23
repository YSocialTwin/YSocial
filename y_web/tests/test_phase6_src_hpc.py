"""
Phase 6 validation tests — src/hpc/ package.

Verifies:
- New src/hpc/ sub-packages are importable
- Functions are reachable via canonical paths
- Legacy shims (utils/) still export the same objects
"""

import pytest
pytestmark = pytest.mark.unit



class TestCanonicalHpcPackageImports:
    def test_src_hpc_package_importable(self):
        import y_web.src.hpc

        assert y_web.src.hpc.__file__.endswith("__init__.py")

    def test_population_backup_importable(self):
        from y_web.src.hpc.population_backup import (
            backup_population_for_hpc_client,
            restore_population_for_hpc_client,
        )

        assert callable(backup_population_for_hpc_client)
        assert callable(restore_population_for_hpc_client)

    def test_log_sync_scheduler_importable(self):
        from y_web.src.hpc.log_sync_scheduler import (
            LogSyncScheduler,
            get_scheduler,
            init_log_sync_scheduler,
            stop_log_sync_scheduler,
        )

        assert callable(init_log_sync_scheduler)
        assert callable(stop_log_sync_scheduler)
        assert callable(get_scheduler)

    def test_hpc_server_importable(self):
        from y_web.src.hpc.server import (
            start_hpc_server,
            start_server_screen,
            stop_hpc_server,
        )

        assert callable(start_hpc_server)
        assert callable(stop_hpc_server)
        assert callable(start_server_screen)

    def test_hpc_client_importable(self):
        from y_web.src.hpc.client import (
            start_hpc_client,
            stop_hpc_client,
        )

        assert callable(start_hpc_client)
        assert callable(stop_hpc_client)

    def test_log_parser_importable(self):
        from y_web.src.hpc.log_parser import (
            get_rotating_log_files,
            has_server_log_files,
            parse_client_log_incremental,
            parse_server_log_incremental,
        )

        assert callable(parse_server_log_incremental)
        assert callable(parse_client_log_incremental)
        assert callable(get_rotating_log_files)
        assert callable(has_server_log_files)

    def test_log_metrics_importable(self):
        from y_web.src.hpc.log_metrics import (
            check_hpc_client_execution_completion,
            monitor_hpc_client_execution_logs,
            update_client_log_metrics,
            update_server_log_metrics,
        )

        assert callable(update_server_log_metrics)
        assert callable(update_client_log_metrics)
        assert callable(check_hpc_client_execution_completion)
        assert callable(monitor_hpc_client_execution_logs)


class TestLegacyShimIdentity:
    def test_hpc_population_backup_shim_identity(self):
        from y_web.src.hpc.population_backup import (
            backup_population_for_hpc_client as canonical,
        )
        from y_web.src.hpc.population_backup import (
            backup_population_for_hpc_client as shim,
        )

        assert shim is canonical

    def test_hpc_population_backup_restore_shim_identity(self):
        from y_web.src.hpc.population_backup import (
            restore_population_for_hpc_client as canonical,
        )
        from y_web.src.hpc.population_backup import (
            restore_population_for_hpc_client as shim,
        )

        assert shim is canonical

    def test_log_metrics_shim_identity(self):
        from y_web.src.hpc.log_metrics import update_client_log_metrics as canonical
        from y_web.src.hpc.log_metrics import update_client_log_metrics as shim

        assert shim is canonical

    def test_log_metrics_server_shim_identity(self):
        from y_web.src.hpc.log_metrics import update_server_log_metrics as canonical
        from y_web.src.hpc.log_metrics import update_server_log_metrics as shim

        assert shim is canonical

    def test_log_parser_shim_identity(self):
        from y_web.src.hpc.log_parser import parse_server_log_incremental as canonical
        from y_web.src.hpc.log_parser import parse_server_log_incremental as shim

        assert shim is canonical

    def test_external_processes_start_hpc_server_shim_identity(self):
        from y_web.src.hpc.server import start_hpc_server as canonical
        from y_web.src.hpc.server import start_hpc_server as shim

        assert shim is canonical

    def test_external_processes_stop_hpc_server_shim_identity(self):
        from y_web.src.hpc.server import stop_hpc_server as canonical
        from y_web.src.hpc.server import stop_hpc_server as shim

        assert shim is canonical

    def test_external_processes_start_hpc_client_shim_identity(self):
        from y_web.src.hpc.client import start_hpc_client as canonical
        from y_web.src.hpc.client import start_hpc_client as shim

        assert shim is canonical

    def test_external_processes_stop_hpc_client_shim_identity(self):
        from y_web.src.hpc.client import stop_hpc_client as canonical
        from y_web.src.hpc.client import stop_hpc_client as shim

        assert shim is canonical

    def test_log_sync_scheduler_shim_identity(self):
        from y_web.src.hpc.log_sync_scheduler import LogSyncScheduler as canonical
        from y_web.src.hpc.log_sync_scheduler import LogSyncScheduler as shim

        assert shim is canonical
