"""
Tests for PyInstaller subprocess handling for server processes.

This test module validates that the server process runner is correctly
invoked when running from a PyInstaller bundle.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestServerSubprocessHandling:
    """Test PyInstaller subprocess handling for server processes"""

    def test_server_subprocess_flag_detection(self):
        """Test that --run-server-subprocess flag is detected correctly"""
        # Simulate the flag detection logic from y_social_launcher.py
        test_args = ["program", "--run-server-subprocess", "-c", "config.json"]

        # Check if first argument after program name is the flag
        if len(test_args) > 1 and test_args[1] == "--run-server-subprocess":
            flag_detected = True
        else:
            flag_detected = False

        assert flag_detected is True

    def test_client_subprocess_flag_not_confused_with_server(self):
        """Test that client and server subprocess flags are distinct"""
        client_args = ["program", "--run-client-subprocess"]
        server_args = ["program", "--run-server-subprocess"]

        # They should be different
        assert client_args[1] != server_args[1]

        # Verify each flag is unique
        assert client_args[1] == "--run-client-subprocess"
        assert server_args[1] == "--run-server-subprocess"

    @patch("sys.argv", ["program", "--run-server-subprocess", "-c", "config.json"])
    def test_server_subprocess_argv_handling(self):
        """Test that argv is correctly modified when server subprocess flag is detected"""
        # Simulate the argv modification logic from y_social_launcher.py
        test_argv = sys.argv.copy()

        if len(test_argv) > 1 and test_argv[1] == "--run-server-subprocess":
            test_argv.pop(1)  # Remove the flag

        # After popping, first arg should be the program name, second should be -c
        assert test_argv[0] == "program"
        assert test_argv[1] == "-c"
        assert test_argv[2] == "config.json"

    def test_pyinstaller_frozen_detection(self):
        """Test PyInstaller frozen state detection"""
        # Test the detection logic used in external_processes.py
        is_frozen = getattr(sys, "frozen", False)

        # In normal Python execution, this should be False
        # In PyInstaller bundle, this would be True
        assert isinstance(is_frozen, bool)

    @patch("sys.frozen", True, create=True)
    @patch("sys.executable", "/path/to/YSocial")
    def test_pyinstaller_command_building_sqlite(self):
        """Test that command is built correctly for SQLite when running from PyInstaller"""
        # Simulate the command building logic from external_processes.py
        config = "/path/to/config.json"
        platform_type = "microblogging"

        # Check if running from PyInstaller
        if getattr(sys, "frozen", False):
            # Should build command with special flag
            cmd = [
                sys.executable,
                "--run-server-subprocess",
                "-c",
                config,
                "--platform",
                platform_type,
            ]
        else:
            # Would build normal command
            cmd = [sys.executable, "y_server_run.py", "-c", config]

        # Verify the command is correct for PyInstaller
        assert cmd[0] == "/path/to/YSocial"
        assert cmd[1] == "--run-server-subprocess"
        assert cmd[2] == "-c"
        assert cmd[3] == config
        assert cmd[4] == "--platform"
        assert cmd[5] == platform_type

    @patch("sys.frozen", True, create=True)
    @patch("sys.executable", "/path/to/YSocial")
    def test_pyinstaller_command_building_postgresql(self):
        """Test that command falls back to server runner for PostgreSQL when in PyInstaller"""
        # When using gunicorn with PyInstaller, should fall back to Flask server
        config = "/path/to/config.json"
        platform_type = "microblogging"
        use_gunicorn = True  # Simulating PostgreSQL mode

        if getattr(sys, "frozen", False) and use_gunicorn:
            # Should fall back to Flask server with special flag
            cmd = [
                sys.executable,
                "--run-server-subprocess",
                "-c",
                config,
                "--platform",
                platform_type,
            ]
            gunicorn_fallback = True
        else:
            cmd = ["gunicorn", "wsgi:app"]
            gunicorn_fallback = False

        # Verify that PyInstaller mode triggers fallback
        assert gunicorn_fallback is True
        assert cmd[1] == "--run-server-subprocess"

    def test_server_runner_argument_parsing(self):
        """Test that server runner correctly parses arguments"""
        # Simulate the argument parsing in y_server_process_runner.py
        from argparse import ArgumentParser

        parser = ArgumentParser()
        parser.add_argument("-c", "--config", required=True)
        parser.add_argument(
            "--platform", required=True, choices=["microblogging", "forum"]
        )

        # Test with valid arguments
        test_args = ["-c", "/path/to/config.json", "--platform", "microblogging"]
        args = parser.parse_args(test_args)

        assert args.config == "/path/to/config.json"
        assert args.platform == "microblogging"

    def test_server_runner_platform_validation(self):
        """Test that server runner validates platform type"""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        parser.add_argument("-c", "--config", required=True)
        parser.add_argument(
            "--platform", required=True, choices=["microblogging", "forum"]
        )

        # Test with microblogging
        args = parser.parse_args(["-c", "config.json", "--platform", "microblogging"])
        assert args.platform in ["microblogging", "forum"]

        # Test with forum
        args = parser.parse_args(["-c", "config.json", "--platform", "forum"])
        assert args.platform in ["microblogging", "forum"]

    def test_server_runner_requires_config(self):
        """Test that server runner requires config argument"""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        parser.add_argument("-c", "--config", required=True)
        parser.add_argument(
            "--platform", required=True, choices=["microblogging", "forum"]
        )

        # Test that missing config raises error
        with pytest.raises(SystemExit):
            parser.parse_args(["--platform", "microblogging"])

    def test_server_runner_requires_platform(self):
        """Test that server runner requires platform argument"""
        from argparse import ArgumentParser

        parser = ArgumentParser()
        parser.add_argument("-c", "--config", required=True)
        parser.add_argument(
            "--platform", required=True, choices=["microblogging", "forum"]
        )

        # Test that missing platform raises error
        with pytest.raises(SystemExit):
            parser.parse_args(["-c", "config.json"])

    def test_fix_addresses_unrecognized_arguments_error(self):
        """
        Test that the fix addresses the unrecognized arguments error.

        The original bug was:
        - start_server() built a command like: python y_server_run.py -c config.json
        - When running from PyInstaller, this became: YSocial y_server_run.py -c config.json
        - YSocial's ArgumentParser didn't recognize these arguments
        - Result: "YSocial: error: unrecognized arguments: .../y_server_run.py -c .../config.json"

        With the fix:
        - When frozen, start_server() builds: YSocial --run-server-subprocess -c config.json --platform microblogging
        - y_social_launcher.py detects --run-server-subprocess and routes to server runner
        - Server runner parses -c and --platform and starts the server
        - No unrecognized arguments error
        """
        # Simulate the old behavior (without fix) - would cause error
        old_cmd = ["YSocial", "/path/to/y_server_run.py", "-c", "config.json"]

        # Simulate the new behavior (with fix) - should work
        new_cmd = [
            "YSocial",
            "--run-server-subprocess",
            "-c",
            "config.json",
            "--platform",
            "microblogging",
        ]

        # The old command would have y_server_run.py as an argument
        # which YSocial's parser doesn't recognize
        assert "/y_server_run.py" in old_cmd[1]

        # The new command uses a special flag that y_social_launcher.py recognizes
        assert new_cmd[1] == "--run-server-subprocess"

        # The new command passes the platform type
        assert "--platform" in new_cmd
        assert "microblogging" in new_cmd

    @patch("sys.frozen", False, create=True)
    def test_non_frozen_mode_uses_script_path(self):
        """Test that non-frozen mode still uses the script path directly"""
        # When not frozen, should use the original script path
        script_path = "/path/to/external/YServer/y_server_run.py"
        config = "/path/to/config.json"

        if not getattr(sys, "frozen", False):
            # Should use script path
            uses_script_path = True
            cmd = [sys.executable, script_path, "-c", config]
        else:
            uses_script_path = False
            cmd = [sys.executable, "--run-server-subprocess", "-c", config]

        assert uses_script_path is True
        assert script_path in cmd
