"""Structural regression tests for the Reddit API blueprint."""

import pytest

pytestmark = pytest.mark.unit


def test_api_reddit_blueprint_prefix():
    from flask import Blueprint

    from y_web.routes.api import api_reddit

    assert isinstance(api_reddit, Blueprint)
    assert api_reddit.name == "api_reddit"
    assert api_reddit.url_prefix == "/api/reddit"
