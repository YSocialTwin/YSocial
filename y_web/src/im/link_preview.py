"""Previews of the links in IM messages: title, summary, image and a short readable address.

What a card shows comes from two places, none of which touches the IM database (the runtime owns it):

* ``news_snapshot.jsonl`` of the experiment folder: title and summary of the articles the news pages share;
* ``link_previews.json`` in the same folder: a cache of what :func:`fetch_remote` read from the article page
  (``og:image``, ``og:title``, ``og:description``). The page never waits for the network: images are asked for
  afterwards by the browser (``/<exp>/im/api/link-preview``), and a failure is remembered for a while.
"""

import html
import ipaddress
import json
import os
import re
import socket
import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

SNAPSHOT_FILE = "news_snapshot.jsonl"
CACHE_FILE = "link_previews.json"
RETRY_AFTER = 6 * 3600  # seconds before a failed page is tried again
SUMMARY_CHARS = 220
MAX_BYTES = 1_000_000
TIMEOUT = 4.0
MAX_REDIRECTS = 3

_snapshot_cache: Dict[str, Any] = {}


def normalize(url: str) -> str:
    """A key that ignores the fragment, tracking parameters, the case of the host and a trailing slash."""
    try:
        p = urlparse((url or "").strip())
    except ValueError:
        return (url or "").strip()
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(p.query)
            if not k.lower().startswith("utm_") and k.lower() != "fbclid"
        ]
    )
    return urlunparse(
        (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", query, "")
    )


def short_url(url: str, limit: int = 46) -> str:
    """``ansa.it/…/in-israele-affluenza-al-449-alle…``: the host, an ellipsis and the end of the address."""
    try:
        p = urlparse(url)
    except ValueError:
        return url[:limit]
    host = (p.netloc or "").lower()
    host = host[4:] if host.startswith("www.") else host
    segments = [s for s in p.path.split("/") if s]
    if not host:
        return url[:limit]
    if not segments:
        text = host
    else:
        text = host + ("/…/" if len(segments) > 1 else "/") + segments[-1]
    return text if len(text) <= limit else text[: limit - 1] + "…"


def strip_urls(text: str, urls: Iterable[str]) -> str:
    """The text of a message without the addresses that are shown as cards (they would appear twice)."""
    out = text or ""
    for url in sorted({u for u in urls if u}, key=len, reverse=True):
        out = out.replace(url, " ")
    if out == (text or ""):
        return out
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\s*\n\s*", "\n", out)
    return out.strip()


def _clean(text: Optional[str], limit: int = SUMMARY_CHARS) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _snapshot(folder: str) -> Dict[str, Dict[str, str]]:
    path = os.path.join(folder, SNAPSHOT_FILE)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    cached = _snapshot_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    rows: Dict[str, Dict[str, str]] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("link"):
                    rows[normalize(row["link"])] = {
                        "title": _clean(row.get("title"), 160),
                        "summary": _clean(row.get("summary")),
                    }
    except OSError:
        return {}
    _snapshot_cache[path] = (mtime, rows)
    return rows


def _read_cache(folder: str) -> Dict[str, Dict[str, Any]]:
    try:
        with open(os.path.join(folder, CACHE_FILE), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(folder: str, data: Dict[str, Dict[str, Any]]) -> None:
    path = os.path.join(folder, CACHE_FILE)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass  # a preview is a convenience: never an error


def lookup(folder: str, url: str) -> Dict[str, Any]:
    """What is known about ``url`` without the network: ``title``, ``summary``, ``image``, ``short``, ``pending``."""
    key = normalize(url)
    known = dict(_snapshot(folder).get(key, {})) if folder else {}
    cached = _read_cache(folder).get(key, {}) if folder else {}
    image = cached.get("image") or ""
    failed = cached.get("failed") or 0
    pending = (
        not image and not (failed and time.time() - failed < RETRY_AFTER) and bool(url)
    )
    return {
        "title": known.get("title") or cached.get("title") or "",
        "summary": known.get("summary") or cached.get("summary") or "",
        "image": image,
        "short": short_url(url),
        "pending": pending,
    }


def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def _meta(soup, *names) -> str:
    for name in names:
        tag = soup.find("meta", property=name) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def fetch_remote(folder: str, url: str, *, get=None) -> Dict[str, Any]:
    """Read the article page once (public hosts only, a few redirects, a small body) and remember the result."""
    key = normalize(url)
    result: Dict[str, Any] = {"title": "", "summary": "", "image": ""}
    try:
        import requests
        from bs4 import BeautifulSoup

        get = get or requests.get
        current = url
        response = None
        for _ in range(MAX_REDIRECTS + 1):
            p = urlparse(current)
            if (
                p.scheme not in ("http", "https")
                or not p.hostname
                or not _public_host(p.hostname)
            ):
                raise ValueError("address not allowed")
            response = get(
                current,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; YSocial link preview)"
                },
                timeout=TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
            if response.status_code in (
                301,
                302,
                303,
                307,
                308,
            ) and response.headers.get("Location"):
                current = urljoin(current, response.headers["Location"])
                continue
            break
        if response is None or not response.ok:
            raise ValueError("no page")
        body = (
            response.raw.read(MAX_BYTES, decode_content=True)
            if hasattr(response, "raw") and response.raw
            else response.content[:MAX_BYTES]
        )
        soup = BeautifulSoup(body, "html.parser")
        image = _meta(soup, "og:image", "og:image:url", "twitter:image")
        if image:
            image = urljoin(current, image)
            if urlparse(image).scheme not in ("http", "https"):
                image = ""
        result = {
            "title": _clean(
                _meta(soup, "og:title", "twitter:title")
                or (soup.title.string if soup.title else ""),
                160,
            ),
            "summary": _clean(
                _meta(soup, "og:description", "description", "twitter:description")
            ),
            "image": image,
        }
    except (
        Exception
    ):  # noqa: BLE001 - offline, blocked, malformed: the card simply stays without image
        result = {"title": "", "summary": "", "image": "", "failed": time.time()}
    if folder:
        data = _read_cache(folder)
        data[key] = result
        _write_cache(folder, data)
    return result
