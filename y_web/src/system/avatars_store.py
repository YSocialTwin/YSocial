"""Avatar images: bundled in a source checkout, downloaded on first run otherwise.

The ``ysocial`` wheel does not ship the ~10k profile pictures (~490 MB).  They
are fetched once into ``<YSOCIAL_HOME>/avatars`` and served by a dedicated route
that takes precedence over the Flask static handler for
``/static/assets/img/users/<file>``.
"""

import os
import tarfile
import threading
import time
import urllib.request

from y_web.src.system.path_utils import get_base_path, get_home_path

DEFAULT_AVATARS_URL = (
    "https://github.com/YSocialTwin/YSocial/releases/download/"
    "avatars-v1/ysocial-avatars.tar.gz"
)
_MIN_BUNDLED = 100
_EXT = (".png", ".jpg", ".jpeg", ".webp")
_FULL_SET = (
    9500  # a download with at least this many images is complete (legacy installs)
)
_CACHE_TTL = (
    300.0  # seconds a folder scan stays valid: listing ~10k files per image is too slow
)
_START_DELAY = 20.0  # let the app finish starting before the download begins
_PAUSE_EVERY, _PAUSE = 25, 0.04  # breathe every N files so requests are never starved
_lock = threading.Lock()
_state = {"status": "idle", "error": None, "bytes": 0, "total": 0, "files": 0}
_paused = threading.Event()  # set while the user has paused the download
_cache: dict = {}

_PLACEHOLDER_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    b'<rect width="64" height="64" fill="#cbd5e1"/>'
    b'<circle cx="32" cy="24" r="12" fill="#94a3b8"/>'
    b'<path d="M10 60c2-14 12-22 22-22s20 8 22 22z" fill="#94a3b8"/></svg>'
)


def bundled_avatars_dir() -> str:
    return os.path.join(get_base_path(), "y_web", "static", "assets", "img", "users")


def downloaded_avatars_dir() -> str:
    return os.path.join(get_home_path(), "avatars")


def _count(path: str) -> int:
    try:
        return sum(1 for f in os.listdir(path) if f.lower().endswith(_EXT))
    except OSError:
        return 0


def _cached(key, compute):
    """Value of ``compute()`` reused for a few minutes (scans of ~10k files are costly)."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    value = compute()
    _cache[key] = (now, value)
    return value


def _invalidate() -> None:
    _cache.clear()


def _marker() -> str:
    """File written when the download finished (next to the avatars folder)."""
    return os.path.join(get_home_path(), "avatars.complete")


def _bundled_populated() -> bool:
    bundled = bundled_avatars_dir()
    return _cached(("bundled", bundled), lambda: _count(bundled) >= _MIN_BUNDLED)


def get_avatars_dir() -> str:
    """Bundled folder when populated, otherwise the downloaded one."""
    if _bundled_populated():
        return bundled_avatars_dir()
    return downloaded_avatars_dir()


def avatars_ready() -> bool:
    """True when the images can be served: bundled, or a *complete* download.

    A download interrupted after a few images is not ready, so it resumes at the
    next start instead of leaving the profile pictures half there.
    """
    if _bundled_populated():
        return True
    if os.path.exists(_marker()):
        return True
    dest = downloaded_avatars_dir()
    if _cached(("downloaded", dest), lambda: _count(dest)) >= _FULL_SET:
        try:  # completed by an earlier version, which wrote no marker
            open(_marker(), "w", encoding="utf-8").close()
        except OSError:
            pass
        return True
    return False


def get_state() -> dict:
    """Status of the download: ``ready``, ``downloading``, ``paused``, ``failed`` or ``idle``.

    While running it also reports ``percent`` (of the archive when its size is known,
    otherwise of the expected number of images), ``bytes``/``total`` and ``files``.
    """
    if avatars_ready():
        return {"status": "ready", "error": None, "percent": 100}
    state = dict(_state)
    if state["status"] == "downloading" and _paused.is_set():
        state["status"] = "paused"
    if state["total"]:
        state["percent"] = min(99, state["bytes"] * 100 // state["total"])
    else:
        state["percent"] = min(99, state["files"] * 100 // _FULL_SET)
    return state


def pause_download() -> bool:
    """Pause a running download (the connection is kept; it continues on resume)."""
    if _state["status"] == "downloading" and not avatars_ready():
        _paused.set()
        return True
    return False


def resume_download() -> bool:
    """Continue a paused download, or start it again after a failure / when never started."""
    if _paused.is_set():
        _paused.clear()
        return True
    if _state["status"] in ("idle", "failed") and not avatars_ready():
        return ensure_avatars(delay=0, force=True)
    return False


class _CountingReader:
    """File-like wrapper that counts the bytes read and holds while paused."""

    def __init__(self, raw):
        self._raw = raw

    def read(self, size=-1):
        while _paused.is_set():
            time.sleep(0.3)
        data = self._raw.read(size)
        _state["bytes"] += len(data)
        return data


def _download(url: str, dest: str, pause: float = _PAUSE) -> None:
    """Stream the archive and extract the missing images one by one.

    Light on the app: no full-size buffer, images already on disk are skipped
    (a resumed download), and every few files the thread sleeps for a moment.
    """
    os.makedirs(dest, exist_ok=True)
    done = 0
    _state.update(bytes=0, files=0, total=0)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        try:
            _state["total"] = int(resp.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            _state["total"] = 0
        with tarfile.open(
            fileobj=_CountingReader(resp), mode="r|*", bufsize=1 << 20
        ) as tar:
            for member in tar:
                name = os.path.basename(member.name)
                if not member.isfile() or not name.lower().endswith(_EXT):
                    continue
                target = os.path.join(dest, name)
                if os.path.exists(target):
                    _state["files"] += 1
                    continue
                tmp = target + ".part"
                with open(tmp, "wb") as fh:
                    fh.write(tar.extractfile(member).read())
                os.replace(tmp, target)
                done += 1
                _state["files"] += 1
                if pause and done % _PAUSE_EVERY == 0:
                    time.sleep(pause)


def ensure_avatars(
    url: str | None = None,
    background: bool = True,
    delay: float | None = None,
    force: bool = False,
) -> bool:
    """Start the one-off avatar download if needed. Returns True if started.

    ``force`` (a person pressed the button) ignores ``YSOCIAL_SKIP_AVATARS_DOWNLOAD``;
    ``delay`` replaces the pause before a background download begins.
    """
    if avatars_ready():
        return False
    if not force and os.environ.get("YSOCIAL_SKIP_AVATARS_DOWNLOAD") == "1":
        return False
    url = url or os.environ.get("YSOCIAL_AVATARS_URL") or DEFAULT_AVATARS_URL
    with _lock:
        if _state["status"] == "downloading":
            return False
        _paused.clear()
        _state.update(status="downloading", error=None, bytes=0, total=0, files=0)

    def work():
        try:
            if background:
                time.sleep(_START_DELAY if delay is None else delay)
            last = None
            for attempt in range(
                3
            ):  # a dropped connection restarts; images on disk are skipped
                try:
                    _download(
                        url,
                        downloaded_avatars_dir(),
                        pause=_PAUSE if background else 0,
                    )
                    last = None
                    break
                except Exception as exc:
                    last = exc
                    time.sleep(2 * (attempt + 1))
            if last is not None:
                raise last
            try:
                open(_marker(), "w", encoding="utf-8").close()
            except OSError:
                pass
            _invalidate()
            _state.update(status="ready", error=None)
        except Exception as exc:  # network errors must never break startup
            _state.update(status="failed", error=str(exc))

    if background:
        threading.Thread(target=work, name="avatars-download", daemon=True).start()
    else:
        work()
    return True


def register_avatar_route(app) -> None:
    """Serve avatars from the active folder, with a placeholder fallback."""
    from flask import Response, send_from_directory

    def serve(filename):
        directory = get_avatars_dir()
        if os.path.isfile(os.path.join(directory, filename)):
            return send_from_directory(directory, filename, max_age=7 * 86400)
        return Response(
            _PLACEHOLDER_SVG,
            mimetype="image/svg+xml",
            headers={"Cache-Control": "no-cache"},
        )

    app.add_url_rule(
        "/static/assets/img/users/<path:filename>",
        endpoint="avatar_files",
        view_func=serve,
    )
