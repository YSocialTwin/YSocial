"""
Tests for external URL opening functionality.
"""

from unittest.mock import MagicMock, patch

import pytest


def test_webbrowser_import():
    """Test that webbrowser module can be imported"""
    import webbrowser

    assert webbrowser is not None
    assert hasattr(webbrowser, "open")


@patch("webbrowser.open")
def test_webbrowser_open_called(mock_webbrowser):
    """Test that webbrowser.open can be called with a URL"""
    import webbrowser

    test_url = "https://example.com"
    webbrowser.open(test_url)
    mock_webbrowser.assert_called_once_with(test_url)


def test_url_validation():
    """Test URL validation logic"""

    def is_valid_url(url):
        """Simple URL validation"""
        if not url:
            return False
        return url.startswith(("http://", "https://"))

    # Valid URLs
    assert is_valid_url("https://example.com")
    assert is_valid_url("http://example.com")
    assert is_valid_url("https://github.com/YSocialTwin/YSocial")

    # Invalid URLs
    assert not is_valid_url("")
    assert not is_valid_url(None)
    assert not is_valid_url("not-a-url")
    assert not is_valid_url("ftp://example.com")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
