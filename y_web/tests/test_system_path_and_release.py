"""
Phase G — system/path_utils.py and system/check_release.py tests.

path_utils is pure logic (no DB, no Flask).
check_release: only version_tuple and download_file are tested; network calls
and DB writes are patched out.
"""

import hashlib
import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# path_utils: get_base_path
# ---------------------------------------------------------------------------


def test_get_base_path_returns_string():
    from y_web.src.system.path_utils import get_base_path

    assert isinstance(get_base_path(), str)


def test_get_base_path_directory_exists():
    from y_web.src.system.path_utils import get_base_path

    assert os.path.isdir(get_base_path())


def test_get_base_path_contains_y_web():
    from y_web.src.system.path_utils import get_base_path

    # The y_web package directory must exist under base_path
    assert os.path.isdir(os.path.join(get_base_path(), "y_web"))


# ---------------------------------------------------------------------------
# path_utils: get_resource_path
# ---------------------------------------------------------------------------


def test_get_resource_path_joins_correctly():
    from y_web.src.system.path_utils import get_base_path, get_resource_path

    expected = os.path.join(get_base_path(), "data_schema")
    assert get_resource_path("data_schema") == expected


def test_get_resource_path_empty_relative():
    from y_web.src.system.path_utils import get_base_path, get_resource_path

    # Empty relative path should return the base path joined with ""
    result = get_resource_path("")
    assert result.startswith(get_base_path())


# ---------------------------------------------------------------------------
# path_utils: get_y_web_path
# ---------------------------------------------------------------------------


def test_get_y_web_path_points_to_y_web_dir():
    from y_web.src.system.path_utils import get_y_web_path

    path = get_y_web_path()
    assert os.path.basename(path) == "y_web"
    assert os.path.isdir(path)


# ---------------------------------------------------------------------------
# path_utils: get_writable_path
# ---------------------------------------------------------------------------


def test_get_writable_path_returns_string():
    from y_web.src.system.path_utils import get_writable_path

    assert isinstance(get_writable_path(), str)


def test_get_writable_path_with_relative_joins():
    from y_web.src.system.path_utils import get_writable_path

    result = get_writable_path("some/subdir")
    assert result.endswith("some/subdir") or result.endswith("some\\subdir")


# ---------------------------------------------------------------------------
# check_release: version_tuple
# ---------------------------------------------------------------------------


def test_version_tuple_basic():
    from y_web.src.system.check_release import version_tuple

    assert version_tuple("1.2.3") == (1, 2, 3)


def test_version_tuple_single():
    from y_web.src.system.check_release import version_tuple

    assert version_tuple("5") == (5,)


def test_version_tuple_comparison():
    from y_web.src.system.check_release import version_tuple

    assert version_tuple("1.10.0") > version_tuple("1.9.0")


# ---------------------------------------------------------------------------
# check_release: download_file (patched network, real tmp file)
# ---------------------------------------------------------------------------


def test_download_file_verifies_size_mismatch(tmp_path):
    """download_file returns (False, msg) when the downloaded size is wrong."""
    from unittest.mock import MagicMock, patch

    from y_web.src.system.check_release import download_file

    dest = tmp_path / "test_download.bin"
    content = b"hello world"

    mock_response = MagicMock()
    mock_response.iter_content = lambda chunk_size: [content]
    mock_response.raise_for_status = MagicMock()

    with patch(
        "y_web.src.system.check_release.requests.get", return_value=mock_response
    ):
        ok, msg = download_file(
            "https://example.com/file.bin",
            str(dest),
            exp_size=999,  # wrong size
            exp_sha256="deadbeef",
        )

    assert ok is False
    assert "size" in msg.lower()


def test_download_file_verifies_sha256_mismatch(tmp_path):
    """download_file returns (False, msg) when SHA256 does not match."""
    from unittest.mock import MagicMock, patch

    from y_web.src.system.check_release import download_file

    dest = tmp_path / "test_download2.bin"
    content = b"hello world"

    mock_response = MagicMock()
    mock_response.iter_content = lambda chunk_size: [content]
    mock_response.raise_for_status = MagicMock()

    with patch(
        "y_web.src.system.check_release.requests.get", return_value=mock_response
    ):
        ok, msg = download_file(
            "https://example.com/file.bin",
            str(dest),
            exp_size=len(content),
            exp_sha256="000000",  # wrong hash
        )

    assert ok is False
    assert "sha256" in msg.lower()


def test_download_file_succeeds_with_correct_metadata(tmp_path):
    """download_file returns (True, msg) when size and SHA256 both match."""
    from unittest.mock import MagicMock, patch

    from y_web.src.system.check_release import download_file

    dest = tmp_path / "test_download3.bin"
    content = b"hello world"
    correct_sha256 = hashlib.sha256(content).hexdigest()

    mock_response = MagicMock()
    mock_response.iter_content = lambda chunk_size: [content]
    mock_response.raise_for_status = MagicMock()

    with patch(
        "y_web.src.system.check_release.requests.get", return_value=mock_response
    ):
        ok, msg = download_file(
            "https://example.com/file.bin",
            str(dest),
            exp_size=len(content),
            exp_sha256=correct_sha256,
        )

    assert ok is True
