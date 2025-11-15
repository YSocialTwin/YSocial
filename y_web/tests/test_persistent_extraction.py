"""
Tests for persistent PyInstaller extraction functionality.

These tests verify that the persistent extraction directory management
works correctly across different platforms and scenarios.
"""

import os
import platform
import sys
from pathlib import Path
from unittest import mock

import pytest

from y_web.pyinstaller_utils.persistent_extraction import (
    get_persistent_extraction_dir,
    get_runtime_tmpdir_for_spec,
)


class TestPersistentExtraction:
    """Tests for persistent extraction directory management."""

    def test_get_persistent_extraction_dir_windows(self):
        """Test that Windows uses LocalAppData directory."""
        with mock.patch("platform.system", return_value="Windows"):
            with mock.patch.dict(
                os.environ, {"LOCALAPPDATA": "C:\\Users\\Test\\AppData\\Local"}
            ):
                result = get_persistent_extraction_dir()
                assert "AppData" in result
                assert "YSocial" in result
                assert "Runtime" in result

    def test_get_persistent_extraction_dir_macos(self):
        """Test that macOS uses Application Support directory."""
        with mock.patch("platform.system", return_value="Darwin"):
            with mock.patch("pathlib.Path.home", return_value=Path("/Users/test")):
                result = get_persistent_extraction_dir()
                assert "Library" in result
                assert "Application Support" in result
                assert "YSocial" in result
                assert "Runtime" in result

    def test_get_persistent_extraction_dir_linux(self):
        """Test that Linux uses XDG data directory."""
        with mock.patch("platform.system", return_value="Linux"):
            with mock.patch("pathlib.Path.home", return_value=Path("/home/test")):
                result = get_persistent_extraction_dir()
                # Should use ~/.local/share by default
                assert ".local" in result or "share" in result.lower()
                assert "ysocial" in result.lower()

    def test_get_persistent_extraction_dir_linux_with_xdg(self):
        """Test that Linux respects XDG_DATA_HOME environment variable."""
        with mock.patch("platform.system", return_value="Linux"):
            with mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/custom/data"}):
                result = get_persistent_extraction_dir()
                assert result.startswith("/custom/data")
                assert "ysocial" in result.lower()

    def test_get_runtime_tmpdir_for_spec_returns_path(self):
        """Test that get_runtime_tmpdir_for_spec returns a valid path by default."""
        result = get_runtime_tmpdir_for_spec()
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_runtime_tmpdir_for_spec_can_be_disabled(self):
        """Test that persistent extraction can be disabled via environment variable."""
        with mock.patch.dict(
            os.environ, {"YSOCIAL_DISABLE_PERSISTENT_EXTRACTION": "1"}
        ):
            result = get_runtime_tmpdir_for_spec()
            assert result is None

    def test_get_runtime_tmpdir_for_spec_disabled_with_true(self):
        """Test that persistent extraction can be disabled with 'true'."""
        with mock.patch.dict(
            os.environ, {"YSOCIAL_DISABLE_PERSISTENT_EXTRACTION": "true"}
        ):
            result = get_runtime_tmpdir_for_spec()
            assert result is None

    def test_get_runtime_tmpdir_for_spec_disabled_with_yes(self):
        """Test that persistent extraction can be disabled with 'yes'."""
        with mock.patch.dict(
            os.environ, {"YSOCIAL_DISABLE_PERSISTENT_EXTRACTION": "yes"}
        ):
            result = get_runtime_tmpdir_for_spec()
            assert result is None

    def test_get_runtime_tmpdir_for_spec_not_disabled_with_other_values(self):
        """Test that other values don't disable persistent extraction."""
        with mock.patch.dict(
            os.environ, {"YSOCIAL_DISABLE_PERSISTENT_EXTRACTION": "no"}
        ):
            result = get_runtime_tmpdir_for_spec()
            assert result is not None

    def test_persistent_extraction_dir_is_platform_specific(self):
        """Test that different platforms get different directories."""
        current_platform = platform.system()
        result = get_persistent_extraction_dir()

        if current_platform == "Windows":
            assert "AppData" in result or "YSocial" in result
        elif current_platform == "Darwin":
            assert "Library" in result
        else:  # Linux and others
            assert "local" in result.lower() or "share" in result.lower()

    def test_persistent_extraction_dir_contains_ysocial(self):
        """Test that the extraction directory path contains 'ysocial'."""
        result = get_persistent_extraction_dir()
        assert "ysocial" in result.lower() or "YSocial" in result

    def test_persistent_extraction_dir_is_absolute(self):
        """Test that the returned path is absolute."""
        result = get_persistent_extraction_dir()
        assert os.path.isabs(result)


class TestPersistentExtractionIntegration:
    """Integration tests for persistent extraction."""

    def test_spec_can_import_module(self):
        """Test that the spec file can import the persistent_extraction module."""
        # Simulate what the spec file does
        spec_basedir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        sys.path.insert(0, os.path.join(spec_basedir, "y_web", "pyinstaller_utils"))

        try:
            from persistent_extraction import get_runtime_tmpdir_for_spec

            result = get_runtime_tmpdir_for_spec()
            assert result is None or isinstance(result, str)
        finally:
            # Clean up sys.path
            if spec_basedir in sys.path:
                sys.path.remove(spec_basedir)

    def test_runtime_tmpdir_value_is_consistent(self):
        """Test that multiple calls return the same directory."""
        result1 = get_runtime_tmpdir_for_spec()
        result2 = get_runtime_tmpdir_for_spec()
        assert result1 == result2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
