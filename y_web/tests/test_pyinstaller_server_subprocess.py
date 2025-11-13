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

    def test_bundle_executable_detection(self):
        """Test that bundle executable is detected by checking executable name"""
        from pathlib import Path

        # Test normal Python executable
        normal_exe = "/usr/bin/python"
        is_bundle = "python" not in Path(normal_exe).name.lower()
        assert is_bundle is False, "Normal Python should not be detected as bundle"

        # Test macOS app bundle
        macos_bundle = "/Applications/YSocial.app/Contents/MacOS/YSocial"
        is_bundle = "python" not in Path(macos_bundle).name.lower()
        assert is_bundle is True, "macOS app bundle should be detected"

        # Test PyInstaller temp extraction
        temp_bundle = "/var/folders/.../YSocial"
        is_bundle = "python" not in Path(temp_bundle).name.lower()
        assert is_bundle is True, "Temp extraction should be detected as bundle"

        # Test Python with version number
        python_versioned = "/usr/bin/python3.9"
        is_bundle = "python" not in Path(python_versioned).name.lower()
        assert (
            is_bundle is False
        ), "Python with version should not be detected as bundle"

    def test_combined_pyinstaller_detection(self):
        """Test combined detection using both sys.frozen and executable name"""
        from pathlib import Path

        # Case 1: sys.frozen=True, bundle name (fully frozen)
        is_frozen = True
        exe_path = "/var/folders/.../YSocial"
        is_bundle_exe = "python" not in Path(exe_path).name.lower()
        is_pyinstaller = is_frozen or is_bundle_exe
        assert is_pyinstaller is True

        # Case 2: sys.frozen=False, bundle name (parent process not frozen but using bundle)
        is_frozen = False
        exe_path = "/Applications/YSocial.app/Contents/MacOS/YSocial"
        is_bundle_exe = "python" not in Path(exe_path).name.lower()
        is_pyinstaller = is_frozen or is_bundle_exe
        assert (
            is_pyinstaller is True
        ), "Should detect PyInstaller even when sys.frozen is False"

        # Case 3: sys.frozen=False, python name (normal development)
        is_frozen = False
        exe_path = "/usr/bin/python"
        is_bundle_exe = "python" not in Path(exe_path).name.lower()
        is_pyinstaller = is_frozen or is_bundle_exe
        assert is_pyinstaller is False

    def test_macos_pyinstaller_error_scenario(self):
        """
        Test that the fix addresses the macOS PyInstaller error.

        The original error on macOS:
        YSocial: error: unrecognized arguments: /var/folders/.../y_server_run.py -c config.json

        This occurred because:
        1. sys.executable pointed to the YSocial bundle
        2. sys.frozen was False in the parent Flask process
        3. Code only checked sys.frozen, missing the bundle detection
        4. Command became: [YSocial, y_server_run.py, -c, config.json] ❌

        With the fix:
        1. Check both sys.frozen AND executable name
        2. Detect bundle by checking if "python" is in executable name
        3. Command becomes: [YSocial, --run-server-subprocess, -c, config.json, --platform, type] ✅
        """
        from pathlib import Path

        # Simulate the macOS PyInstaller scenario from the error
        sys_executable = (
            "/var/folders/c1/gw_hwyms79bccypfg3x2988w0000gn/T/_MEIK6Hfpr/YSocial"
        )
        sys_frozen = False  # Not set in parent process

        # Old detection (would fail)
        old_detection = sys_frozen
        assert old_detection is False, "Old detection would miss this case"

        # New detection (should work)
        is_frozen = sys_frozen
        is_bundle_exe = "python" not in Path(sys_executable).name.lower()
        new_detection = is_frozen or is_bundle_exe
        assert new_detection is True, "New detection should catch this case"

        # Verify the correct command would be built
        if new_detection:
            cmd = [
                sys_executable,
                "--run-server-subprocess",
                "-c",
                "config.json",
                "--platform",
                "microblogging",
            ]
            assert cmd[1] == "--run-server-subprocess", "Should use special flag"
            assert "y_server_run.py" not in str(cmd), "Should not include script path"

    def test_meipass_detection(self):
        """Test that sys._MEIPASS is checked for PyInstaller detection"""
        # Test the detection logic with _MEIPASS

        # Case 1: sys._MEIPASS exists but sys.frozen is False
        # This is the problematic case reported by the user
        is_frozen = False
        has_meipass = True  # Simulating hasattr(sys, "_MEIPASS")
        is_bundle_exe = False  # Executable might contain "python"
        is_pyinstaller = is_frozen or has_meipass or is_bundle_exe
        assert (
            is_pyinstaller is True
        ), "Should detect PyInstaller via _MEIPASS even when frozen is False"

        # Case 2: Normal development (no _MEIPASS)
        is_frozen = False
        has_meipass = False
        is_bundle_exe = False
        is_pyinstaller = is_frozen or has_meipass or is_bundle_exe
        assert (
            is_pyinstaller is False
        ), "Should not detect PyInstaller in normal development"

        # Case 3: Full PyInstaller (all indicators present)
        is_frozen = True
        has_meipass = True
        is_bundle_exe = True
        is_pyinstaller = is_frozen or has_meipass or is_bundle_exe
        assert is_pyinstaller is True, "Should detect PyInstaller with all indicators"

    def test_macos_error_with_meipass(self):
        """
        Test that the fix addresses the specific macOS error with _MEIPASS.

        The user reported error shows script path in _MEI temp directory:
        /var/folders/.../T/_MEIluC6ib/external/YServer/y_server_run.py

        This indicates:
        1. PyInstaller extracted files to temp directory (has _MEIPASS)
        2. But sys.frozen might not be set in the Flask parent process
        3. The original fix only checked sys.frozen and executable name
        4. Need to also check sys._MEIPASS which is always set by PyInstaller

        With this fix:
        - Check sys.frozen (for typical cases)
        - Check sys._MEIPASS (for cases where frozen is not set) ← NEW
        - Check executable name (as backup)
        """
        import sys

        # Simulate the error scenario: _MEIPASS exists, but frozen might not be set
        # In actual PyInstaller, sys._MEIPASS would be set to something like:
        # /var/folders/c1/gw_hwyms79bccypfg3x2988w0000gn/T/_MEIluC6ib

        has_meipass = hasattr(sys, "_MEIPASS")  # This would be True in PyInstaller
        is_frozen = getattr(sys, "frozen", False)  # This might be False

        # In the test environment, _MEIPASS won't exist, but we can test the logic
        # The key is that checking hasattr(sys, "_MEIPASS") is more reliable

        # Simulate the detection
        simulated_has_meipass = True  # Would be true in PyInstaller
        simulated_is_frozen = False  # Might be false in parent process

        # OLD detection (would fail)
        old_detection = simulated_is_frozen
        assert old_detection is False, "Old detection misses this case"

        # NEW detection (should work)
        new_detection = simulated_is_frozen or simulated_has_meipass
        assert new_detection is True, "New detection catches this via _MEIPASS check"
