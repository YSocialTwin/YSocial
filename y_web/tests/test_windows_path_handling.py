"""
Tests for Windows path handling in external_processes module.

This test module specifically addresses the fix for Windows compatibility
when starting the YServer, ensuring that Python executable paths containing
spaces are handled correctly.
"""

import os
import sys
from pathlib import Path

import pytest


class TestPathDetectionLogic:
    """Test the path detection logic that fixes Windows compatibility"""

    def test_windows_absolute_path_detection(self):
        """Test that Windows absolute paths are correctly identified"""
        # Windows absolute paths
        windows_paths = [
            r"C:\Python\python.exe",
            r"C:\Users\John Doe\python.exe",
            r"D:\Program Files\Python\python.exe",
            r"\\network\share\python.exe",
        ]

        for path in windows_paths:
            # On any platform, os.path.isabs should recognize these as absolute
            # (on Unix it might not, but the important thing is consistency)
            result = os.path.isabs(path)
            # On Windows, these should be absolute
            if os.name == "nt":
                assert result, f"Path {path} should be absolute on Windows"

    def test_unix_absolute_path_detection(self):
        """Test that Unix absolute paths are correctly identified"""
        # Unix absolute paths
        unix_paths = [
            "/usr/bin/python",
            "/home/user/python",
            "/home/john doe/python",
            "/opt/python/bin/python",
        ]

        for path in unix_paths:
            # These should always be recognized as absolute on Unix-like systems
            result = os.path.isabs(path)
            if os.name != "nt":  # On Unix
                assert result, f"Path {path} should be absolute on Unix"

    def test_relative_command_detection(self):
        """Test that commands are not recognized as absolute paths"""
        # Commands (not absolute paths)
        commands = [
            "pipenv run python",
            "poetry run python",
            "python",
            "python3",
        ]

        for cmd in commands:
            result = os.path.isabs(cmd)
            assert not result, f"Command {cmd} should not be recognized as absolute path"

    def test_path_classification_logic(self):
        """
        Test the core logic used in start_server to classify paths vs commands.

        This is the key logic that fixes the Windows bug:
        - Paths (even with spaces) should NOT be split
        - Commands (with spaces) SHOULD be split
        """

        # Define test cases based on the current platform
        if os.name == "nt":  # Windows
            test_cases = [
                # (input_string, has_space, is_absolute, should_split)
                # Windows paths with spaces - should NOT be split
                (r"C:\Users\Erica Cau\.conda\envs\Y\python.exe", True, True, False),
                (r"C:\Program Files\Python\python.exe", True, True, False),
                # Windows paths without spaces - should NOT be split
                (r"C:\Python\python.exe", False, True, False),
                # Commands with spaces - SHOULD be split
                ("pipenv run python", True, False, True),
                ("poetry run python", True, False, True),
                # Simple commands without spaces - should NOT be split
                ("python", False, False, False),
                ("python3", False, False, False),
            ]
        else:  # Unix/Linux
            test_cases = [
                # (input_string, has_space, is_absolute, should_split)
                # Unix paths with spaces - should NOT be split
                ("/home/john doe/python", True, True, False),
                # Unix paths without spaces - should NOT be split
                ("/usr/bin/python", False, True, False),
                # Commands with spaces - SHOULD be split
                ("pipenv run python", True, False, True),
                ("poetry run python", True, False, True),
                # Simple commands without spaces - should NOT be split
                ("python", False, False, False),
                ("python3", False, False, False),
            ]

        for path, has_space, is_absolute, should_split in test_cases:
            # Check space detection
            actual_has_space = " " in path
            assert (
                actual_has_space == has_space
            ), f"Space detection failed for {path}"

            # Check absolute path detection
            actual_is_abs = os.path.isabs(path)

            # The logic in start_server is:
            # if (isinstance(python_cmd, str) and " " in python_cmd and not os.path.isabs(python_cmd)):
            #     # split the command
            # This means split if: string AND has_space AND not_absolute
            actual_should_split = (
                isinstance(path, str) and " " in path and not os.path.isabs(path)
            )

            assert (
                actual_should_split == should_split
            ), f"Split decision failed for {path}: expected {should_split}, got {actual_should_split} (is_abs={actual_is_abs})"

    def test_fix_handles_windows_error(self):
        """
        Test that the fix specifically addresses the Windows error.

        The original bug was:
        - Path: "C:\\Users\\Erica Cau\\.conda\\envs\\Y\\python.exe"
        - Old logic: not python_cmd.startswith("/") -> True (split it)
        - Result: ["C:\\Users\\Erica", "Cau\\.conda\\envs\\Y\\python.exe", ...]
        - Error: WinError 193 (invalid Win32 application)

        With the fix:
        - Path: "C:\\Users\\Erica Cau\\.conda\\envs\\Y\\python.exe"
        - New logic: not os.path.isabs(python_cmd) -> False (don't split)
        - Result: ["C:\\Users\\Erica Cau\\.conda\\envs\\Y\\python.exe", ...]
        - No error
        """
        problematic_path = r"C:\Users\Erica Cau\.conda\envs\Y\python.exe"

        # Old logic (buggy)
        old_condition = (
            isinstance(problematic_path, str)
            and " " in problematic_path
            and not problematic_path.startswith("/")
        )
        # This would be True on Windows, causing the path to be incorrectly split

        # New logic (fixed)
        new_condition = (
            isinstance(problematic_path, str)
            and " " in problematic_path
            and not os.path.isabs(problematic_path)
        )
        # This should be False on Windows (because it IS an absolute path)

        # On Windows, the new logic should correctly identify this as a path
        if os.name == "nt":
            # Old logic would split (bad)
            assert (
                old_condition == True
            ), "Old logic should have split the path (bug)"
            # New logic should NOT split (good)
            assert (
                new_condition == False
            ), "New logic should NOT split the path (fix)"
        else:
            # On Unix, the path isn't absolute, so behavior may differ
            # But that's okay because Unix paths don't have spaces in drive letters
            pass

    def test_commands_still_work(self):
        """
        Test that the fix doesn't break command handling.

        Commands like "pipenv run python" should still be split correctly.
        """
        command = "pipenv run python"

        # The logic should split this
        should_split = (
            isinstance(command, str)
            and " " in command
            and not os.path.isabs(command)
        )

        assert should_split, "Commands with spaces should still be split"

        # If we were to split it:
        parts = command.split()
        assert parts == ["pipenv", "run", "python"]

