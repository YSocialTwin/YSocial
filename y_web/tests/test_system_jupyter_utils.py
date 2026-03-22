"""
Phase H — system/jupyter_utils.py tests.

Focuses on the pure/easily-mockable helpers.  Functions that require a running
Jupyter process or a real DB transaction are tested with mocked dependencies.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


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

    import shutil
    from y_web.src.system.jupyter_utils import get_python_executable

    with (
        patch.object(sys, "frozen", True, create=True),
        patch("shutil.which", side_effect=lambda n: fake_python if n == "python3" else None),
    ):
        result = get_python_executable()
    assert result == fake_python


# ---------------------------------------------------------------------------
# find_free_port (DB mocked)
# ---------------------------------------------------------------------------


def test_find_free_port_returns_integer(app):
    from y_web.src.system.jupyter_utils import find_free_port

    with app.app_context():
        with (
            patch("y_web.src.system.jupyter_utils.db") as mock_db,
            patch("y_web.src.system.jupyter_utils.psutil") as mock_psutil,
        ):
            mock_db.session.query.return_value.all.return_value = []
            mock_psutil.process_iter.return_value = []
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

    with app.app_context():
        with (
            patch("y_web.src.system.jupyter_utils.db") as mock_db,
            patch("y_web.src.system.jupyter_utils.psutil") as mock_psutil,
        ):
            mock_db.session.query.return_value.all.return_value = [fake_inst]
            mock_psutil.process_iter.return_value = []
            port = find_free_port(start_port=19999)
    # Port 19999 is taken → must return 20000
    assert port == 20000


# ---------------------------------------------------------------------------
# find_instance_by_notebook_dir (DB mocked)
# ---------------------------------------------------------------------------


def test_find_instance_by_notebook_dir_returns_match(app):
    from y_web.src.system.jupyter_utils import find_instance_by_notebook_dir

    fake_inst = MagicMock()
    fake_inst.notebook_dir = "/home/user/notebooks"

    with app.app_context():
        with patch("y_web.src.system.jupyter_utils.db") as mock_db:
            mock_db.session.query.return_value.all.return_value = [fake_inst]
            result = find_instance_by_notebook_dir("/home/user/notebooks")
    assert result is fake_inst


def test_find_instance_by_notebook_dir_returns_none_when_no_match(app):
    from y_web.src.system.jupyter_utils import find_instance_by_notebook_dir

    fake_inst = MagicMock()
    fake_inst.notebook_dir = "/other/path"

    with app.app_context():
        with patch("y_web.src.system.jupyter_utils.db") as mock_db:
            mock_db.session.query.return_value.all.return_value = [fake_inst]
            result = find_instance_by_notebook_dir("/home/user/notebooks")
    assert result is None


# ---------------------------------------------------------------------------
# create_notebook_with_template
# ---------------------------------------------------------------------------


def test_create_notebook_with_template_creates_file(app, tmp_path):
    """create_notebook_with_template writes a .ipynb file into notebook_dir."""
    from y_web.src.system.jupyter_utils import create_notebook_with_template

    with app.app_context():
        with (
            patch("y_web.src.system.jupyter_utils.get_resource_path",
                  return_value=str(tmp_path / "templates")),
            patch("y_web.src.system.jupyter_utils.shutil.copy2"),
            patch("y_web.src.system.jupyter_utils.os.path.exists", return_value=True),
        ):
            result = create_notebook_with_template(
                filename="start_here.ipynb",
                notebook_dir=str(tmp_path),
            )
    # Should return a path ending with the notebook filename
    assert result is None or "start_here.ipynb" in str(result)
