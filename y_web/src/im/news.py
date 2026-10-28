"""News of an instant messaging (IM) experiment: the RSS collection, the news pages and the snapshot.

Same pattern as the forum: the researcher assigns reusable RSS resources (``ForumRssFeedResource``) to the experiment
(``rss_feeds.json``). IM publishes news through *page* accounts that carry a ``feed_url``; this module turns the assigned
feeds into such pages, and writes ``news_snapshot.jsonl`` (the fixed article list of the ``snapshot`` mode, which makes the
run reproducible and independent of the network). No Flask and no database here, so it is tested alone.
"""

import hashlib
import json
import os
import re
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional

from y_web.src.im.client_config import build_page

RSS_FILE = "rss_feeds.json"
SNAPSHOT_FILE = "news_snapshot.jsonl"
NEWS_MODES = ("snapshot", "live")
DEFAULT_PAGE_PROFILE = "Always On"


def parse_news_mode(value) -> str:
    """``snapshot`` (the default) or ``live``; anything else is the default."""
    value = str(value or "").strip().lower()
    return value if value in NEWS_MODES else "snapshot"


TOPIC_MODES = ("classify", "channel")


def parse_topic_mode(value) -> str:
    """``classify`` (the default: each news post gets the topic of its article) or ``channel`` (all channel topics)."""
    value = str(value or "").strip().lower()
    return value if value in TOPIC_MODES else "classify"


def selected_feeds(exp_folder: str) -> List[Dict[str, str]]:
    """The feeds assigned to the experiment, as ``[{"name", "feed_url"}]`` (the forum's ``rss_feeds.json``)."""
    try:
        with open(os.path.join(exp_folder, RSS_FILE), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    out, seen = [], set()
    for item in data if isinstance(data, list) else []:
        url = str((item or {}).get("feed_url") or "").strip()
        if url and url not in seen:
            seen.add(url)
            out.append({"name": str((item or {}).get("name") or "").strip(), "feed_url": url})
    return out


def page_username(name: str, url: str, taken: Iterable[str] = ()) -> str:
    """A username for the news page of a feed: the feed's name, made safe and unique."""
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", name or "").strip("_.-")[:30] or "news"
    taken = {t.lower() for t in taken}
    if base.lower() not in taken:
        return base
    return f"{base}_{hashlib.sha1(url.encode()).hexdigest()[:6]}"


def feed_pages(
    feeds: Iterable[Dict[str, str]],
    *,
    used_urls: Iterable[str],
    used_usernames: Iterable[str],
    topics: Iterable[str],
    activity_profile: str,
) -> List[Dict[str, Any]]:
    """A page account for each assigned feed that no page of the population already carries."""
    urls = {u for u in used_urls if u}
    names = list(used_usernames)
    topics = list(topics)
    out = []
    for feed in feeds:
        url = feed["feed_url"]
        if url in urls:
            continue
        username = page_username(feed.get("name", ""), url, names)
        names.append(username)
        urls.add(url)
        page = SimpleNamespace(
            id=f"rss-{hashlib.sha1(url.encode()).hexdigest()[:8]}", name=username, leaning="", feed=url
        )
        out.append(build_page(page, topics=topics, activity_profile=activity_profile))
    return out


def write_snapshot(
    exp_folder: str,
    feed_urls: Iterable[str],
    *,
    fetch: Optional[Callable[[str], List[dict]]] = None,
    replace: bool = False,
) -> Dict[str, Any]:
    """Fetch the feeds and write ``news_snapshot.jsonl`` with the runtime's own reader and file format.

    Returns ``{"articles": n, "feeds": {url: count}, "written": bool}``. A feed that cannot be read counts 0 and never
    stops the others. An existing snapshot is kept unless ``replace`` (a run that started must not change it).
    """
    from y_web.src.im.engine import ensure_im_importable

    ensure_im_importable()
    from yinstantmessaging.services.news_service import NewsFeedService

    path = os.path.join(exp_folder, SNAPSHOT_FILE)
    urls = sorted({u for u in feed_urls if u})
    if os.path.exists(path):
        if not replace:
            return {"articles": 0, "feeds": {}, "written": False}
        os.remove(path)
    service = NewsFeedService("live", path, fetch=fetch)
    service.load(urls)
    counts = {url: len(service._articles.get(url, [])) for url in urls}  # noqa: SLF001 - the runtime's own loader
    return {"articles": sum(counts.values()), "feeds": counts, "written": os.path.exists(path)}
