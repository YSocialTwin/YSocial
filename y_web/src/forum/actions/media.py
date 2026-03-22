from __future__ import annotations
import os
import re
import uuid
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse
import requests

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg")
_VIDEO_EXTENSIONS = (".mp4",)
_MEDIA_EXTENSIONS = _IMAGE_EXTENSIONS + _VIDEO_EXTENSIONS


def _normalize_external_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    # Local URLs (e.g. /uploads/...) should be preserved as-is.
    if url.startswith("/"):
        return url
    if url.lower().startswith("data:"):
        return ""
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    return url


def _looks_like_image_url(url: str) -> bool:
    if not url:
        return False
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = url.lower()
    return path.endswith(_IMAGE_EXTENSIONS)


def _looks_like_video_url(url: str) -> bool:
    if not url:
        return False
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = url.lower()
    return path.endswith(_VIDEO_EXTENSIONS)


def _looks_like_media_url(url: str) -> bool:
    if not url:
        return False
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = url.lower()
    return path.endswith(_MEDIA_EXTENSIONS)


def _extract_candidate_media_url(url: str) -> str:
    """
    Extract a likely media URL from direct links or query-embedded links.

    Common search pages use query params like `imgurl=` or `url=` that point
    to the real image URL.
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    if _looks_like_media_url(raw):
        return _normalize_external_url(raw)

    try:
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query, keep_blank_values=True)
    except Exception:
        return raw

    candidate_keys = ("imgurl", "image_url", "mediaurl", "url")
    for key in candidate_keys:
        values = qs.get(key) or []
        if not values:
            continue
        candidate = unquote((values[0] or "").strip())
        if not candidate:
            continue
        if candidate.startswith("//"):
            candidate = f"{parsed.scheme}:{candidate}"
        if candidate.startswith("/"):
            candidate = f"{parsed.scheme}://{parsed.netloc}{candidate}"
        normalized_candidate = _normalize_external_url(candidate)
        if _looks_like_media_url(normalized_candidate):
            return normalized_candidate

    return _normalize_external_url(raw)


_CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}
_MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_DOWNLOAD_TIMEOUT = 10  # seconds


def _remote_looks_like_image(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }
    try:
        resp = requests.head(
            url, headers=headers, timeout=_DOWNLOAD_TIMEOUT, allow_redirects=True
        )
        content_type = (
            resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        )
        if content_type.startswith("image/"):
            return True
    except Exception:
        pass

    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=_DOWNLOAD_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )
        content_type = (
            resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        )
        return content_type.startswith("image/")
    except Exception:
        return False


def _download_image_to_uploads(remote_url: str, exp_id: int) -> Optional[str]:
    """
    Fetch a remote image URL and save it locally under uploads/reddit/<exp_id>/.

    Returns the served path (e.g. '/uploads/reddit/8/abc123.gif') on success,
    or None if the download fails for any reason.

    Uses a browser-like User-Agent and Referer so that CDN-gated hosts like
    preview.redd.it serve the content.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": f"{urlparse(remote_url).scheme}://{urlparse(remote_url).netloc}/",
        }
        resp = requests.get(
            remote_url, headers=headers, timeout=_DOWNLOAD_TIMEOUT, stream=True
        )
        if resp.status_code != 200:
            return None

        # Honour Content-Length if provided to avoid reading huge files.
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > _MAX_DOWNLOAD_BYTES:
            return None

        raw = b""
        for chunk in resp.iter_content(chunk_size=65536):
            raw += chunk
            if len(raw) > _MAX_DOWNLOAD_BYTES:
                return None

        if not raw:
            return None

        # Determine file extension: prefer Content-Type, fall back to URL path.
        content_type = (
            resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        )
        ext = _CONTENT_TYPE_TO_EXT.get(content_type)
        if not ext:
            path = urlparse(remote_url).path.lower()
            for candidate in _IMAGE_EXTENSIONS:
                if path.endswith(candidate):
                    ext = candidate
                    break
        if not ext:
            return None

        from y_web.src.system.path_utils import get_writable_path

        out_dir = os.path.join(
            get_writable_path(), "y_web", "uploads", "reddit", str(exp_id)
        )
        os.makedirs(out_dir, exist_ok=True)

        filename = f"{uuid.uuid4().hex}{ext}"
        out_path = os.path.join(out_dir, filename)
        with open(out_path, "wb") as fh:
            fh.write(raw)

        return f"/uploads/reddit/{exp_id}/{filename}"

    except Exception:
        return None
