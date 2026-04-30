import pytest

pytestmark = pytest.mark.unit


def test_microblogging_server_get_post_topics_falls_back_to_thread_root():
    source = open(
        "/app/external/YServer/y_server/routes/content_management.py",
        "r",
    ).read()

    assert "def get_post_topics():" in source
    assert "topic_post_id = post_id" in source
    assert "if not direct_topics and post.thread_id is not None:" in source
    assert "topic_post_id = post.thread_id" in source
    assert "Post_topics.query.filter_by(post_id=topic_post_id)" in source
