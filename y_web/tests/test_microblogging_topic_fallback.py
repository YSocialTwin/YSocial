from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_get_topics_falls_back_to_post_topics_when_sentiment_rows_are_absent():
    source = Path(
        "y_web/src/data_access/posts.py"
    ).read_text()

    assert "if not cleaned:" in source
    assert "Post_topics.query.filter_by(post_id=post_id)" in source
    assert ".add_columns(Interests.interest)" in source
    assert '"neutral"' in source
