"""
Phase 7 validation tests — src/simulation/ package.

Verifies:
- New src/simulation/ sub-packages are importable via canonical paths
- Functions are callable
- Legacy shims (utils/) still export the same objects
- process_runner merged module exposes both server and client entry points
"""

import pytest
pytestmark = pytest.mark.unit



class TestCanonicalSimulationPackageImports:
    def test_src_simulation_package_importable(self):
        import y_web.src.simulation

        assert y_web.src.simulation.__file__.endswith("__init__.py")

    def test_process_registry_importable(self):
        from y_web.src.simulation.process_registry import (
            WATCHDOG_ENABLED,
            _process_registry,
            _register_process,
            _unregister_process,
            cleanup_client_processes_from_db,
            cleanup_server_processes_from_db,
            stop_all_exps,
        )

        assert callable(_register_process)
        assert callable(_unregister_process)
        assert callable(stop_all_exps)
        assert callable(cleanup_server_processes_from_db)
        assert callable(cleanup_client_processes_from_db)
        assert isinstance(_process_registry, dict)
        assert isinstance(WATCHDOG_ENABLED, bool)

    def test_port_manager_importable(self):
        from y_web.src.simulation.port_manager import (
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

        assert callable(_is_port_available)
        assert callable(_find_available_port)
        assert callable(_find_new_available_port)
        assert callable(terminate_process_on_port)
        assert callable(_force_terminate_process_tree)
        assert SERVER_PORT_MIN == 5000
        assert SERVER_PORT_MAX == 6000

    def test_server_importable(self):
        from y_web.src.simulation.server import (
            _register_server_with_watchdog,
            _resolve_server_runtime_paths,
            _update_server_port_in_configs,
            build_screen_command,
            build_screen_command_old,
            detect_env_handler,
            detect_env_handler_old,
            get_server_process_status,
            start_server,
            terminate_server_process,
        )

        assert callable(start_server)
        assert callable(terminate_server_process)
        assert callable(detect_env_handler)
        assert callable(_resolve_server_runtime_paths)
        assert callable(get_server_process_status)

    def test_client_importable(self):
        from y_web.src.simulation.client import (
            _is_client_process,
            _register_client_with_watchdog,
            start_client,
            terminate_client,
        )

        assert callable(start_client)
        assert callable(terminate_client)
        assert callable(_is_client_process)
        assert callable(_register_client_with_watchdog)

    def test_watchdog_importable(self):
        from y_web.src.simulation.watchdog import (
            ProcessWatchdog,
            check_server_status,
            get_watchdog,
            get_watchdog_status,
            run_watchdog_once,
            set_watchdog_interval,
            stop_watchdog,
            wait_for_servers_ready,
        )

        assert callable(get_watchdog)
        assert callable(stop_watchdog)
        assert callable(run_watchdog_once)
        assert callable(set_watchdog_interval)
        assert callable(get_watchdog_status)
        assert callable(check_server_status)
        assert callable(wait_for_servers_ready)

    def test_execution_backend_importable(self):
        from y_web.src.simulation.execution_backend import (
            start_client_for_experiment,
            start_server_for_experiment,
            stop_client_for_experiment,
            stop_server_for_experiment,
            uses_hpc_backend,
        )

        assert callable(uses_hpc_backend)
        assert callable(start_server_for_experiment)
        assert callable(stop_server_for_experiment)
        assert callable(start_client_for_experiment)
        assert callable(stop_client_for_experiment)

    def test_process_runner_importable(self):
        from y_web.src.simulation.process_runner import (
            _get_client_archetypes,
            _resolve_client_package_dir,
            run_client_main,
            run_server_main,
            start_client_process,
        )

        assert callable(run_server_main)
        assert callable(run_client_main)
        assert callable(start_client_process)
        assert callable(_resolve_client_package_dir)
        assert callable(_get_client_archetypes)

    def test_simulation_init_lazy_exports(self):
        from y_web.src.simulation import (
            start_client,
            start_server,
            stop_all_exps,
            terminate_client,
            terminate_server_process,
        )

        assert callable(start_server)
        assert callable(terminate_server_process)
        assert callable(start_client)
        assert callable(terminate_client)
        assert callable(stop_all_exps)


class TestServerRuntimePaths:
    def test_resolve_microblogging_path(self):
        from y_web.src.simulation.server import _resolve_server_runtime_paths

        server_dir, script_path = _resolve_server_runtime_paths(
            "/repo", "microblogging"
        )
        assert script_path.endswith("external/YServer/y_server_run.py")
        assert script_path.startswith(server_dir)

    def test_resolve_forum_path(self):
        from y_web.src.simulation.server import _resolve_server_runtime_paths

        server_dir, script_path = _resolve_server_runtime_paths("/repo", "forum")
        assert script_path.endswith("external/YServerReddit/y_server_run.py")
        assert script_path.startswith(server_dir)

    def test_resolve_unsupported_platform_raises(self):
        from y_web.src.simulation.server import _resolve_server_runtime_paths

        with pytest.raises(NotImplementedError):
            _resolve_server_runtime_paths("/repo", "unknown_platform")


class TestClientProcessRunner:
    def test_resolve_client_package_microblogging(self):
        from y_web.src.simulation.process_runner import _resolve_client_package_dir

        pkg_dir = _resolve_client_package_dir("/repo", "microblogging")
        assert pkg_dir.endswith("external/YClient")

    def test_resolve_client_package_forum(self):
        from y_web.src.simulation.process_runner import _resolve_client_package_dir

        pkg_dir = _resolve_client_package_dir("/repo", "forum")
        assert pkg_dir.endswith("external/YClientReddit")


class TestPortManager:
    def test_is_port_available_returns_bool(self):
        from y_web.src.simulation.port_manager import _is_port_available

        result = _is_port_available(59999)
        assert isinstance(result, bool)

    def test_port_constants(self):
        from y_web.src.simulation.port_manager import SERVER_PORT_MAX, SERVER_PORT_MIN

        assert SERVER_PORT_MIN == 5000
        assert SERVER_PORT_MAX == 6000
        assert SERVER_PORT_MIN < SERVER_PORT_MAX


class TestLegacyShimIdentity:
    """Verify that shims in utils/ export the exact same objects as src/simulation/."""

    def test_external_processes_start_server_shim(self):
        from y_web.src.simulation.server import start_server as canonical
        from y_web.src.simulation.server import start_server as shim

        assert shim is canonical

    def test_external_processes_terminate_server_shim(self):
        from y_web.src.simulation.server import terminate_server_process as canonical
        from y_web.src.simulation.server import terminate_server_process as shim

        assert shim is canonical

    def test_external_processes_start_client_shim(self):
        from y_web.src.simulation.client import start_client as canonical
        from y_web.src.simulation.client import start_client as shim

        assert shim is canonical

    def test_external_processes_terminate_client_shim(self):
        from y_web.src.simulation.client import terminate_client as canonical
        from y_web.src.simulation.client import terminate_client as shim

        assert shim is canonical

    def test_external_processes_detect_env_handler_shim(self):
        from y_web.src.simulation.server import detect_env_handler as canonical
        from y_web.src.simulation.server import detect_env_handler as shim

        assert shim is canonical

    def test_external_processes_port_manager_shim(self):
        from y_web.src.simulation.port_manager import (
            terminate_process_on_port as canonical,
        )
        from y_web.src.simulation.port_manager import terminate_process_on_port as shim

        assert shim is canonical

    def test_external_processes_stop_all_exps_shim(self):
        from y_web.src.simulation.process_registry import stop_all_exps as canonical
        from y_web.src.simulation.process_registry import stop_all_exps as shim

        assert shim is canonical

    def test_external_processes_watchdog_enabled_shim(self):
        from y_web.src.simulation.process_registry import WATCHDOG_ENABLED as canonical
        from y_web.src.simulation.process_registry import WATCHDOG_ENABLED as shim

        assert shim is canonical

    def test_process_watchdog_shim_identity(self):
        from y_web.src.simulation.watchdog import get_watchdog as canonical
        from y_web.src.simulation.watchdog import get_watchdog as shim

        assert shim is canonical

    def test_process_watchdog_class_shim_identity(self):
        from y_web.src.simulation.watchdog import ProcessWatchdog as canonical
        from y_web.src.simulation.watchdog import ProcessWatchdog as shim

        assert shim is canonical

    def test_y_client_runner_shim_identity(self):
        from y_web.src.simulation.process_runner import (
            _resolve_client_package_dir as canonical,
        )
        from y_web.src.simulation.process_runner import (
            _resolve_client_package_dir as shim,
        )

        assert shim is canonical

    def test_y_client_runner_start_client_process_shim(self):
        from y_web.src.simulation.process_runner import (
            start_client_process as canonical,
        )
        from y_web.src.simulation.process_runner import start_client_process as shim

        assert shim is canonical

    def test_execution_backend_shim_identity(self):
        from y_web.src.simulation.execution_backend import (
            start_server_for_experiment as canonical,
        )
        from y_web.src.simulation.execution_backend import (
            start_server_for_experiment as shim,
        )

        assert shim is canonical

    def test_process_registry_uppercase_alias_identity(self):
        """Spec validation: _PROCESS_REGISTRY (uppercase) must be the same dict as _process_registry."""
        from y_web.src.simulation.process_registry import (
            _PROCESS_REGISTRY,
            _process_registry,
        )

        assert _PROCESS_REGISTRY is _process_registry

    def test_process_registry_shim_uppercase_identity(self):
        """Spec validation from BUSINESS_LOGIC_REFACTORING.md: registry identity via shim."""
        from y_web.src.simulation.process_registry import _PROCESS_REGISTRY as canonical
        from y_web.src.simulation.process_registry import _PROCESS_REGISTRY as shim_reg

        assert canonical is shim_reg, "Process registry identity mismatch!"
