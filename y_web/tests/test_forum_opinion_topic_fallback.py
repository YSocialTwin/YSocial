from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.external_repo]


def test_forum_server_topic_routes_fall_back_to_thread_root():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/external/YServerReddit/y_server/routes/content_management.py"
    ).read_text()

    assert "post = Post.query.filter_by(id=post_id).first()" in source
    assert "if not direct_topics and post.thread_id is not None:" in source
    assert "topic_post_id = post.thread_id" in source
    assert "Post_topics.query.filter_by(post_id=topic_post_id)" in source


def test_forum_experiment_10_comments_need_thread_root_topic_fallback():
    import sqlite3

    uid = "85def307_d1e7_478c_9b0b_0e2f5d46d0c5"
    db = f"/Users/rossetti/PycharmProjects/YWeb/y_web/experiments/{uid}/database_server.db"
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute("""
        select count(*)
        from post p
        join post_topics pt on pt.post_id = p.thread_id
        where p.comment_to != -1
        """)
    comments_with_root_topics = cur.fetchone()[0]
    cur.execute("""
        select count(*)
        from post p
        join post_topics pt on pt.post_id = p.id
        where p.comment_to != -1
        """)
    comments_with_direct_topics = cur.fetchone()[0]
    con.close()

    assert comments_with_root_topics > 0
    assert comments_with_direct_topics == 0
