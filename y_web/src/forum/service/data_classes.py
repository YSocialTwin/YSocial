from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ArticlePreview:
    title: str
    summary: str
    url: str
    source: str
    subreddit: str = ""
    image: Optional[Dict[str, str]] = None  # {"url": ..., "description": ...}


def _article_payload(article: Optional[ArticlePreview]) -> Any:
    if not article:
        return 0
    return {
        "title": article.title,
        "summary": article.summary,
        "url": article.url,
        "source": article.source,
        "subreddit": article.subreddit,
        "image": article.image,
    }


def _strip_article_title_from_body(body: str, article: Optional[ArticlePreview]) -> str:
    """
    Strip the article title from the post body if it appears at the beginning.

    This handles cases where the LLM includes the article title in its response
    without a proper newline separator, causing the title to appear in the body
    even though it's already shown in the article preview card.
    """
    if not body or not article or not article.title:
        return body

    # Check if body starts with the article title (possibly with "TITLE: " prefix)
    article_title = article.title.strip()
    body_stripped = body.strip()

    # Try matching with "TITLE: " prefix first
    if body_stripped.startswith(f"TITLE: {article_title}"):
        body_stripped = body_stripped[len(f"TITLE: {article_title}") :].lstrip()
    # Also try matching without the prefix (in case it was already partially stripped)
    elif body_stripped.startswith(article_title):
        body_stripped = body_stripped[len(article_title) :].lstrip()

    return body_stripped


@dataclass
class PostStats:
    likes: int
    dislikes: int
    score: int
    comment_count: int
    share_count: int
    user_vote: Optional[str]


@dataclass
class FeedPost:
    id: int
    thread_id: int
    author_id: int
    author_username: str
    author_is_page: bool
    author_profile_pic: str
    title: Optional[str]
    body: str
    day: str
    hour: str
    display_time: str
    created_at: Optional[str]
    round_id: Optional[int]
    stats: PostStats
    shared_from: Optional[Tuple[int, str]]
    article_id: Optional[int]
    article_needs_enrichment: bool
    article: Optional[ArticlePreview]
    image_id: Optional[int]
    image_needs_enrichment: bool
    image: Any
    primary_community: Optional[Dict[str, str]]
    emotions: List[Tuple[str, str, int]]
    topics: List[Tuple[int, str, str]]
    comments: List[Dict[str, Any]]
    comment_total: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.id,
            "thread_id": self.thread_id,
            "author": self.author_username,
            "author_id": self.author_id,
            "profile_pic": self.author_profile_pic,
            "shared_from": self.shared_from,
            "post": self.body,
            "title": self.title,
            "round": self.round_id,
            "day": self.day,
            "hour": self.hour,
            "display_time": self.display_time,
            "created_at": self.created_at,
            "likes": self.stats.likes,
            "dislikes": self.stats.dislikes,
            "is_liked": self.stats.user_vote == "like",
            "is_disliked": self.stats.user_vote == "dislike",
            "is_shared": self.stats.share_count,
            "t_comments": self.comment_total,
            "comments": self.comments,
            "article_id": self.article_id,
            "article_needs_enrichment": bool(self.article_needs_enrichment),
            "article": _article_payload(self.article),
            "image_id": self.image_id,
            "image_needs_enrichment": bool(self.image_needs_enrichment),
            "image": self.image,
            "primary_community": self.primary_community or None,
            "emotions": self.emotions,
            "topics": self.topics,
        }


@dataclass
class FeedPage:
    posts: List[FeedPost]
    page: int
    per_page: int
    total: int
