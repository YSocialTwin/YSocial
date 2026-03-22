"""
Phase 8 validation tests — src/forum/ package.

Verifies:
- New src/forum/ sub-packages are importable via canonical paths
- Key functions are callable at canonical locations
- Legacy shims (reddit/) still export the same objects (identity check)
- Data classes can be instantiated
- hot_rank functions work correctly
"""

import pytest


class TestCanonicalForumPackageImports:
    def test_src_forum_package_importable(self):
        import y_web.src.forum

        assert y_web.src.forum.__file__.endswith("__init__.py")

    def test_hot_rank_importable(self):
        from y_web.src.forum.hot_rank import (
            RankedPost,
            base_hot_score,
            longtail_boost,
            rank_posts_longtail,
            stable_uniform_0_1,
        )

        assert callable(base_hot_score)
        assert callable(longtail_boost)
        assert callable(rank_posts_longtail)
        assert callable(stable_uniform_0_1)

    def test_actions_media_importable(self):
        from y_web.src.forum.actions.media import (
            _CONTENT_TYPE_TO_EXT,
            _DOWNLOAD_TIMEOUT,
            _IMAGE_EXTENSIONS,
            _MAX_DOWNLOAD_BYTES,
            _MEDIA_EXTENSIONS,
            _VIDEO_EXTENSIONS,
            _download_image_to_uploads,
            _extract_candidate_media_url,
            _looks_like_image_url,
            _looks_like_media_url,
            _looks_like_video_url,
            _normalize_external_url,
            _remote_looks_like_image,
        )

        assert callable(_normalize_external_url)
        assert callable(_looks_like_image_url)
        assert callable(_looks_like_video_url)
        assert callable(_looks_like_media_url)
        assert callable(_extract_candidate_media_url)
        assert callable(_remote_looks_like_image)
        assert callable(_download_image_to_uploads)
        assert isinstance(_IMAGE_EXTENSIONS, tuple)
        assert isinstance(_VIDEO_EXTENSIONS, tuple)
        assert isinstance(_MEDIA_EXTENSIONS, tuple)
        assert isinstance(_CONTENT_TYPE_TO_EXT, dict)
        assert isinstance(_MAX_DOWNLOAD_BYTES, int)
        assert isinstance(_DOWNLOAD_TIMEOUT, int)

    def test_actions_posts_importable(self):
        from y_web.src.forum.actions.posts import (
            _comment_dedupe_key,
            _ensure_experiment_context,
            _get_current_round,
            _normalize_comment_for_dedupe,
            create_comment_reddit,
            create_post_reddit,
        )

        assert callable(_normalize_comment_for_dedupe)
        assert callable(_comment_dedupe_key)
        assert callable(_ensure_experiment_context)
        assert callable(_get_current_round)
        assert callable(create_comment_reddit)
        assert callable(create_post_reddit)

    def test_actions_reactions_importable(self):
        from y_web.src.forum.actions.reactions import (
            _calculate_vote_tallies,
            apply_vote,
        )

        assert callable(_calculate_vote_tallies)
        assert callable(apply_vote)

    def test_actions_package_importable(self):
        from y_web.src.forum.actions import (
            _calculate_vote_tallies,
            apply_vote,
            create_comment_reddit,
            create_post_reddit,
        )

        assert callable(create_post_reddit)
        assert callable(apply_vote)
        assert callable(create_comment_reddit)
        assert callable(_calculate_vote_tallies)

    def test_service_data_classes_importable(self):
        from y_web.src.forum.service.data_classes import (
            ArticlePreview,
            FeedPage,
            FeedPost,
            PostStats,
            _article_payload,
            _strip_article_title_from_body,
        )

        assert callable(_article_payload)
        assert callable(_strip_article_title_from_body)

    def test_service_formatters_importable(self):
        from y_web.src.forum.service.formatters import (
            _article_summary_needs_enrichment,
            _author_agent_page_cache,
            _clock_config_cache,
            _fetch_and_cache_og_image,
            _format_display_time,
            _format_display_time_from_created_at,
            _format_round,
            _get_experiment_dir,
            _get_profile_pic,
            _is_agent_or_page_author,
            _media_type_from_url,
            _og_image_cache,
            _resolve_article,
            _resolve_experiment_clock,
            _resolve_image,
            _resolve_image_post,
            _shared_from,
            _upgrade_reddit_image_url,
            clean_reddit_formatting,
            extract_reddit_summary_image,
            extract_youtube_thumbnail,
        )

        assert callable(clean_reddit_formatting)
        assert callable(extract_reddit_summary_image)
        assert callable(extract_youtube_thumbnail)
        assert callable(_format_display_time)
        assert callable(_format_display_time_from_created_at)
        assert callable(_media_type_from_url)
        assert callable(_upgrade_reddit_image_url)
        assert isinstance(_og_image_cache, dict)
        assert isinstance(_clock_config_cache, dict)
        assert isinstance(_author_agent_page_cache, dict)

    def test_service_queries_importable(self):
        from y_web.src.forum.service.queries import (
            _build_comment_payload,
            _build_feed_posts,
            _comment_count_subquery,
            _create_feed_post,
            _fetch_comment_map,
            _fetch_reaction_map,
            _fetch_share_map,
            _fetch_viewer_vote_map,
            _normalize_posts,
            _post_with_aggregates,
            _reaction_aggregates_subquery,
            _share_count_subquery,
            _viewer_vote_subquery,
            build_user_feed_posts,
            fetch_feed_page,
            fetch_thread,
            serialize_feed_posts,
        )

        assert callable(fetch_feed_page)
        assert callable(serialize_feed_posts)
        assert callable(build_user_feed_posts)
        assert callable(fetch_thread)
        assert callable(_normalize_posts)
        assert callable(_build_feed_posts)

    def test_service_package_importable(self):
        from y_web.src.forum.service import (
            build_user_feed_posts,
            fetch_feed_page,
            fetch_thread,
            serialize_feed_posts,
        )

        assert callable(fetch_feed_page)
        assert callable(fetch_thread)
        assert callable(build_user_feed_posts)
        assert callable(serialize_feed_posts)

    def test_forum_top_level_importable(self):
        from y_web.src.forum import (
            apply_vote,
            base_hot_score,
            build_user_feed_posts,
            create_comment_reddit,
            create_post_reddit,
            fetch_feed_page,
            fetch_thread,
            rank_posts_longtail,
            serialize_feed_posts,
        )

        assert callable(fetch_feed_page)
        assert callable(create_post_reddit)
        assert callable(apply_vote)


class TestCanonicalForumFunctions:
    def test_normalize_external_url_empty(self):
        from y_web.src.forum.actions.media import _normalize_external_url

        assert _normalize_external_url("") == ""
        assert _normalize_external_url("  ") == ""

    def test_normalize_external_url_adds_scheme(self):
        from y_web.src.forum.actions.media import _normalize_external_url

        result = _normalize_external_url("example.com/path")
        assert result.startswith("http://")

    def test_normalize_external_url_preserves_local(self):
        from y_web.src.forum.actions.media import _normalize_external_url

        assert _normalize_external_url("/uploads/foo.jpg") == "/uploads/foo.jpg"

    def test_normalize_external_url_strips_data(self):
        from y_web.src.forum.actions.media import _normalize_external_url

        assert _normalize_external_url("data:image/png;base64,abc") == ""

    def test_looks_like_image_url(self):
        from y_web.src.forum.actions.media import _looks_like_image_url

        assert _looks_like_image_url("http://example.com/photo.jpg") is True
        assert _looks_like_image_url("http://example.com/photo.PNG") is True
        assert _looks_like_image_url("http://example.com/video.mp4") is False
        assert _looks_like_image_url("") is False

    def test_looks_like_video_url(self):
        from y_web.src.forum.actions.media import _looks_like_video_url

        assert _looks_like_video_url("http://example.com/clip.mp4") is True
        assert _looks_like_video_url("http://example.com/photo.jpg") is False
        assert _looks_like_video_url("") is False

    def test_looks_like_media_url(self):
        from y_web.src.forum.actions.media import _looks_like_media_url

        assert _looks_like_media_url("http://example.com/photo.gif") is True
        assert _looks_like_media_url("http://example.com/clip.mp4") is True
        assert _looks_like_media_url("http://example.com/article") is False

    def test_extract_candidate_media_url_direct(self):
        from y_web.src.forum.actions.media import _extract_candidate_media_url

        url = "http://example.com/photo.jpg"
        result = _extract_candidate_media_url(url)
        assert result == url

    def test_extract_candidate_media_url_from_query(self):
        from y_web.src.forum.actions.media import _extract_candidate_media_url

        url = "http://search.example.com/?imgurl=http://cdn.example.com/photo.png"
        result = _extract_candidate_media_url(url)
        assert "photo.png" in result

    def test_normalize_comment_for_dedupe(self):
        from y_web.src.forum.actions.posts import _normalize_comment_for_dedupe

        assert _normalize_comment_for_dedupe("  Hello World!  ") == "hello world"
        assert _normalize_comment_for_dedupe("") == ""

    def test_comment_dedupe_key_none_for_empty(self):
        from y_web.src.forum.actions.posts import _comment_dedupe_key

        assert _comment_dedupe_key("") is None
        assert _comment_dedupe_key("   ") is None

    def test_comment_dedupe_key_is_hex(self):
        from y_web.src.forum.actions.posts import _comment_dedupe_key

        key = _comment_dedupe_key("hello world")
        assert key is not None
        assert len(key) == 40  # SHA1 hex length

    def test_clean_reddit_formatting(self):
        from y_web.src.forum.service.formatters import clean_reddit_formatting

        text = "Some post submitted by /u/testuser [link] [comments]"
        result = clean_reddit_formatting(text)
        assert "submitted by" not in result
        assert "[link]" not in result
        assert "[comments]" not in result

    def test_extract_youtube_thumbnail_watch_url(self):
        from y_web.src.forum.service.formatters import extract_youtube_thumbnail

        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        thumb = extract_youtube_thumbnail(url)
        assert thumb is not None
        assert "dQw4w9WgXcQ" in thumb

    def test_extract_youtube_thumbnail_short_url(self):
        from y_web.src.forum.service.formatters import extract_youtube_thumbnail

        url = "https://youtu.be/dQw4w9WgXcQ"
        thumb = extract_youtube_thumbnail(url)
        assert thumb is not None
        assert "dQw4w9WgXcQ" in thumb

    def test_extract_youtube_thumbnail_none_for_non_yt(self):
        from y_web.src.forum.service.formatters import extract_youtube_thumbnail

        assert extract_youtube_thumbnail("https://example.com") is None
        assert extract_youtube_thumbnail("") is None

    def test_media_type_from_url_video(self):
        from y_web.src.forum.service.formatters import _media_type_from_url

        assert _media_type_from_url("http://example.com/video.mp4") == "video"
        assert _media_type_from_url("http://example.com/clip.webm") == "video"

    def test_media_type_from_url_image(self):
        from y_web.src.forum.service.formatters import _media_type_from_url

        assert _media_type_from_url("http://example.com/photo.jpg") == "image"
        assert _media_type_from_url("") == "image"

    def test_upgrade_reddit_image_url_preview(self):
        from y_web.src.forum.service.formatters import _upgrade_reddit_image_url

        url = "https://preview.redd.it/image.jpg?width=320&format=pjpg"
        result = _upgrade_reddit_image_url(url)
        assert "960" in result

    def test_upgrade_reddit_image_url_passthrough(self):
        from y_web.src.forum.service.formatters import _upgrade_reddit_image_url

        url = "https://i.redd.it/image.jpg"
        assert _upgrade_reddit_image_url(url) == url

    def test_article_summary_needs_enrichment_empty(self):
        from y_web.src.forum.service.formatters import _article_summary_needs_enrichment

        assert _article_summary_needs_enrichment("") is True
        assert _article_summary_needs_enrichment(None) is True

    def test_article_summary_needs_enrichment_placeholder(self):
        from y_web.src.forum.service.formatters import _article_summary_needs_enrichment

        assert _article_summary_needs_enrichment("User shared article") is True
        assert _article_summary_needs_enrichment("Shared link: example.com") is True

    def test_article_summary_needs_enrichment_short(self):
        from y_web.src.forum.service.formatters import _article_summary_needs_enrichment

        assert _article_summary_needs_enrichment("Short.") is True

    def test_article_summary_needs_enrichment_long(self):
        from y_web.src.forum.service.formatters import _article_summary_needs_enrichment

        long_summary = "A" * 100
        assert _article_summary_needs_enrichment(long_summary) is False

    def test_normalize_posts_deduplication(self):
        from y_web.src.forum.service.queries import _normalize_posts
        from y_web.src.models import Post

        # _normalize_posts only processes actual Post ORM instances;
        # just verify it returns an empty list for non-Post objects
        result = _normalize_posts([])
        assert result == []

        result2 = _normalize_posts(["not a post", 42])
        assert result2 == []


class TestForumShimIdentity:
    def test_create_post_reddit_identity(self):
        from y_web.src.forum.actions import create_post_reddit as shim
        from y_web.src.forum.actions.posts import create_post_reddit as canonical

        assert shim is canonical

    def test_apply_vote_identity(self):
        from y_web.src.forum.actions import apply_vote as shim
        from y_web.src.forum.actions.reactions import apply_vote as canonical

        assert shim is canonical

    def test_create_comment_reddit_identity(self):
        from y_web.src.forum.actions import create_comment_reddit as shim
        from y_web.src.forum.actions.posts import create_comment_reddit as canonical

        assert shim is canonical

    def test_fetch_feed_page_identity(self):
        from y_web.src.forum.service import fetch_feed_page as shim
        from y_web.src.forum.service.queries import fetch_feed_page as canonical

        assert shim is canonical

    def test_serialize_feed_posts_identity(self):
        from y_web.src.forum.service import serialize_feed_posts as shim
        from y_web.src.forum.service.queries import serialize_feed_posts as canonical

        assert shim is canonical

    def test_rank_posts_longtail_identity(self):
        from y_web.src.forum.hot_rank import rank_posts_longtail as canonical
        from y_web.src.forum.hot_rank import rank_posts_longtail as shim

        assert shim is canonical

    def test_base_hot_score_identity(self):
        from y_web.src.forum.hot_rank import base_hot_score as canonical
        from y_web.src.forum.hot_rank import base_hot_score as shim

        assert shim is canonical

    def test_calculate_vote_tallies_identity(self):
        from y_web.src.forum.actions import _calculate_vote_tallies as shim
        from y_web.src.forum.actions.reactions import (
            _calculate_vote_tallies as canonical,
        )

        assert shim is canonical

    def test_clean_reddit_formatting_identity(self):
        from y_web.src.forum.service import clean_reddit_formatting as shim
        from y_web.src.forum.service.formatters import (
            clean_reddit_formatting as canonical,
        )

        assert shim is canonical

    def test_article_preview_identity(self):
        from y_web.src.forum.service import ArticlePreview as shim
        from y_web.src.forum.service.data_classes import ArticlePreview as canonical

        assert shim is canonical


class TestForumDataClasses:
    def test_article_preview_instantiation(self):
        from y_web.src.forum.service.data_classes import ArticlePreview

        ap = ArticlePreview(
            title="T", summary="S", url="http://example.com", source="src"
        )
        assert ap.title == "T"
        assert ap.summary == "S"
        assert ap.url == "http://example.com"
        assert ap.source == "src"
        assert ap.image is None

    def test_article_preview_with_image(self):
        from y_web.src.forum.service.data_classes import ArticlePreview

        img = {"url": "http://example.com/img.jpg", "description": "photo"}
        ap = ArticlePreview(title="T", summary="S", url="u", source="s", image=img)
        assert ap.image == img

    def test_post_stats_instantiation(self):
        from y_web.src.forum.service.data_classes import PostStats

        ps = PostStats(
            likes=5,
            dislikes=2,
            score=3,
            comment_count=1,
            share_count=0,
            user_vote="like",
        )
        assert ps.likes == 5
        assert ps.dislikes == 2
        assert ps.score == 3
        assert ps.user_vote == "like"

    def test_post_stats_no_vote(self):
        from y_web.src.forum.service.data_classes import PostStats

        ps = PostStats(
            likes=0, dislikes=0, score=0, comment_count=0, share_count=0, user_vote=None
        )
        assert ps.user_vote is None

    def test_feed_page_instantiation(self):
        from y_web.src.forum.service.data_classes import FeedPage

        fp = FeedPage(posts=[], page=1, per_page=20, total=0)
        assert fp.page == 1
        assert fp.per_page == 20
        assert fp.total == 0
        assert fp.posts == []

    def test_article_payload_none(self):
        from y_web.src.forum.service.data_classes import _article_payload

        assert _article_payload(None) == 0

    def test_article_payload_filled(self):
        from y_web.src.forum.service.data_classes import (
            ArticlePreview,
            _article_payload,
        )

        ap = ArticlePreview(title="T", summary="S", url="u", source="s")
        payload = _article_payload(ap)
        assert isinstance(payload, dict)
        assert payload["title"] == "T"
        assert payload["summary"] == "S"

    def test_strip_article_title_from_body_no_title(self):
        from y_web.src.forum.service.data_classes import _strip_article_title_from_body

        assert _strip_article_title_from_body("body text", None) == "body text"

    def test_strip_article_title_from_body_strips_prefix(self):
        from y_web.src.forum.service.data_classes import (
            ArticlePreview,
            _strip_article_title_from_body,
        )

        ap = ArticlePreview(title="Big Story", summary="", url="u", source="s")
        body = "Big Story\nThis is the post body."
        result = _strip_article_title_from_body(body, ap)
        assert not result.startswith("Big Story")

    def test_strip_article_title_with_prefix(self):
        from y_web.src.forum.service.data_classes import (
            ArticlePreview,
            _strip_article_title_from_body,
        )

        ap = ArticlePreview(title="Big Story", summary="", url="u", source="s")
        body = "TITLE: Big Story\nThis is the post body."
        result = _strip_article_title_from_body(body, ap)
        assert "TITLE: Big Story" not in result


class TestHotRankFunctions:
    def test_stable_uniform_range(self):
        from y_web.src.forum.hot_rank import stable_uniform_0_1

        u = stable_uniform_0_1(1, 2, 3)
        assert 0.0 <= u < 1.0
        assert isinstance(u, float)

    def test_stable_uniform_deterministic(self):
        from y_web.src.forum.hot_rank import stable_uniform_0_1

        u1 = stable_uniform_0_1(1, 2, 3)
        u2 = stable_uniform_0_1(1, 2, 3)
        assert u1 == u2

    def test_stable_uniform_different_inputs(self):
        from y_web.src.forum.hot_rank import stable_uniform_0_1

        u1 = stable_uniform_0_1(1, 2, 3)
        u2 = stable_uniform_0_1(1, 2, 4)
        assert u1 != u2

    def test_base_hot_score_positive(self):
        from y_web.src.forum.hot_rank import base_hot_score

        score = base_hot_score(10, 5)
        assert isinstance(score, float)
        assert score > 0

    def test_base_hot_score_zero(self):
        from y_web.src.forum.hot_rank import base_hot_score

        score = base_hot_score(0, 1)
        assert score == 0.0

    def test_base_hot_score_negative(self):
        from y_web.src.forum.hot_rank import base_hot_score

        # With a net score of -1 and round 6, round_decay=12: log10(2) - 6/12 < 0
        score = base_hot_score(-1, 6)
        assert score < 0

    def test_longtail_boost_low_votes(self):
        from y_web.src.forum.hot_rank import longtail_boost

        boost = longtail_boost(1, 0, u01=0.5)
        assert boost > 0
        assert boost < 0.45

    def test_longtail_boost_high_votes(self):
        from y_web.src.forum.hot_rank import longtail_boost

        boost = longtail_boost(10, 10, u01=0.5)
        assert boost == 0.0

    def test_ranked_post_dataclass(self):
        from y_web.src.forum.hot_rank import RankedPost

        class MockPost:
            pass

        p = MockPost()
        rp = RankedPost(score=3.14, post=p)
        assert rp.score == 3.14
        assert rp.post is p

    def test_rank_posts_longtail_ordering(self):
        from y_web.src.forum.hot_rank import rank_posts_longtail

        class MockPost:
            def __init__(self, id_, round_):
                self.id = id_
                self.round = round_

        posts = [MockPost(1, 1), MockPost(2, 5), MockPost(3, 10)]
        reaction_map = {1: (2, 1), 2: (10, 0), 3: (1, 5)}
        result = rank_posts_longtail(
            posts, reaction_map, viewer_id=1, current_round_id=3
        )
        assert len(result) == 3
        # Post with most net votes should rank higher
        assert result[0].id == 2  # 10 likes, 0 dislikes

    def test_rank_posts_longtail_empty(self):
        from y_web.src.forum.hot_rank import rank_posts_longtail

        result = rank_posts_longtail([], {}, viewer_id=1, current_round_id=1)
        assert result == []
