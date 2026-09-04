"""
Tests for _is_client_process() fix.

The original implementation checked for patterns that never appeared in the
actual process cmdline when running from source:
  - "y_client_process_runner" — the script is named client_runner.py, not this
  - "_client.log"             — set in an env var (YCLIENT_LOG_FILE), not cmdline

This caused terminate_client() to skip os.kill() for all source-based runs,
leaving the process alive while the DB was updated to status=0.

The fix replaces those patterns with:
  - "client_runner"  — matches the actual runner script name client_runner.py
  - "--client-id"    — a unique CLI arg present in every client invocation
"""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestIsClientProcessPatterns:
    """Verify _is_client_process recognises real client cmdlines."""

    def _run(self, cmdline):
        from y_web.src.simulation.client import _is_client_process

        mock_proc = MagicMock()
        mock_proc.cmdline.return_value = cmdline

        with patch("psutil.Process", return_value=mock_proc):
            return _is_client_process(12345)

    # ── patterns that MUST match ──────────────────────────────────────────────

    def test_source_run_client_runner_py(self):
        """Source-based run: python /path/to/y_web/src/simulation/client_runner.py ..."""
        assert self._run([
            "/usr/bin/python3",
            "/path/to/y_web/src/simulation/client_runner.py",
            "--exp-id", "1", "--client-id", "2",
        ])

    def test_client_id_arg_alone_is_sufficient(self):
        """Any invocation that includes --client-id is a client process."""
        assert self._run([
            "python", "somescript.py",
            "--exp-id", "1", "--client-id", "3", "--db-type", "sqlite",
        ])

    def test_frozen_run_client_subprocess_flag(self):
        """PyInstaller frozen mode: executable --run-client-subprocess ..."""
        assert self._run([
            "/Applications/YSocial.app/MacOS/ysocial",
            "--run-client-subprocess",
            "--exp-id", "1", "--client-id", "2",
        ])

    def test_y_client_process_runner_name(self):
        """Frozen executable named y_client_process_runner still matches."""
        assert self._run([
            "/usr/local/bin/y_client_process_runner",
            "--exp-id", "1", "--client-id", "2",
        ])

    # ── patterns that MUST NOT match ─────────────────────────────────────────

    def test_unrelated_process_rejected(self):
        """A random Python process is not a client."""
        assert not self._run([
            "/usr/bin/python3", "/path/to/some_other_script.py", "--foo", "bar"
        ])

    def test_client_log_env_var_in_cmdline_not_matched(self):
        """_client.log appearing in cmdline (unusual) would wrongly match old code.
        Confirm the new code doesn't accidentally rely on it either."""
        # If cmdline has _client.log but NOT client_runner / --client-id,
        # it should NOT be considered a client process.
        assert not self._run([
            "/usr/bin/python3", "other.py",
            "--log", "/tmp/something_client.log",
        ])

    def test_server_process_not_matched(self):
        """A server process cmdline does not match client patterns."""
        assert not self._run([
            "/usr/bin/python3",
            "/path/to/external/YServer/y_server_run.py",
            "--port", "5001",
        ])

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_no_such_process_returns_false(self):
        """When the PID no longer exists, return False (process is gone)."""
        import psutil
        from y_web.src.simulation.client import _is_client_process

        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(12345)):
            assert _is_client_process(12345) is False

    def test_access_denied_returns_true(self):
        """When we can't inspect the process, assume it's valid to avoid false skips."""
        import psutil
        from y_web.src.simulation.client import _is_client_process

        with patch("psutil.Process", side_effect=psutil.AccessDenied(12345)):
            assert _is_client_process(12345) is True
