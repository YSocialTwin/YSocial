"""
Phase H — system/jupyter_utils.py tests.

Focuses on the pure/easily-mockable helpers.  Functions that require a running
Jupyter process or a real DB transaction are tested with mocked dependencies.

Key notes about jupyter_utils.py internals:
- psutil is imported *locally* inside functions (not at module level).
  We inject a mock via sys.modules before calling the function.
- find_instance_by_notebook_dir returns the exp_id key (not the instance object)
  when a running match is found, or None otherwise.
- create_notebook_with_template returns (False, msg) if the file already exists,
  or True on success.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# get_python_executable
# ---------------------------------------------------------------------------


def test_get_python_executable_returns_string():
    from y_web.src.system.jupyter_utils import get_python_executable

    result = get_python_executable()
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_python_executable_not_frozen_returns_sys_executable():
    """In a normal (non-frozen) environment, must return sys.executable."""
    from y_web.src.system.jupyter_utils import get_python_executable

    with patch.object(sys, "frozen", False, create=True):
        result = get_python_executable()
    assert result == sys.executable


def test_get_python_executable_frozen_falls_back_to_which(tmp_path):
    """When frozen, must use shutil.which to find a system Python."""
    fake_python = str(tmp_path / "python3")
    Path(fake_python).touch()

    from y_web.src.system.jupyter_utils import get_python_executable

    with (
        patch.object(sys, "frozen", True, create=True),
        patch(
            "shutil.which",
            side_effect=lambda n: fake_python if n == "python3" else None,
        ),
    ):
        result = get_python_executable()
    assert result == fake_python


# ---------------------------------------------------------------------------
# find_free_port (DB + psutil mocked via sys.modules)
# ---------------------------------------------------------------------------


def _make_psutil_mock(occupied_ports=None):
    """Build a psutil mock that reports the given ports as occupied."""
    occupied_ports = occupied_ports or set()
    mock_psutil = MagicMock()
    mock_psutil.AccessDenied = Exception
    mock_psutil.NoSuchProcess = Exception

    def fake_process_iter(attrs):
        if not occupied_ports:
            return []
        # Return a fake process whose connection uses the occupied port
        proc = MagicMock()
        conn = MagicMock()
        conn.laddr.port = next(iter(occupied_ports))
        proc.connections.return_value = [conn]
        return [proc]

    mock_psutil.process_iter.side_effect = fake_process_iter
    return mock_psutil


def test_find_free_port_returns_integer(app):
    from y_web.src.system.jupyter_utils import find_free_port

    mock_psutil = _make_psutil_mock()
    with app.app_context():
        with (
            patch("y_web.src.system.jupyter_utils.db") as mock_db,
            patch.dict(sys.modules, {"psutil": mock_psutil}),
        ):
            mock_db.session.query.return_value.all.return_value = []
            port = find_free_port(start_port=19999)
    assert isinstance(port, int)
    assert port == 19999


def test_find_free_port_skips_used_db_port(app):
    """find_free_port must skip ports already used by tracked Jupyter instances."""
    from y_web.src.system.jupyter_utils import find_free_port

    fake_inst = MagicMock()
    fake_inst.id = 1
    fake_inst.port = 19999
    fake_inst.process = 12345
    fake_inst.notebook_dir = "/tmp/nb"

    mock_psutil = _make_psutil_mock()
    with app.app_context():
        with (
            patch("y_web.src.system.jupyter_utils.db") as mock_db,
            patch.dict(sys.modules, {"psutil": mock_psutil}),
        ):
            mock_db.session.query.return_value.all.return_value = [fake_inst]
            port = find_free_port(start_port=19999)
    # Port 19999 is taken by DB record → must return 20000
    assert port == 20000


# ---------------------------------------------------------------------------
# find_instance_by_notebook_dir (DB mocked)
# The function returns the exp_id of the matching instance (not the ORM object)
# when a running process is found, or None otherwise.
# ---------------------------------------------------------------------------


def test_find_instance_by_notebook_dir_returns_none_when_no_match(app):
    from y_web.src.system.jupyter_utils import find_instance_by_notebook_dir

    fake_inst = MagicMock()
    fake_inst.exp_id = 42
    fake_inst.notebook_dir = "/other/path"
    fake_inst.port = 8888
    fake_inst.process = None

    with app.app_context():
        with patch("y_web.src.system.jupyter_utils.db") as mock_db:
            mock_db.session.query.return_value.all.return_value = [fake_inst]
            result = find_instance_by_notebook_dir("/home/user/notebooks")
    assert result is None


def test_find_instance_by_notebook_dir_returns_none_when_no_process(app, tmp_path):
    """When notebook_dir matches but process is None, returns None."""
    from y_web.src.system.jupyter_utils import find_instance_by_notebook_dir

    fake_inst = MagicMock()
    fake_inst.exp_id = 7
    fake_inst.notebook_dir = str(tmp_path)
    fake_inst.port = 8888
    fake_inst.process = None  # no process → returns None

    with app.app_context():
        with patch("y_web.src.system.jupyter_utils.db") as mock_db:
            mock_db.session.query.return_value.all.return_value = [fake_inst]
            result = find_instance_by_notebook_dir(str(tmp_path))
    assert result is None


# ---------------------------------------------------------------------------
# create_notebook_with_template — "already exists" short-circuit
# ---------------------------------------------------------------------------


def test_create_notebook_already_exists_returns_false(tmp_path):
    """When the target notebook file already exists, returns (False, msg)."""
    from y_web.src.system.jupyter_utils import create_notebook_with_template

    existing = tmp_path / "start_here.ipynb"
    existing.touch()

    result = create_notebook_with_template(
        filename="start_here.ipynb",
        notebook_dir=str(tmp_path),
    )
    assert result[0] is False
    assert "already exists" in result[1]
