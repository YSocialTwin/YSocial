"""
Utility module to check for new blog posts from y-not.social/blog.

This module fetches the latest blog posts from the blog's RSS/Atom feed and
stores them in the ``blog_posts`` table of the admin database, so the admin
dashboard can list them without fetching the feed on every page load.
"""

import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from sqlalchemy import select

BLOG_FEED_URL = "https://y-not.social/feed.xml"
BLOG_URL = "https://y-not.social/blog/"
# How many of the newest feed entries are kept in the table (the dashboard shows 4)
BLOG_POSTS_TO_STORE = 6
# The dashboard refreshes the table in the background when the last check is older than this
BLOG_REFRESH_AFTER = timedelta(hours=12)
# ...and never tries more often than this, even when the feed is unreachable
BLOG_RETRY_AFTER = timedelta(hours=1)

_refresh_lock = threading.Lock()
_last_refresh_attempt = None


def _text(elem):
    """Return the stripped text of an XML element, or None."""
    if elem is None or elem.text is None:
        return None
    value = elem.text.strip()
    return value or None


def parse_blog_feed(content, limit=BLOG_POSTS_TO_STORE):
    """
    Parse an RSS 2.0 or Atom feed.

    Args:
        content: raw feed bytes/str
        limit: maximum number of entries to return

    Returns:
        list[dict]: newest first (feed order), each with ``title``, ``link`` and
        ``published_at`` (the date text as found in the feed). Empty when the feed
        has no usable entries.
    """
    default_date = datetime.utcnow().isoformat()
    root = ET.fromstring(content)
    posts = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        if title and link:
            pub_date = _text(item.find("pubDate"))
            posts.append(
                {
                    "title": title,
                    "link": link,
                    "published_at": pub_date or default_date,
                }
            )

    # Atom
    if not posts:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title = _text(entry.find("atom:title", ns))
            link_elem = entry.find("atom:link[@rel='alternate']", ns)
            if link_elem is None:
                link_elem = entry.find("atom:link", ns)
            link = None
            if link_elem is not None:
                link = link_elem.get("href") or _text(link_elem)
            published = _text(entry.find("atom:published", ns)) or _text(
                entry.find("atom:updated", ns)
            )
            if title and link:
                posts.append(
                    {
                        "title": title,
                        "link": link,
                        "published_at": published or default_date,
                    }
                )

    return posts[:limit]


def fetch_blog_posts(limit=BLOG_POSTS_TO_STORE):
    """
    Fetch the newest blog posts from the Y Social blog feed.

    Returns:
        list[dict]: newest first, see :func:`parse_blog_feed`. Empty list when the
        feed cannot be fetched or parsed.
    """
    try:
        try:
            response = requests.get(BLOG_FEED_URL, timeout=10, verify=True)
            if response.status_code != 200:
                print(f"Failed to fetch blog feed. Status: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error fetching blog feed: {e}")
            return []

        posts = parse_blog_feed(response.content, limit)
        if not posts:
            print("Could not parse blog feed - no valid item/entry found")
        return posts

    except Exception as e:
        print(f"Error fetching blog posts: {e}")
        return []


def fetch_latest_blog_post():
    """
    Fetch the latest blog post from the Y Social blog RSS feed.

    Returns:
        dict: Information about the latest blog post with keys:
              - title: Blog post title
              - published_at: Publication date (ISO format string)
              - link: URL to the blog post
              Returns None if unable to fetch or parse the feed.
    """
    posts = fetch_blog_posts(1)
    return posts[0] if posts else None


def parse_blog_date(value):
    """Parse an RSS (RFC 822) or ISO 8601 date; return a naive UTC datetime or None."""
    if not value:
        return None
    text = str(value).strip()
    parsed = None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def get_recent_blog_posts(limit=4):
    """
    Return the most recent blog posts stored in the database, newest first.

    Posts are ordered by publication date (falling back to insertion order when a
    date cannot be parsed), so older posts stored later still sort correctly.

    Returns:
        list[dict]: with ``id``, ``title``, ``link``, ``published_at`` (raw text),
        ``date`` (datetime or None) and ``is_new`` (not yet read).
    """
    from y_web import db
    from y_web.src.models import BlogPost

    rows = db.session.scalars(
        select(BlogPost).where(BlogPost.link.isnot(None)).order_by(BlogPost.id.desc())
    ).all()
    posts = [
        {
            "id": row.id,
            "title": (row.title or row.link).strip(),
            "link": row.link,
            "published_at": row.published_at,
            "date": parse_blog_date(row.published_at),
            "is_new": not row.is_read,
        }
        for row in rows
    ]
    posts.sort(key=lambda p: (p["date"] or datetime.min, p["id"]), reverse=True)
    return posts[:limit]


def update_blog_info_in_db():
    """
    Check for new blog posts and store/update blog information in the database.

    This function is called at application startup (and in the background by the
    dashboard when the stored data is old). It keeps the newest posts of the feed in
    the blog_posts table. Only the newest post is marked as unread (so it still
    triggers the announcement banner); older posts found for the first time are
    stored as already read.

    Returns:
        tuple: (has_new_post: bool, blog_info: dict or None)
    """
    try:
        print("Checking for new blog posts...")
        feed_posts = fetch_blog_posts()

        # Import here to avoid circular imports
        from y_web import db
        from y_web.src.models import BlogPost

        # Get the latest blog post from DB
        latest_in_db = db.session.scalars(
            select(BlogPost).order_by(BlogPost.id.desc())
        ).first()

        # Update check time
        check_time = datetime.utcnow().isoformat()

        if not feed_posts:
            # Could not fetch blog post, but update check time if record exists
            if latest_in_db:
                latest_in_db.latest_check_on = check_time
                db.session.commit()
            print("Could not fetch blog post")
            return False, None

        newest = feed_posts[0]
        known_links = {
            link
            for link in db.session.scalars(select(BlogPost.link)).all()
            if link is not None
        }

        new_posts = [p for p in feed_posts if p["link"] not in known_links]
        # oldest first, so row ids follow publication order
        for post in reversed(new_posts):
            db.session.add(
                BlogPost(
                    title=post["title"],
                    published_at=post["published_at"],
                    link=post["link"],
                    is_read=post is not newest,
                    latest_check_on=check_time,
                )
            )

        # Keep the check time of the rows that were already there fresh
        for row in db.session.scalars(
            select(BlogPost).where(BlogPost.link.in_(known_links))
        ).all():
            row.latest_check_on = check_time
        db.session.commit()

        newest_row = db.session.scalars(
            select(BlogPost).where(BlogPost.link == newest["link"])
        ).first()

        if newest["link"] in known_links:
            print("No new blog post")
            if newest_row is not None and not newest_row.is_read:
                return True, {
                    "id": newest_row.id,
                    "title": newest_row.title,
                    "published_at": newest_row.published_at,
                    "link": newest_row.link,
                }
            return False, None

        print("New blog post found")
        return True, {
            "id": newest_row.id,
            "title": newest_row.title,
            "published_at": newest_row.published_at,
            "link": newest_row.link,
        }

    except Exception as e:
        print(f"Error checking for blog posts: {e}")
        import traceback

        traceback.print_exc()
        try:
            from y_web import db

            db.session.rollback()
        except Exception:
            pass
        return False, None


def refresh_blog_posts_if_stale(app):
    """
    Refresh the stored blog posts in a background thread when they are old.

    Never blocks the caller and never runs more than one refresh at a time; after an
    attempt (successful or not) it waits at least ``BLOG_RETRY_AFTER`` before trying
    again. Skipped when the application is in testing mode.

    Returns:
        bool: True when a refresh was started.
    """
    global _last_refresh_attempt

    if app.config.get("TESTING"):
        return False

    from y_web import db
    from y_web.src.models import BlogPost

    now = datetime.utcnow()
    if _last_refresh_attempt and now - _last_refresh_attempt < BLOG_RETRY_AFTER:
        return False

    try:
        checks = [
            parse_blog_date(value)
            for value in db.session.scalars(select(BlogPost.latest_check_on)).all()
        ]
    except Exception:
        return False
    last_check = max((c for c in checks if c), default=None)
    if last_check and now - last_check < BLOG_REFRESH_AFTER:
        return False

    if not _refresh_lock.acquire(blocking=False):
        return False
    _last_refresh_attempt = now

    def _run():
        try:
            with app.app_context():
                update_blog_info_in_db()
        finally:
            _refresh_lock.release()

    threading.Thread(target=_run, name="blog-refresh", daemon=True).start()
    return True
