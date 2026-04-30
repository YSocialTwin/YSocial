from pathlib import Path

from y_web.routes.social.forum import _build_forum_sidebar_communities


def test_sidebar_prefers_subreddit_and_deduplicates_entries():
    items = [
        {
            "article": {
                "subreddit": "politics",
                "source": "reddit.com",
                "url": "https://www.reddit.com/r/politics/comments/abc",
            },
            "topics": [(1, "war", "neutral")],
        },
        {
            "article": {
                "subreddit": "r/politics",
                "source": "reddit.com",
                "url": "https://www.reddit.com/r/politics/comments/def",
            },
            "topics": [(2, "elections", "neutral")],
        },
        {
            "article": {},
            "topics": [(3, "war", "neutral"), (4, "economy", "neutral")],
        },
    ]

    communities = _build_forum_sidebar_communities(items)

    assert [entry["label"] for entry in communities] == [
        "y/politics",
        "y/war",
        "y/economy",
    ]
    assert communities[0]["kind"] == "subreddit"
    assert communities[1]["kind"] == "topic"


def test_sidebar_can_recover_subreddit_from_url_when_field_missing():
    items = [
        {
            "article": {
                "subreddit": "",
                "source": "https://www.reddit.com/r/worldnews.rss",
                "url": "https://www.reddit.com/r/worldnews/comments/abc",
            },
            "topics": [],
        }
    ]

    communities = _build_forum_sidebar_communities(items)

    assert communities == [
        {
            "slug": "worldnews",
            "label": "y/worldnews",
            "kind": "subreddit",
        }
    ]


def test_forum_compose_template_exposes_community_selector():
    template = Path("/app/y_web/templates/forum/feed.html").read_text(encoding="utf-8")

    assert 'id="post-community"' in template
    assert 'name="community_slug"' in template
    assert "Select community" in template
    assert "General feed" not in template
    assert "{% for community in available_communities %}" in template


def test_forum_compose_and_api_forward_selected_community_slug():
    js_source = Path("/app/y_web/static/assets/js/reddit/async_updates.js").read_text(
        encoding="utf-8"
    )
    api_source = Path("/app/y_web/routes/api/reddit.py").read_text(encoding="utf-8")
    action_source = Path("/app/y_web/src/forum/actions/posts.py").read_text(
        encoding="utf-8"
    )

    assert 'communitySelect: "#post-community"' in js_source
    assert "community_slug: payload.communitySlug" in js_source
    assert 'notify("Select a community before publishing.", "error");' in js_source
    assert (
        'community_slug = (payload.get("community_slug") or "").strip()' in api_source
    )
    assert (
        "create_post_reddit(current_user, content, url, community_slug)" in api_source
    )
    assert (
        'selected_community_slug = _normalize_community_slug(community_slug or "")'
        in action_source
    )


def test_forum_sidebar_template_contains_recent_and_user_sections():
    template = Path("/app/y_web/templates/forum/components/sidebar.html").read_text(
        encoding="utf-8"
    )

    assert "Most recently active communities" in template
    assert "My Communities" in template
    assert "{% for community in recent_communities %}" in template
    assert "{% for community in my_communities %}" in template


def test_forum_post_headers_render_primary_community_links():
    template = Path("/app/y_web/templates/forum/components/posts.html").read_text(
        encoding="utf-8"
    )
    js_source = Path("/app/y_web/static/assets/js/reddit/async_updates.js").read_text(
        encoding="utf-8"
    )
    query_source = Path("/app/y_web/src/forum/service/queries.py").read_text(
        encoding="utf-8"
    )

    assert "primary_community" in template
    assert "forum-post-community-link" in template
    assert "buildSubforumUrl(post.primary_community.slug)" in js_source
    assert "_primary_community_payload(article, topics, image)" in query_source


def test_forum_queries_include_image_post_subreddit_communities():
    query_source = Path("/app/y_web/src/forum/service/queries.py").read_text(
        encoding="utf-8"
    )
    formatter_source = Path("/app/y_web/src/forum/service/formatters.py").read_text(
        encoding="utf-8"
    )

    assert 'func.lower(ImagePosts.subreddit).label("image_subreddit")' in query_source
    assert "Post.id.in_(image_subquery)" in query_source
    assert 'func.lower(ImagePosts.subreddit).label("rss")' in query_source
    assert "reddit.com/media?url=" in formatter_source
    assert '"subreddit": row[4] or ""' in formatter_source


def test_forum_manual_posts_do_not_auto_extract_topics():
    action_source = Path("/app/y_web/src/forum/actions/posts.py").read_text(
        encoding="utf-8"
    )

    assert "topics = annotator.annotate_topics(content)" not in action_source
    assert "topics = []" in action_source


def test_forum_comments_inherit_topics_from_thread_root():
    action_source = Path("/app/y_web/src/forum/actions/posts.py").read_text(
        encoding="utf-8"
    )

    assert "Post_topics(post_id=comment.id, topic_id=topic_id)" in action_source
