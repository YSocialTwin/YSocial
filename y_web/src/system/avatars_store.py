"""Avatar images: bundled in a source checkout, downloaded on first run otherwise.

The ``ysocial`` wheel does not ship the ~10k profile pictures (~490 MB).  They
are fetched once into ``<YSOCIAL_HOME>/avatars`` and served by a dedicated route
that takes precedence over the Flask static handler for
``/static/assets/img/users/<file>``.
"""

import os
import tarfile
import threading
import urllib.request

from y_web.src.system.path_utils import get_base_path, get_home_path

DEFAULT_AVATARS_URL = (
    "https://github.com/YSocialTwin/YSocial/releases/download/"
    "avatars-v1/ysocial-avatars.tar.gz"
)
_MIN_BUNDLED = 100
_EXT = (".png", ".jpg", ".jpeg", ".webp")
_lock = threading.Lock()
_state = {"status": "idle", "error": None}

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


def get_avatars_dir() -> str:
    """Bundled folder when populated, otherwise the downloaded one."""
    bundled = bundled_avatars_dir()
    if _count(bundled) >= _MIN_BUNDLED:
        return bundled
    return downloaded_avatars_dir()


def avatars_ready() -> bool:
    return _count(get_avatars_dir()) >= _MIN_BUNDLED


def get_state() -> dict:
    if avatars_ready():
        return {"status": "ready", "error": None}
    return dict(_state)


def _download(url: str, dest: str) -> None:
    """Stream the archive and extract images one by one (no full-size buffer)."""
    os.makedirs(dest, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        with tarfile.open(fileobj=resp, mode="r|*") as tar:
            for member in tar:
                name = os.path.basename(member.name)
                if not member.isfile() or not name.lower().endswith(_EXT):
                    continue
                tmp = os.path.join(dest, name + ".part")
                with open(tmp, "wb") as fh:
                    fh.write(tar.extractfile(member).read())
                os.replace(tmp, os.path.join(dest, name))


def ensure_avatars(url: str | None = None, background: bool = True) -> bool:
    """Start the one-off avatar download if needed. Returns True if started."""
    if avatars_ready() or os.environ.get("YSOCIAL_SKIP_AVATARS_DOWNLOAD") == "1":
        return False
    url = url or os.environ.get("YSOCIAL_AVATARS_URL") or DEFAULT_AVATARS_URL
    with _lock:
        if _state["status"] == "downloading":
            return False
        _state.update(status="downloading", error=None)

    def work():
        try:
            _download(url, downloaded_avatars_dir())
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
            return send_from_directory(directory, filename, max_age=86400)
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
