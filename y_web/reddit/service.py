from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from sqlalchemy import case, func, or_, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import aliased

from y_web import db
from y_web.data_access import get_elicited_emotions, get_topics
from y_web.experiment_context import get_current_experiment_id
from y_web.models import (
    Admin_users,
    Agent,
    Articles,
    Exps,
    Images,
    Page,
    Post,
    Reactions,
    Rounds,
    User_mgmt,
    Websites,
)
from y_web.reddit.hot_rank import rank_posts_longtail
from y_web.utils.experiment_clock import (
    DEFAULT_CLOCK_MODE,
    DEFAULT_CLOCK_TIMEZONE,
    default_clock_config,
    ensure_experiment_clock,
    parse_anchor_date,
)
from y_web.utils.text_utils import (
    augment_text,
    normalize_punctuation_spacing,
    process_reddit_post,
    strip_reproduced_article_content,
    strip_tags,
)

_Y_WEB_DIR = Path(__file__).resolve().parents[1]


def _get_experiment_dir(experiment: Exps) -> Path:
    """Locate the on-disk directory that stores experiment artifacts."""
    db_name = str(getattr(experiment, "db_name", "") or "").replace("\\", os.sep)
    if os.sep in db_name:
        return _Y_WEB_DIR / Path(db_name).parent
    folder = db_name.removeprefix("experiments_")
    return _Y_WEB_DIR / "experiments" / folder


def clean_reddit_formatting(text: str) -> str:
    """Remove Reddit-specific formatting artifacts from text."""
    if not text:
        return ""
    normalized = html.unescape(text)
    # Remove "submitted by /u/username" patterns (tolerate extra spaces)
    normalized = re.sub(
        r"\bsubmitted\s+by\s+/?u/[A-Za-z0-9_-]+\b", "", normalized, flags=re.IGNORECASE
    )
    # Remove [link] [comments] patterns
    normalized = re.sub(r"\[link\]|\[comments\]", "", normalized, flags=re.IGNORECASE)
    # Clean up extra whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def extract_reddit_summary_image(summary_html: str) -> Optional[Dict[str, str]]:
    """Extract a preview image from Reddit summary HTML (no network)."""
    if not summary_html:
        return None
    try:
        soup = BeautifulSoup(summary_html, "html.parser")
        img = soup.find("img")
        if not img:
            return None
        src = img.get("src", "")
        if not src or src.startswith("data:"):
            return None
        src = html.unescape(src)
        src = _upgrade_reddit_image_url(src)
        if not src:
            return None
        alt = img.get("alt", "") or ""
        return {"url": src, "description": alt}
    except Exception:
        return None


def extract_youtube_thumbnail(url: str) -> Optional[str]:
    """Extract YouTube thumbnail URL from a YouTube link."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        video_id = None

        if "youtu.be" in host:
            video_id = path.strip("/").split("/")[0] if path else None
        elif "youtube.com" in host or "youtube-nocookie.com" in host:
            if path.startswith("/watch"):
                qs = parse_qs(parsed.query)
                video_id = (qs.get("v") or [None])[0]
            elif path.startswith("/embed/"):
                video_id = path.split("/embed/")[1].split("/")[0]
            elif path.startswith("/shorts/"):
                video_id = path.split("/shorts/")[1].split("/")[0]
            elif path.startswith("/live/"):
                video_id = path.split("/live/")[1].split("/")[0]
            elif path.startswith("/v/"):
                video_id = path.split("/v/")[1].split("/")[0]

        if not video_id:
            return None
        return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    except Exception:
        return None


# In-memory cache for OG image lookups to avoid repeated network requests
# Maps article_id -> Optional[Dict] (None means "already tried, no image found")
_og_image_cache: Dict[int, Optional[Dict[str, str]]] = {}
_clock_config_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
_author_agent_page_cache: Dict[str, bool] = {}


def _fetch_and_cache_og_image(article) -> Optional[Dict[str, str]]:
    """Fetch OG image from article URL, cache in DB and memory."""
    if article.id in _og_image_cache:
        return _og_image_cache[article.id]

    image = None
    try:
        import requests

        from y_web.utils.article_extractor import extract_image

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(article.link, headers=headers, timeout=5)
        if resp.ok:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_img = extract_image(soup, article.link)
            if og_img:
                image = {"url": og_img, "description": ""}
                # Cache in DB for future lookups (persists across restarts)
                try:
                    existing = Images.query.filter_by(article_id=article.id).first()
                    if not existing:
                        img_record = Images(url=og_img, article_id=article.id)
                        db.session.add(img_record)
                        db.session.commit()
                except Exception:
                    db.session.rollback()
    except Exception:
        pass

    _og_image_cache[article.id] = image
    return image


@dataclass
class ArticlePreview:
    title: str
    summary: str
    url: str
    source: str
    image: Optional[Dict[str, str]] = None  # {"url": ..., "description": ...}


def _article_payload(article: Optional[ArticlePreview]) -> Any:
    if not article:
        return 0
    return {
        "title": article.title,
        "summary": article.summary,
        "url": article.url,
        "source": article.source,
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
            "emotions": self.emotions,
            "topics": self.topics,
        }


@dataclass
class FeedPage:
    posts: List[FeedPost]
    page: int
    per_page: int
    total: int


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


def _get_profile_pic(user: User_mgmt) -> str:
    from y_web.utils.avatars import deterministic_forum_avatar_url

    return deterministic_forum_avatar_url(user.username)


def _is_agent_or_page_author(user: Optional[User_mgmt]) -> bool:
    if user is None:
        return False
    if bool(getattr(user, "is_page", False)):
        return True

    username = (getattr(user, "username", "") or "").strip()
    if not username:
        return False
    if username in _author_agent_page_cache:
        return _author_agent_page_cache[username]

    is_agent = Agent.query.filter_by(name=username).first() is not None
    is_page = Page.query.filter_by(name=username).first() is not None
    result = bool(is_agent or is_page)
    _author_agent_page_cache[username] = result
    return result


def _format_round(round_id: Optional[int]) -> Tuple[str, str]:
    if round_id is None:
        return "None", "00"
    round_obj = Rounds.query.filter_by(id=round_id).first()
    if not round_obj:
        return "None", "00"
    return str(round_obj.day), f"{round_obj.hour:02d}"


def _resolve_experiment_clock() -> Dict[str, Any]:
    """
    Load experiment clock settings from config_server.json with a lightweight mtime cache.
    """
    try:
        exp_id_raw = get_current_experiment_id()
    except Exception:
        return default_clock_config()

    if exp_id_raw is None:
        return default_clock_config()

    try:
        exp_id = int(exp_id_raw)
    except (TypeError, ValueError):
        return default_clock_config()

    try:
        experiment = Exps.query.filter_by(idexp=exp_id).first()
        if not experiment:
            return default_clock_config()

        config_path = _get_experiment_dir(experiment) / "config_server.json"
        mtime = config_path.stat().st_mtime if config_path.exists() else -1.0
        cached = _clock_config_cache.get(exp_id)
        if cached and cached[0] == mtime:
            return cached[1]

        resolved_clock = default_clock_config()
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            resolved_clock = ensure_experiment_clock(payload)

        _clock_config_cache[exp_id] = (mtime, resolved_clock)
        return resolved_clock
    except Exception:
        return default_clock_config()


def _format_display_time(day: str, hour: str) -> str:
    """
    Return a calendar timestamp label for feed items.

    Simulation day/hour is mapped onto the experiment anchor date in the configured timezone.
    """
    clock = _resolve_experiment_clock()
    timezone_name = str(
        clock.get("timezone", DEFAULT_CLOCK_TIMEZONE) or DEFAULT_CLOCK_TIMEZONE
    )

    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        try:
            tz = ZoneInfo(DEFAULT_CLOCK_TIMEZONE)
        except Exception:
            return datetime.now().strftime("%d-%m-%y %H:%M")

    fallback = datetime.now(tz).strftime("%d-%m-%y %H:%M")
    if day == "None":
        return fallback

    try:
        day_num = int(day)
        hour_num = int(hour)
    except (TypeError, ValueError):
        return fallback

    anchor_date = parse_anchor_date(clock.get("anchor_date"))
    if anchor_date is None:
        anchor_date = datetime.now(tz).date()

    try:
        day_offset = max(day_num, 0)
        normalized_hour = min(max(hour_num, 0), 23)
        dt = datetime.combine(
            anchor_date + timedelta(days=day_offset),
            time(hour=normalized_hour, minute=0),
            tzinfo=tz,
        )
    except Exception:
        return fallback

    return dt.strftime("%d-%m-%y %H:%M")


def _format_display_time_from_created_at(
    created_at: Optional[datetime],
) -> Optional[str]:
    """
    Format a persisted post/comment timestamp as calendar datetime.
    """
    if created_at is None:
        return None

    clock = _resolve_experiment_clock()
    timezone_name = str(
        clock.get("timezone", DEFAULT_CLOCK_TIMEZONE) or DEFAULT_CLOCK_TIMEZONE
    )

    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = None

    dt = created_at
    if tz is not None:
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            else:
                dt = dt.astimezone(tz)
        except Exception:
            pass

    return dt.strftime("%d-%m-%y %H:%M")


def _resolve_article(article: Optional[Articles]) -> Optional[ArticlePreview]:
    if article is None:
        return None
    website = Websites.query.filter_by(id=article.website_id).first()
    source = website.name if website else ""

    # Fetch image associated with this article
    image = None
    try:
        img = Images.query.filter_by(article_id=article.id).first()
        if img and img.url:
            image = {
                "url": img.url,
                "description": getattr(img, "description", "") or "",
            }
    except OperationalError:
        # Handle schema mismatch for older databases
        try:
            row = db.session.execute(
                text(
                    "SELECT url, description FROM images WHERE article_id = :article_id LIMIT 1"
                ),
                {"article_id": article.id},
            ).fetchone()
            if row and row[0]:
                image = {"url": row[0], "description": row[1] or ""}
        except Exception:
            pass

    summary = strip_tags(article.summary) if article.summary else ""
    summary = clean_reddit_formatting(summary)

    if not image and article.summary:
        image = extract_reddit_summary_image(article.summary)

    if not image:
        yt_thumb = extract_youtube_thumbnail(article.link)
        if yt_thumb:
            image = {"url": yt_thumb, "description": ""}

    # Fallback: fetch OG image from the article URL and cache it in the DB
    if not image and article.link:
        image = _fetch_and_cache_og_image(article)

    return ArticlePreview(
        title=strip_tags(article.title) if article.title else "",
        summary=summary,
        url=article.link,
        source=source,
        image=image,
    )


def _article_summary_needs_enrichment(summary: Optional[str]) -> bool:
    """
    Heuristic for deciding whether a link's summary should be upgraded by an LLM.

    We store a fast metadata-derived summary on share; if it is empty or looks like
    a generic placeholder, we can request an on-demand LLM summary.
    """
    s = (summary or "").strip()
    if not s:
        return True
    lowered = s.lower()
    if lowered == "user shared article":
        return True
    if lowered.startswith("shared link:"):
        return True
    # Very short summaries are usually meta tag stubs or placeholders.
    return len(s) < 60


def _resolve_image(image_id: Optional[int]) -> Optional[str]:
    if not image_id:
        return ""
    try:
        image = Images.query.filter_by(id=image_id).first()
    except OperationalError as exc:
        message = str(exc).lower()
        if "no such column" in message and "remote_article_id" in message:
            row = db.session.execute(
                text("SELECT url FROM images WHERE id = :image_id LIMIT 1"),
                {"image_id": image_id},
            ).fetchone()
            if row and row[0]:
                return {
                    "url": row[0],
                    "description": "",
                    "media_type": _media_type_from_url(row[0]),
                }
            return ""
        raise
    if not image:
        return ""
    url = getattr(image, "url", None)
    description = getattr(image, "description", "") or ""
    if not url:
        return ""
    return {
        "url": url,
        "description": description,
        "media_type": _media_type_from_url(url),
    }


def _media_type_from_url(url: str) -> str:
    if not url:
        return "image"
    lowered = url.split("?", 1)[0].split("#", 1)[0].lower()
    if (
        lowered.endswith(".mp4")
        or lowered.endswith(".webm")
        or lowered.endswith(".ogg")
        or lowered.endswith(".gifv")
    ):
        return "video"
    return "image"


def _upgrade_reddit_image_url(url: str) -> str:
    """Transform Reddit thumbnail URL to larger preview URL if possible."""
    if not url:
        return url

    # preview.redd.it / external-preview.redd.it URLs can have size params for larger images
    if "preview.redd.it" in url or "external-preview.redd.it" in url:
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if "width" in query:
            query["width"] = ["960"]
        else:
            query["width"] = ["960"]
        query.setdefault("format", ["pjpg"])
        query.setdefault("auto", ["webp"])
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    # i.redd.it URLs are already full size
    return url


def _resolve_image_post(image_post_id: Optional[int]) -> Optional[Dict[str, str]]:
    """Resolve image from image_posts table (standalone images shared by agents)."""
    if not image_post_id:
        return None
    try:
        # Use the current experiment's database bind
        from y_web.experiment_context import get_current_experiment_bind

        bind_key = get_current_experiment_bind()
        engine = db.get_engine(bind=bind_key)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT url, description, local_path FROM image_posts WHERE id = :id LIMIT 1"
                ),
                {"id": image_post_id},
            ).fetchone()
            if row and row[0]:
                # Prefer local path if available
                if row[2]:  # local_path exists
                    url = f"/static/{row[2]}"
                else:
                    url = _upgrade_reddit_image_url(row[0])
                return {
                    "url": url,
                    "description": row[1] or "",
                    "media_type": _media_type_from_url(url),
                }
    except Exception:
        pass
    return None


def _shared_from(post: Post) -> Optional[Tuple[int, str]]:
    if post.shared_from == -1:
        return -1
    author = (
        db.session.query(User_mgmt.username)
        .join(Post, User_mgmt.id == Post.user_id)
        .filter(Post.id == post.shared_from)
        .scalar()
    )
    return (post.shared_from, author) if author else -1


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
            }
        )

    return comments, len(comments)


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
        emotions=emotions,
        topics=topics,
        comments=comments,
        comment_total=comment_count,
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
    from y_web.recsys_support import get_suggested_posts

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
) -> FeedPage:
    sys.stderr.write(
        f"[DEBUG] fetch_feed_page called with feed_type={feed_type}, page={page}, per_page={per_page}\n"
    )
    sys.stderr.flush()
    base_query = db.session.query(Post).filter(Post.comment_to == -1).options()

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
