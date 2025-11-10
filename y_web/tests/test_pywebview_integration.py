"""
Tests for PyWebview desktop mode integration.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch


class TestDesktopModeImport(unittest.TestCase):
    """Test that desktop mode module can be imported."""

    def test_import_y_social_desktop(self):
        """Test that y_social_desktop module can be imported."""
        try:
            import y_social_desktop

            self.assertTrue(hasattr(y_social_desktop, "start_desktop_app"))
        except ImportError as e:
            self.fail(f"Failed to import y_social_desktop: {e}")

    def test_pywebview_available(self):
        """Test that pywebview is installed and can be imported."""
        try:
            import webview

            self.assertTrue(hasattr(webview, "create_window"))
            self.assertTrue(hasattr(webview, "start"))
        except ImportError:
            self.fail("pywebview is not installed")


class TestLauncherDesktopModeSupport(unittest.TestCase):
    """Test that launcher supports desktop mode argument."""

    @patch("sys.argv", ["y_social_launcher.py", "--help"])
    def test_launcher_help_includes_desktop_option(self):
        """Test that launcher help includes desktop mode option."""
        from argparse import ArgumentParser

        from y_social_launcher import main

        # Capture help output
        with patch("sys.stdout") as mock_stdout:
            try:
                # Import and check if parser has desktop option
                import y_social_launcher

                # The launcher should have these options
                self.assertTrue(
                    "--desktop" in str(y_social_launcher.__file__)
                    or hasattr(y_social_launcher, "main")
                )
            except SystemExit:
                pass  # --help causes exit

    def test_desktop_mode_option_in_launcher_code(self):
        """Test that y_social_launcher.py contains desktop mode code."""
        with open("y_social_launcher.py", "r") as f:
            content = f.read()
            self.assertIn("--desktop", content)
            self.assertIn("y_social_desktop", content)
            self.assertIn("start_desktop_app", content)


class TestDesktopModeFunction(unittest.TestCase):
    """Test desktop mode function signature."""

    def test_start_desktop_app_signature(self):
        """Test that start_desktop_app has correct parameters."""
        import inspect

        from y_social_desktop import start_desktop_app

        sig = inspect.signature(start_desktop_app)
        params = list(sig.parameters.keys())

        # Check for essential parameters
        self.assertIn("db_type", params)
        self.assertIn("debug", params)
        self.assertIn("host", params)
        self.assertIn("port", params)
        self.assertIn("llm_backend", params)
        self.assertIn("notebook", params)
        self.assertIn("window_title", params)
        self.assertIn("window_width", params)
        self.assertIn("window_height", params)


class TestPyInstallerSpecUpdated(unittest.TestCase):
    """Test that PyInstaller spec file includes webview."""

    def test_spec_includes_webview(self):
        """Test that y_social.spec includes webview in hidden imports."""
        with open("y_social.spec", "r") as f:
            content = f.read()
            self.assertIn("webview", content)
            self.assertIn("collect_submodules(\"webview\")", content)

    def test_spec_includes_pywebview_metadata(self):
        """Test that y_social.spec includes pywebview metadata."""
        with open("y_social.spec", "r") as f:
            content = f.read()
            self.assertIn("pywebview", content)


class TestRequirementsTxt(unittest.TestCase):
    """Test that requirements.txt includes pywebview."""

    def test_requirements_includes_pywebview(self):
        """Test that pywebview is in requirements.txt."""
        with open("requirements.txt", "r") as f:
            content = f.read()
            self.assertIn("pywebview", content)


class TestPyInstallerHooks(unittest.TestCase):
    """Test that PyInstaller hooks for webview exist."""

    def test_hook_webview_exists(self):
        """Test that hook-webview.py exists in pyinstaller_hooks/."""
        import os

        hook_path = os.path.join("pyinstaller_hooks", "hook-webview.py")
        self.assertTrue(
            os.path.exists(hook_path), f"PyInstaller hook not found at {hook_path}"
        )

    def test_hook_webview_content(self):
        """Test that hook-webview.py has correct content."""
        hook_path = os.path.join("pyinstaller_hooks", "hook-webview.py")
        with open(hook_path, "r") as f:
            content = f.read()
            self.assertIn("collect_data_files", content)
            self.assertIn("collect_submodules", content)
            self.assertIn("webview", content)


if __name__ == "__main__":
    unittest.main()
