import pytest

pytestmark = pytest.mark.unit

import json
from types import SimpleNamespace

from y_web.routes.admin.sub.experiments._feeds import (
    _forum_image_resource_payload,
    _forum_rss_resource_payload,
    _selected_image_resource_ids,
    _selected_rss_resource_ids,
)


def test_forum_rss_resource_payload_matches_experiment_file_shape():
    resource = SimpleNamespace(
        id=4,
        name="Example Feed",
        feed_url="https://example.com/feed.xml",
        url_site="https://example.com",
        description="Example description",
    )

    assert _forum_rss_resource_payload(resource) == {
        "id": 4,
        "name": "Example Feed",
        "feed_url": "https://example.com/feed.xml",
        "url_site": "https://example.com",
        "description": "Example description",
    }


def test_forum_image_resource_payload_normalizes_interests():
    resource = SimpleNamespace(id=7, subreddit="Memes", interests='["fun", " memes "]')

    assert _forum_image_resource_payload(resource) == {
        "id": 7,
        "subreddit": "memes",
        "interests": ["fun", "memes"],
    }


def test_selected_rss_resource_ids_map_from_existing_experiment_file(tmp_path):
    resources = [
        SimpleNamespace(id=11, feed_url="https://example.com/feed.xml"),
        SimpleNamespace(id=12, feed_url="https://other.example/rss"),
    ]
    (tmp_path / "rss_feeds.json").write_text(
        json.dumps(
            [
                {"feed_url": "https://other.example/rss"},
                {"feed_url": "https://example.com/feed.xml"},
            ]
        ),
        encoding="utf-8",
    )

    assert _selected_rss_resource_ids(str(tmp_path), resources) == [12, 11]


def test_selected_image_resource_ids_map_from_existing_experiment_file(tmp_path):
    resources = [
        SimpleNamespace(id=21, subreddit="memes"),
        SimpleNamespace(id=22, subreddit="pics"),
    ]
    (tmp_path / "image_feeds.json").write_text(
        json.dumps(
            [
                {"subreddit": "pics"},
                {"subreddit": "memes"},
            ]
        ),
        encoding="utf-8",
    )

    assert _selected_image_resource_ids(str(tmp_path), resources) == [22, 21]
