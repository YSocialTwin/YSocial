from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import aliased

from y_web import db
from y_web.src.content.text_utils import (
    augment_text,
    normalize_punctuation_spacing,
    process_reddit_post,
    strip_reproduced_article_content,
)
from y_web.src.data_access import get_elicited_emotions, get_topics
from y_web.src.experiment.context import get_current_experiment_id
from y_web.src.forum.hot_rank import rank_posts_longtail
from y_web.src.forum.service.data_classes import (
    ArticlePreview,
    FeedPage,
    FeedPost,
    PostStats,
    _article_payload,
    _strip_article_title_from_body,
)
from y_web.src.forum.service.formatters import (
    _article_summary_needs_enrichment,
    _format_display_time,
    _format_display_time_from_created_at,
    _format_round,
    _get_profile_pic,
    _is_agent_or_page_author,
    _resolve_article,
    _resolve_image,
    _resolve_image_post,
    _shared_from,
)
from y_web.src.models import (
    Articles,
    ImagePosts,
    Images,
    Interests,
    Post,
    Post_topics,
    Reactions,
    Rounds,
    User_mgmt,
    Websites,
)


def _normalize_sidebar_slug(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    raw = raw.replace("\\", "/")
    match = re.search(r"(?:^|/)r/([a-z0-9_]+)", raw)
    if match:
        return match.group(1)
    raw = raw.removeprefix("y/").removeprefix("r/").strip("/")
    raw = re.sub(r"[^a-z0-9_/-]+", "-", raw)
    raw = raw.strip("-_/")
    return raw.split("/")[0] if raw else ""


def _subreddit_slug_from_sources(*values: str) -> str:
    for value in values:
        slug = _normalize_sidebar_slug(value or "")
        if slug:
            return slug
    return ""


def _community_entry(slug: str, kind: str) -> Dict[str, str]:
    return {"slug": slug, "label": f"y/{slug}", "kind": kind}


def _build_root_post_community_map(
    root_ids: List[int],
) -> Dict[int, List[Dict[str, str]]]:
    normalized_root_ids = [int(root_id) for root_id in root_ids if root_id]
    if not normalized_root_ids:
        return {}

    root_rows = (
        db.session.query(
            Post.id.label("post_id"),
            Websites.rss.label("website_rss"),
            Articles.link.label("article_link"),
            func.lower(ImagePosts.subreddit).label("image_subreddit"),
        )
        .outerjoin(Articles, Articles.id == Post.news_id)
        .outerjoin(Websites, Websites.id == Articles.website_id)
        .outerjoin(ImagePosts, ImagePosts.id == Post.image_post_id)
        .filter(Post.id.in_(normalized_root_ids))
        .all()
    )
    topic_rows = (
        db.session.query(
            Post_topics.post_id.label("post_id"),
            func.lower(Interests.interest).label("topic_slug"),
        )
        .join(Interests, Interests.iid == Post_topics.topic_id)
        .filter(Post_topics.post_id.in_(normalized_root_ids))
        .order_by(Post_topics.post_id.asc(), Interests.interest.asc())
        .all()
    )

    topic_map: Dict[int, List[str]] = {}
    for row in topic_rows:
        slug = _normalize_sidebar_slug(row.topic_slug or "")
        if not slug:
            continue
        topic_map.setdefault(int(row.post_id), [])
        if slug not in topic_map[int(row.post_id)]:
            topic_map[int(row.post_id)].append(slug)

    root_map: Dict[int, List[Dict[str, str]]] = {}
    for row in root_rows:
        post_id = int(row.post_id)
        subreddit_slug = _subreddit_slug_from_sources(
            row.website_rss or "",
            row.article_link or "",
            row.image_subreddit or "",
        )
        if subreddit_slug:
            root_map[post_id] = [_community_entry(subreddit_slug, "subreddit")]
            continue
        root_map[post_id] = [
            _community_entry(topic_slug, "topic")
            for topic_slug in topic_map.get(post_id, [])
        ]

    return root_map


def _collect_ranked_communities_from_post_rows(
    post_rows: Iterable[Any], limit: int
) -> List[Dict[str, str]]:
    ordered_root_ids: List[int] = []
    seen_roots: set[int] = set()
    for row in post_rows:
        root_id = int(getattr(row, "thread_id", None) or getattr(row, "id", 0) or 0)
        if not root_id or root_id in seen_roots:
            continue
        seen_roots.add(root_id)
        ordered_root_ids.append(root_id)

    root_map = _build_root_post_community_map(ordered_root_ids)
    communities: List[Dict[str, str]] = []
    seen_slugs: set[str] = set()
    for root_id in ordered_root_ids:
        for community in root_map.get(root_id, []):
            slug = str(community.get("slug") or "").strip().lower()
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            communities.append(community)
            if len(communities) >= limit:
                return communities
    return communities


def _primary_community_payload(
    article: Optional[ArticlePreview],
    topics: List[Tuple[int, str, str]],
    image: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, str]]:
    subreddit_slug = _subreddit_slug_from_sources(
        getattr(article, "subreddit", "") if article else "",
        getattr(article, "url", "") if article else "",
        getattr(article, "source", "") if article else "",
        str((image or {}).get("subreddit") or ""),
    )
    if subreddit_slug:
        return _community_entry(subreddit_slug, "subreddit")

    for topic in topics or []:
        topic_name = ""
        if isinstance(topic, (list, tuple)) and len(topic) >= 2:
            topic_name = topic[1]
        elif isinstance(topic, str):
            topic_name = topic
        topic_slug = _normalize_sidebar_slug(topic_name)
        if topic_slug:
            return _community_entry(topic_slug, "topic")
    return None


def _apply_community_filter(base_query, community_slug: Optional[str]):
    slug = str(community_slug or "").strip().lower()
    if not slug:
        return base_query

    website_subquery = (
        db.session.query(Post.id)
        .join(Articles, Articles.id == Post.news_id)
        .join(Websites, Websites.id == Articles.website_id)
        .filter(
            or_(
                func.lower(Websites.rss).like(f"%/r/{slug}%"),
                func.lower(Articles.link).like(f"%/r/{slug}%"),
            )
        )
    )

    image_subquery = (
        db.session.query(Post.id)
        .join(ImagePosts, ImagePosts.id == Post.image_post_id)
        .filter(func.lower(ImagePosts.subreddit) == slug)
    )

    topic_subquery = (
        db.session.query(Post_topics.post_id)
        .join(Interests, Interests.iid == Post_topics.topic_id)
        .filter(func.lower(Interests.interest) == slug)
    )

    return base_query.filter(
        or_(
            Post.id.in_(website_subquery),
            Post.id.in_(image_subquery),
            Post.id.in_(topic_subquery),
        )
    )


def fetch_available_communities() -> List[Dict[str, str]]:
    subreddit_rows = (
        db.session.query(func.lower(Websites.rss).label("rss"))
        .join(Articles, Articles.website_id == Websites.id)
        .join(Post, Post.news_id == Articles.id)
        .filter(
            Post.comment_to == -1,
            Websites.rss.isnot(None),
            Websites.rss != "",
        )
        .distinct()
        .order_by(text("rss asc"))
        .all()
    )

    image_subreddit_rows = (
        db.session.query(func.lower(ImagePosts.subreddit).label("rss"))
        .join(Post, Post.image_post_id == ImagePosts.id)
        .filter(
            Post.comment_to == -1,
            ImagePosts.subreddit.isnot(None),
            ImagePosts.subreddit != "",
        )
        .distinct()
        .order_by(text("rss asc"))
        .all()
    )

    topic_rows = (
        db.session.query(func.lower(Interests.interest).label("slug"))
        .join(Post_topics, Post_topics.topic_id == Interests.iid)
        .join(Post, Post.id == Post_topics.post_id)
        .filter(
            Post.comment_to == -1,
            or_(Post.news_id.is_(None), Post.news_id.in_([-1, 0])),
            Interests.interest.isnot(None),
            Interests.interest != "",
        )
        .distinct()
        .order_by(text("slug asc"))
        .all()
    )

    communities: List[Dict[str, str]] = []
    seen: set[str] = set()

    for row in list(subreddit_rows) + list(image_subreddit_rows):
        rss_value = str(row.rss or "").strip().lower()
        slug = _subreddit_slug_from_sources(rss_value)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        communities.append({"slug": slug, "label": f"y/{slug}", "kind": "subreddit"})

    for row in topic_rows:
        slug = str(row.slug or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        communities.append({"slug": slug, "label": f"y/{slug}", "kind": "topic"})

    return communities


def fetch_recent_active_communities(limit: int = 8) -> List[Dict[str, str]]:
    recent_posts = (
        db.session.query(Post.id, Post.thread_id)
        .order_by(Post.id.desc())
        .limit(max(limit * 12, 96))
        .all()
    )
    return _collect_ranked_communities_from_post_rows(recent_posts, limit)


def fetch_user_communities(user_id: int, limit: int = 8) -> List[Dict[str, str]]:
    if not user_id:
        return []
    user_posts = (
        db.session.query(Post.id, Post.thread_id)
        .filter(Post.user_id == int(user_id))
        .order_by(Post.id.desc())
        .limit(max(limit * 12, 96))
        .all()
    )
    return _collect_ranked_communities_from_post_rows(user_posts, limit)


def _reaction_aggregates_subquery():
    return (
        db.session.query(
            Reactions.post_id.label("post_id"),
            func.sum(case((Reactions.type == "like", 1), else_=0)).label("like_count"),
            func.sum(case((Reactions.type == "dislike", 1), else_=0)).label(
                "dislike_count"
            ),
        )
        .group_by(Reactions.post_id)
        .subquery()
    )


def _comment_count_subquery():
    return (
        db.session.query(
            Post.thread_id.label("thread_id"),
            func.count(Post.id).label("comment_count"),
        )
        .filter(Post.comment_to != -1)
        .group_by(Post.thread_id)
        .subquery()
    )


def _share_count_subquery():
    return (
        db.session.query(
            Post.shared_from.label("post_id"),
            func.count(Post.id).label("share_count"),
        )
        .filter(Post.shared_from != -1)
        .group_by(Post.shared_from)
        .subquery()
    )


def _viewer_vote_subquery(viewer_id: int):
    # get latest reaction per post for viewer
    latest_ids = (
        db.session.query(
            func.max(Reactions.id).label("latest_id"),
            Reactions.post_id.label("post_id"),
        )
        .filter(Reactions.user_id == viewer_id)
        .group_by(Reactions.post_id)
        .subquery()
    )

    rv = aliased(Reactions)
    return (
        db.session.query(rv.post_id.label("post_id"), rv.type.label("vote_type"))
        .join(latest_ids, latest_ids.c.latest_id == rv.id)
        .subquery()
    )


def _fetch_reaction_map(post_ids: List[int]) -> Dict[int, Tuple[int, int]]:
    if not post_ids:
        return {}
    reaction_sub = _reaction_aggregates_subquery()
    rows = (
        db.session.query(
            reaction_sub.c.post_id,
            func.coalesce(reaction_sub.c.like_count, 0).label("likes"),
            func.coalesce(reaction_sub.c.dislike_count, 0).label("dislikes"),
        )
        .filter(reaction_sub.c.post_id.in_(post_ids))
        .all()
    )
    return {row.post_id: (int(row.likes), int(row.dislikes)) for row in rows}


def _fetch_comment_map(thread_ids: List[int]) -> Dict[int, int]:
    if not thread_ids:
        return {}
    comment_sub = _comment_count_subquery()
    rows = (
        db.session.query(
            comment_sub.c.thread_id,
            func.coalesce(comment_sub.c.comment_count, 0).label("comment_count"),
        )
        .filter(comment_sub.c.thread_id.in_(thread_ids))
        .all()
    )
    return {row.thread_id: int(row.comment_count) for row in rows}


def _fetch_share_map(post_ids: List[int]) -> Dict[int, int]:
    if not post_ids:
        return {}
    share_sub = _share_count_subquery()
    rows = (
        db.session.query(
            share_sub.c.post_id,
            func.coalesce(share_sub.c.share_count, 0).label("share_count"),
        )
        .filter(share_sub.c.post_id.in_(post_ids))
        .all()
    )
    return {row.post_id: int(row.share_count) for row in rows}


def _fetch_viewer_vote_map(viewer_id: int, post_ids: List[int]) -> Dict[int, str]:
    if not post_ids:
        return {}
    sub = _viewer_vote_subquery(viewer_id)
    rows = (
        db.session.query(sub.c.post_id, sub.c.vote_type)
        .filter(sub.c.post_id.in_(post_ids))
        .all()
    )
    return {row.post_id: row.vote_type for row in rows}


def _normalize_posts(posts: Iterable[Any]) -> List[Post]:
    """Convert pagination results into a unique list of Post entities preserving order.

    Deduplicates by both post ID and content signature (user_id, tweet hash, round)
    to catch duplicate posts that may have different IDs.
    """
    normalized: List[Post] = []
    seen_ids: set[int] = set()
    seen_content: set[tuple] = set()  # (user_id, tweet_hash, round)

    for entry in posts:
        post = entry
        if isinstance(entry, (list, tuple)) and entry:
            post = entry[0]
        if isinstance(post, Post):
            if post.id in seen_ids:
                continue
            # Also check content signature to catch duplicates with different IDs
            tweet_text = post.tweet[:500] if post.tweet else ""
            content_sig = (post.user_id, hash(tweet_text), post.round)
            if content_sig in seen_content:
                continue
            normalized.append(post)
            seen_ids.add(post.id)
            seen_content.add(content_sig)
    return normalized


def _build_comment_payload(
    post: Post, viewer_id: int
) -> Tuple[List[Dict[str, Any]], int]:
    comments_list = (
        db.session.query(Post)
        .filter(Post.thread_id == post.id, Post.id != post.id)
        .order_by(Post.id.asc())
        .all()
    )

    if not comments_list:
        return [], 0

    comment_ids = [comment.id for comment in comments_list]
    reaction_map = _fetch_reaction_map(comment_ids)
    share_map = _fetch_share_map(comment_ids)
    viewer_vote_map = _fetch_viewer_vote_map(viewer_id, comment_ids)

    comments = []

    for comment in comments_list:
        author = User_mgmt.query.filter_by(id=comment.user_id).first()
        profile_pic = _get_profile_pic(author) if author else ""

        title, body = process_reddit_post(
            comment.tweet, allow_legacy_blankline_title=False
        )
        if _is_agent_or_page_author(author):
            if title:
                title = normalize_punctuation_spacing(title)
            if body:
                body = normalize_punctuation_spacing(body)
        exp_id = get_current_experiment_id()
        processed_body = augment_text(body, exp_id) if body else ""

        emotions = get_elicited_emotions(comment.id)
        topics = get_topics(comment.id, comment.user_id)

        day, hour = _format_round(comment.round)
        comment_created_at = getattr(comment, "created_at", None)
        display_time = _format_display_time_from_created_at(
            comment_created_at
        ) or _format_display_time(day, hour)

        likes, dislikes = reaction_map.get(comment.id, (0, 0))
        viewer_vote = viewer_vote_map.get(comment.id)
        share_count = share_map.get(comment.id, 0)

        comments.append(
            {
                "post_id": comment.id,
                "profile_pic": profile_pic,
                "author": author.username if author else "",
                "author_id": comment.user_id,
                "post": processed_body,
                "title": title,
                "round": comment.round,
                "day": day,
                "hour": hour,
                "display_time": display_time,
                "created_at": (
                    comment_created_at.isoformat() if comment_created_at else None
                ),
                "likes": likes,
                "dislikes": dislikes,
                "is_liked": viewer_vote == "like",
                "is_disliked": viewer_vote == "dislike",
                "is_shared": share_count,
                "emotions": emotions,
                "topics": topics,
                "is_moderation_comment": bool(
                    int(getattr(comment, "is_moderation_comment", 0) or 0)
                ),
            }
        )

    return comments, len(comments)


def _create_feed_post(
    post: Post,
    viewer_id: int,
    reaction_map: Dict[int, Tuple[int, int]],
    comment_map: Dict[int, int],
    share_map: Dict[int, int],
    viewer_vote_map: Dict[int, str],
) -> FeedPost:
    author = User_mgmt.query.filter_by(id=post.user_id).first()
    author_username = author.username if author else ""
    author_is_page = bool(author.is_page) if author else False
    profile_pic = _get_profile_pic(author) if author else ""

    day, hour = _format_round(post.round)
    post_created_at = getattr(post, "created_at", None)
    display_time = _format_display_time_from_created_at(
        post_created_at
    ) or _format_display_time(day, hour)

    likes, dislikes = reaction_map.get(post.id, (0, 0))
    viewer_vote = viewer_vote_map.get(post.id)
    comment_count = comment_map.get(post.thread_id or post.id, 0)
    share_count = share_map.get(post.id, 0)

    title, body = process_reddit_post(post.tweet)

    article_row = (
        Articles.query.filter_by(id=post.news_id).first() if post.news_id else None
    )
    article_needs_enrichment = bool(
        article_row
        and _article_summary_needs_enrichment(getattr(article_row, "summary", None))
    )
    article = _resolve_article(article_row)

    # Strip article title from body if it appears at the beginning (avoids duplication)
    body = _strip_article_title_from_body(body, article)

    # Strip reproduced article content from body (catches LLM copying summary)
    if article and article.summary:
        body, _ = strip_reproduced_article_content(body, article.summary)

    if _is_agent_or_page_author(author):
        if title:
            title = normalize_punctuation_spacing(title)
        if body:
            body = normalize_punctuation_spacing(body)

    exp_id = get_current_experiment_id()
    processed_body = augment_text(body, exp_id) if body else ""

    image_row = (
        Images.query.filter_by(id=post.image_id).first()
        if getattr(post, "image_id", None)
        else None
    )
    image_needs_enrichment = bool(
        image_row and not (getattr(image_row, "description", "") or "").strip()
    )

    # Check image_post_id first (new standalone images), then fall back to image_id (old format)
    image = _resolve_image_post(getattr(post, "image_post_id", None)) or _resolve_image(
        post.image_id
    )
    if not image and article and article.image:
        image = article.image
    shared_from = _shared_from(post)

    emotions = get_elicited_emotions(post.id)
    topics = get_topics(post.id, post.user_id)
    primary_community = _primary_community_payload(article, topics, image)

    comments, _ = _build_comment_payload(post, viewer_id)

    stats = PostStats(
        likes=likes,
        dislikes=dislikes,
        score=likes - dislikes,
        comment_count=comment_count,
        share_count=share_count,
        user_vote=viewer_vote,
    )

    return FeedPost(
        id=post.id,
        thread_id=post.thread_id or post.id,
        author_id=post.user_id,
        author_username=author_username,
        author_is_page=author_is_page,
        author_profile_pic=profile_pic,
        title=title,
        body=processed_body,
        day=day,
        hour=hour,
        display_time=display_time,
        created_at=post_created_at.isoformat() if post_created_at else None,
        round_id=post.round,
        stats=stats,
        shared_from=shared_from,
        article_id=getattr(article_row, "id", None) if article_row else None,
        article_needs_enrichment=article_needs_enrichment,
        article=article,
        image_id=getattr(image_row, "id", None) if image_row else None,
        image_needs_enrichment=image_needs_enrichment,
        image=image,
        primary_community=primary_community,
        emotions=emotions,
        topics=topics,
        comments=comments,
        comment_total=comment_count,
        is_moderation_comment=bool(int(getattr(post, "is_moderation_comment", 0) or 0)),
    )


def _build_feed_posts(posts: Iterable[Any], viewer_id: int) -> List[FeedPost]:
    normalized_posts = _normalize_posts(posts)
    if not normalized_posts:
        return []

    post_ids = [post.id for post in normalized_posts]
    thread_ids = [post.thread_id or post.id for post in normalized_posts]

    reaction_map = _fetch_reaction_map(post_ids)
    comment_map = _fetch_comment_map(thread_ids)
    share_map = _fetch_share_map(post_ids)
    viewer_vote_map = _fetch_viewer_vote_map(viewer_id, post_ids)

    return [
        _create_feed_post(
            post,
            viewer_id=viewer_id,
            reaction_map=reaction_map,
            comment_map=comment_map,
            share_map=share_map,
            viewer_vote_map=viewer_vote_map,
        )
        for post in normalized_posts
    ]


def serialize_feed_posts(posts: Iterable[Any], viewer_id: int) -> List[Dict[str, Any]]:
    return [feed_post.to_dict() for feed_post in _build_feed_posts(posts, viewer_id)]


def build_user_feed_posts(
    viewer_id: int,
    target_user_id: int,
    recsys_type: str,
    page: int,
    per_page: int,
    feed_type: str = "new",
) -> Tuple[List[FeedPost], bool]:
    from y_web.src.recsys import get_suggested_posts

    sys.stderr.write(
        f"[DEBUG] build_user_feed_posts called with feed_type={feed_type}, target_user_id={target_user_id}\n"
    )
    sys.stderr.flush()

    recsys_posts, additional = get_suggested_posts(
        target_user_id, recsys_type, page, per_page
    )

    combined: List[Any] = []

    if recsys_posts is not None:
        combined.extend(recsys_posts.items)
    if additional is not None:
        combined.extend(additional.items)

    own_posts = (
        Post.query.filter(
            Post.user_id == target_user_id,
            Post.comment_to == -1,
        )
        .order_by(Post.id.desc())
        .limit(per_page)
        .all()
    )

    # Merge own posts with recommended posts, maintaining chronological order
    combined.extend(own_posts)

    normalized = _normalize_posts(combined)

    # Apply sorting based on feed_type
    if feed_type == "top":
        # Sort by score (likes - dislikes) descending
        reaction_map = _fetch_reaction_map([p.id for p in normalized])
        normalized.sort(
            key=lambda p: (
                reaction_map.get(p.id, (0, 0))[0] - reaction_map.get(p.id, (0, 0))[1],
                p.id,
            ),
            reverse=True,
        )
    elif feed_type == "most_commented":
        # Sort by comment count descending
        thread_ids = [p.thread_id or p.id for p in normalized]
        comment_map = _fetch_comment_map(thread_ids)
        normalized.sort(
            key=lambda p: (comment_map.get(p.thread_id or p.id, 0), p.id), reverse=True
        )
    else:
        # Default: Sort by post ID descending (newest first)
        normalized.sort(key=lambda p: p.id, reverse=True)

    total_posts = len(normalized)
    start_idx = max((page - 1) * per_page, 0)
    end_idx = start_idx + per_page

    if start_idx >= total_posts:
        return [], False

    page_posts = normalized[start_idx:end_idx]
    has_more = end_idx < total_posts

    feed_posts = _build_feed_posts(page_posts, viewer_id)
    return feed_posts, has_more


def fetch_feed_page(
    *,
    viewer_id: int,
    page: int,
    per_page: int,
    feed_user_id: Optional[int] = None,
    feed_type: str = "new",
    search_query: str = "",
    exclude_user_ids: Optional[List[int]] = None,
    community_slug: Optional[str] = None,
) -> FeedPage:
    sys.stderr.write(
        f"[DEBUG] fetch_feed_page called with feed_type={feed_type}, page={page}, per_page={per_page}\n"
    )
    sys.stderr.flush()
    base_query = db.session.query(Post).filter(Post.comment_to == -1).options()
    base_query = _apply_community_filter(base_query, community_slug)

    if feed_user_id is not None:
        base_query = base_query.filter(Post.user_id == feed_user_id)
    if exclude_user_ids:
        base_query = base_query.filter(Post.user_id.notin_(exclude_user_ids))
    if search_query:
        like_pattern = f"%{search_query.strip()}%"
        if like_pattern != "%%":
            base_query = (
                base_query.outerjoin(User_mgmt, User_mgmt.id == Post.user_id)
                .outerjoin(Articles, Articles.id == Post.news_id)
                .filter(
                    or_(
                        Post.tweet.ilike(like_pattern),
                        User_mgmt.username.ilike(like_pattern),
                        Articles.title.ilike(like_pattern),
                        Articles.summary.ilike(like_pattern),
                    )
                )
            )

    total = int(base_query.count())

    if feed_type == "top":
        reaction_sub = _reaction_aggregates_subquery()
        score_expr = func.coalesce(reaction_sub.c.like_count, 0) - func.coalesce(
            reaction_sub.c.dislike_count, 0
        )
        base_query = base_query.outerjoin(
            reaction_sub, reaction_sub.c.post_id == Post.id
        ).order_by(score_expr.desc(), Post.id.desc())
    elif feed_type == "hot":
        # Reddit-style hot with logarithmic scoring
        # Base formula: log10(|score| + 1) + sign(score) * round / round_decay
        # Every round_decay rounds, a post needs ~10x more votes to maintain position
        round_decay = 12.0
        reaction_sub = _reaction_aggregates_subquery()

        # Net score
        net_score = func.coalesce(reaction_sub.c.like_count, 0) - func.coalesce(
            reaction_sub.c.dislike_count, 0
        )

        # Sign of score: 1 if positive, -1 if negative, 0 if zero
        sign_expr = case((net_score > 0, 1), (net_score < 0, -1), else_=0)

        # Logarithmic order: log10(abs(score) + 1)
        abs_score = func.abs(net_score)
        log_order = func.log(abs_score + 1) / func.log(10.0)

        # Hot score: logarithmic order + sign * time_boost
        hot_score = log_order + sign_expr * (Post.round / round_decay)

        longtail_enabled = os.getenv(
            "YSOCIAL_FORUM_HOT_LONGTAIL", "1"
        ).strip().lower() not in {
            "0",
            "false",
            "off",
            "",
        }

        desired_end = page * per_page
        max_candidates = 2000

        # Windowed rerank for shallow pages only; fall back for deep scroll.
        if longtail_enabled and desired_end <= max_candidates:
            oversample = 5
            min_candidates = 200
            limit = min(
                max_candidates,
                max(min_candidates, int(desired_end * oversample), int(desired_end)),
            )

            candidates = (
                base_query.outerjoin(reaction_sub, reaction_sub.c.post_id == Post.id)
                .order_by(hot_score.desc(), Post.id.desc())
                .limit(limit)
                .all()
            )

            start_idx = max((page - 1) * per_page, 0)
            end_idx = start_idx + per_page

            if not candidates or start_idx >= total:
                return FeedPage(posts=[], page=page, per_page=per_page, total=total)

            post_ids = [p.id for p in candidates]
            reaction_map = _fetch_reaction_map(post_ids)
            current_round_id = db.session.query(func.max(Rounds.id)).scalar() or 0

            ranked = rank_posts_longtail(
                candidates,
                reaction_map,
                viewer_id=viewer_id,
                current_round_id=int(current_round_id),
                round_decay=round_decay,
            )

            page_posts = ranked[start_idx:end_idx]
            return FeedPage(
                posts=_build_feed_posts(page_posts, viewer_id),
                page=page,
                per_page=per_page,
                total=total,
            )

        base_query = base_query.outerjoin(
            reaction_sub, reaction_sub.c.post_id == Post.id
        ).order_by(hot_score.desc(), Post.id.desc())
    elif feed_type == "most_commented":
        comment_sub = _comment_count_subquery()
        comment_expr = func.coalesce(comment_sub.c.comment_count, 0)
        base_query = base_query.outerjoin(
            comment_sub, comment_sub.c.thread_id == Post.id
        ).order_by(comment_expr.desc(), Post.id.desc())
    else:
        base_query = base_query.order_by(Post.id.desc())

    pagination = base_query.paginate(page=page, per_page=per_page, error_out=False)

    sys.stderr.write(
        f"[DEBUG] Found {len(pagination.items)} posts out of {pagination.total} total, feed_type={feed_type}\n"
    )
    if pagination.items:
        post_ids = [
            (
                item.id
                if isinstance(item, Post)
                else item[0].id if isinstance(item, tuple) else str(item)
            )
            for item in pagination.items[:10]
        ]
        sys.stderr.write(f"[DEBUG] First 10 post IDs returned: {post_ids}\n")
    sys.stderr.flush()

    return FeedPage(
        posts=_build_feed_posts(pagination.items, viewer_id),
        page=pagination.page,
        per_page=pagination.per_page,
        total=total if feed_type == "hot" else pagination.total,
    )


def _post_with_aggregates(
    post: Post,
    reaction_map: Dict[int, Tuple[int, int]],
    share_map: Dict[int, int],
    viewer_vote_map: Dict[int, str],
) -> Dict[str, Any]:
    likes, dislikes = reaction_map.get(post.id, (0, 0))
    viewer_vote = viewer_vote_map.get(post.id)
    author = User_mgmt.query.filter_by(id=post.user_id).first()
    profile_pic = _get_profile_pic(author) if author else ""
    day, hour = _format_round(post.round)
    post_created_at = getattr(post, "created_at", None)
    display_time = _format_display_time_from_created_at(
        post_created_at
    ) or _format_display_time(day, hour)

    title, body = process_reddit_post(post.tweet)
    article_row = (
        Articles.query.filter_by(id=post.news_id).first() if post.news_id else None
    )
    article_needs_enrichment = bool(
        article_row
        and _article_summary_needs_enrichment(getattr(article_row, "summary", None))
    )
    article = _resolve_article(article_row)

    # Strip article title from body if it appears at the beginning (avoids duplication)
    body = _strip_article_title_from_body(body, article)

    # Strip reproduced article content from body (catches LLM copying summary)
    if article and article.summary:
        body, _ = strip_reproduced_article_content(body, article.summary)

    if post.comment_to == -1 and _is_agent_or_page_author(author):
        if title:
            title = normalize_punctuation_spacing(title)
        if body:
            body = normalize_punctuation_spacing(body)

    exp_id = get_current_experiment_id()
    processed_body = augment_text(body, exp_id) if body else ""

    image_row = (
        Images.query.filter_by(id=post.image_id).first()
        if getattr(post, "image_id", None)
        else None
    )
    image_needs_enrichment = bool(
        image_row and not (getattr(image_row, "description", "") or "").strip()
    )

    # Check image_post_id first (new standalone images), then fall back to image_id (old format)
    image_obj = _resolve_image_post(
        getattr(post, "image_post_id", None)
    ) or _resolve_image(post.image_id)
    if not image_obj and article and article.image:
        image_obj = article.image

    return {
        "title": title,
        "post": processed_body,
        "profile_pic": profile_pic,
        "image": image_obj,
        "shared_from": _shared_from(post),
        "post_id": post.id,
        "author": author.username if author else "",
        "author_id": post.user_id,
        "day": day,
        "hour": hour,
        "display_time": display_time,
        "created_at": post_created_at.isoformat() if post_created_at else None,
        "article_id": getattr(article_row, "id", None) if article_row else None,
        "article_needs_enrichment": bool(article_needs_enrichment),
        "article": _article_payload(article),
        "image_id": getattr(image_row, "id", None) if image_row else None,
        "image_needs_enrichment": bool(image_needs_enrichment),
        "likes": likes,
        "dislikes": dislikes,
        "score": likes - dislikes,
        "is_liked": viewer_vote == "like",
        "is_disliked": viewer_vote == "dislike",
        "is_shared": share_map.get(post.id, 0),
        "emotions": get_elicited_emotions(post.id),
        "topics": get_topics(post.id, post.user_id),
    }


def fetch_thread(post_id: int, viewer_id: int) -> Dict[str, Any]:
    post = Post.query.filter_by(id=post_id).first()
    if not post:
        raise ValueError(f"Post {post_id} not found")

    thread_posts = (
        Post.query.filter_by(thread_id=post.thread_id or post.id)
        .order_by(Post.id.asc())
        .all()
    )

    post_ids = [tp.id for tp in thread_posts]
    reaction_map = _fetch_reaction_map(post_ids)
    share_map = _fetch_share_map(post_ids)
    viewer_vote_map = _fetch_viewer_vote_map(viewer_id, post_ids)

    reverse_map: Dict[int, Optional[int]] = {}
    post_children: Dict[int, List[int]] = {}
    post_payloads: Dict[int, Dict[str, Any]] = {}

    for idx, thread_post in enumerate(thread_posts):
        payload = _post_with_aggregates(
            thread_post,
            reaction_map=reaction_map,
            share_map=share_map,
            viewer_vote_map=viewer_vote_map,
        )
        payload["children"] = []

        post_payloads[thread_post.id] = payload
        parent_id = thread_post.comment_to if thread_post.comment_to != -1 else None

        if thread_post.id not in post_children:
            post_children[thread_post.id] = []

        if parent_id is not None:
            post_children.setdefault(parent_id, []).append(thread_post.id)

    root_id = thread_posts[0].id if thread_posts else post_id

    def attach_children(node_id: int):
        payload = post_payloads[node_id]
        for child_id in post_children.get(node_id, []):
            attach_children(child_id)
            payload["children"].append(post_payloads[child_id])

    attach_children(root_id)
    return post_payloads[root_id]
