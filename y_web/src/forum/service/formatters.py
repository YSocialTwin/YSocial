from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from y_web import db
from y_web.src.content.text_utils import strip_tags
from y_web.src.experiment.clock import (
    DEFAULT_CLOCK_MODE,
    DEFAULT_CLOCK_TIMEZONE,
    default_clock_config,
    ensure_experiment_clock,
    parse_anchor_date,
)
from y_web.src.experiment.context import get_current_experiment_id
from y_web.src.forum.service.data_classes import ArticlePreview
from y_web.src.models import (
    Agent,
    Articles,
    Exps,
    Images,
    Page,
    Post,
    Rounds,
    User_mgmt,
    Websites,
)

_Y_WEB_DIR = Path(__file__).resolve().parents[3]

# In-memory cache for OG image lookups to avoid repeated network requests
# Maps article_id -> Optional[Dict] (None means "already tried, no image found")
_og_image_cache: Dict[int, Optional[Dict[str, str]]] = {}
_clock_config_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}
_author_agent_page_cache: Dict[str, bool] = {}


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


def _fetch_and_cache_og_image(article) -> Optional[Dict[str, str]]:
    """Fetch OG image from article URL, cache in DB and memory."""
    if article.id in _og_image_cache:
        return _og_image_cache[article.id]

    image = None
    try:
        import requests

        from y_web.src.content.article_extractor import extract_image

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
        from y_web.src.experiment.context import get_current_experiment_bind

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


def _get_profile_pic(user: User_mgmt) -> str:
    from y_web.src.content.avatars import resolve_forum_profile_pic

    return resolve_forum_profile_pic(user, get_current_experiment_id())


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
    Load experiment clock settings from config_server.json, with fallback to the
    client JSON generated at creation time when the experiment-level clock config
    is stale or missing.
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

        experiment_dir = _get_experiment_dir(experiment)
        config_path = experiment_dir / "config_server.json"
        client_paths = sorted(experiment_dir.glob("client_*.json"))
        newest_client_mtime = (
            max(path.stat().st_mtime for path in client_paths) if client_paths else -1.0
        )
        mtime = max(
            config_path.stat().st_mtime if config_path.exists() else -1.0,
            newest_client_mtime,
        )
        cached = _clock_config_cache.get(exp_id)
        if cached and cached[0] == mtime:
            return cached[1]

        resolved_clock = default_clock_config()
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            resolved_clock = ensure_experiment_clock(payload)

        if client_paths:
            latest_client_path = max(
                client_paths, key=lambda path: path.stat().st_mtime
            )
            try:
                with latest_client_path.open("r", encoding="utf-8") as fh:
                    client_payload = json.load(fh)
                simulation = client_payload.get("simulation", {})
                raw_mode = simulation.get("clock_mode")
                raw_timezone = simulation.get("clock_timezone") or simulation.get(
                    "timezone"
                )
                raw_feed_refresh = simulation.get("feed_refresh")
                raw_anchor_date = simulation.get("clock_anchor_date")
                if raw_mode or raw_timezone or raw_feed_refresh or raw_anchor_date:
                    candidate_payload = {
                        "clock": {
                            "mode": raw_mode or resolved_clock.get("mode"),
                            "timezone": raw_timezone or resolved_clock.get("timezone"),
                            "feed_refresh": raw_feed_refresh
                            or resolved_clock.get("feed_refresh"),
                            "anchor_date": raw_anchor_date
                            or resolved_clock.get("anchor_date"),
                        }
                    }
                    resolved_clock = ensure_experiment_clock(candidate_payload)
            except Exception:
                pass

        _clock_config_cache[exp_id] = (mtime, resolved_clock)
        return resolved_clock
    except Exception:
        return default_clock_config()


def _format_display_time(day: str, hour: str) -> str:
    """
    Return the user-facing timestamp label for feed items.
    """
    clock = _resolve_experiment_clock()
    clock_mode = str(clock.get("mode", DEFAULT_CLOCK_MODE) or DEFAULT_CLOCK_MODE)

    if clock_mode != "real_time":
        if day == "None":
            return ""
        try:
            day_num = int(day)
            hour_num = int(hour)
            return f"Day {max(day_num, 0)} · Hour {min(max(hour_num, 0), 23):02d}"
        except (TypeError, ValueError):
            return str(day or "").strip()

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
    clock_mode = str(clock.get("mode", DEFAULT_CLOCK_MODE) or DEFAULT_CLOCK_MODE)
    if clock_mode != "real_time":
        return None

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
