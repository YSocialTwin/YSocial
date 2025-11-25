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
        """Test that y_social_desktop module can be imported from pyinstaller_utils."""
        # First check if pywebview is available
        try:
            import webview
        except ImportError:
            self.skipTest(
                "pywebview is not installed - skipping desktop module import test"
            )

        try:
            from y_web.pyinstaller_utils.y_social_desktop import start_desktop_app

            self.assertTrue(callable(start_desktop_app))
        except ImportError as e:
            self.fail(f"Failed to import y_social_desktop: {e}")

    def test_pywebview_available(self):
        """Test that pywebview is installed and can be imported."""
        try:
            import webview

            self.assertTrue(hasattr(webview, "create_window"))
            self.assertTrue(hasattr(webview, "start"))
        except ImportError:
            self.skipTest("pywebview is not installed")


class TestLauncherDesktopModeSupport(unittest.TestCase):
    """Test that launcher supports desktop mode argument."""

    def test_launcher_import(self):
        """Test that y_social_launcher can be imported."""
        try:
            from y_web.pyinstaller_utils.y_social_launcher import main

            self.assertTrue(callable(main))
        except ImportError as e:
            self.fail(f"Failed to import y_social_launcher: {e}")

    def test_desktop_launcher_exists(self):
        """Test that y_social_desktop.py exists in pyinstaller_utils."""
        from pathlib import Path

        desktop_path = (
            Path(__file__).parent.parent / "pyinstaller_utils" / "y_social_desktop.py"
        )
        self.assertTrue(
            desktop_path.exists(), f"y_social_desktop.py not found at {desktop_path}"
        )


class TestDesktopModeFunction(unittest.TestCase):
    """Test desktop mode function signature."""

    def test_start_desktop_app_signature(self):
        """Test that start_desktop_app has correct parameters."""
        try:
            import webview
        except ImportError:
            self.skipTest("pywebview is not installed - skipping signature test")

        import inspect

        from y_web.pyinstaller_utils.y_social_desktop import start_desktop_app

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
        from pathlib import Path

        project_root = Path(__file__).parent.parent.parent
        spec_path = project_root / "y_social.spec"

        with open(spec_path, "r") as f:
            content = f.read()
            self.assertIn("webview", content)
            self.assertIn('collect_submodules("webview")', content)

    def test_spec_includes_pywebview_metadata(self):
        """Test that y_social.spec includes pywebview metadata."""
        from pathlib import Path

        project_root = Path(__file__).parent.parent.parent
        spec_path = project_root / "y_social.spec"

        with open(spec_path, "r") as f:
            content = f.read()
            self.assertIn("pywebview", content)


class TestRequirementsTxt(unittest.TestCase):
    """Test that requirements.txt includes pywebview."""

    def test_requirements_includes_pywebview(self):
        """Test that pywebview is in requirements.txt."""
        from pathlib import Path

        project_root = Path(__file__).parent.parent.parent
        req_path = project_root / "requirements.txt"

        with open(req_path, "r") as f:
            content = f.read()
            self.assertIn("pywebview", content)


class TestPyInstallerHooks(unittest.TestCase):
    """Test that PyInstaller hooks for webview exist."""

    def test_hook_webview_exists(self):
        """Test that hook-webview.py exists in pyinstaller_hooks/."""
        from pathlib import Path

        hook_path = (
            Path(__file__).parent.parent
            / "pyinstaller_utils"
            / "pyinstaller_hooks"
            / "hook-webview.py"
        )
        self.assertTrue(
            hook_path.exists(), f"PyInstaller hook not found at {hook_path}"
        )

    def test_hook_webview_content(self):
        """Test that hook-webview.py has correct content."""
        from pathlib import Path

        hook_path = (
            Path(__file__).parent.parent
            / "pyinstaller_utils"
            / "pyinstaller_hooks"
            / "hook-webview.py"
        )
        with open(hook_path, "r") as f:
            content = f.read()
            self.assertIn("collect_data_files", content)
            self.assertIn("collect_submodules", content)
            self.assertIn("webview", content)


if __name__ == "__main__":
    unittest.main()
