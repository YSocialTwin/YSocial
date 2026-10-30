"""Forum avatar helpers with deterministic and config-aware resolution."""

from __future__ import annotations

import hashlib
import json
import os
from urllib.parse import quote

from flask import current_app
from sqlalchemy import select

from y_web import db

DEFAULT_FORUM_AVATAR_MODE = "placeholder"
_FORUM_AVATAR_MODE_CACHE = {}


def discover_forum_avatar_urls():
    """Return static forum avatar URLs when local avatar assets are available."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        avatars_dir = os.path.normpath(
            os.path.join(
                base_dir,
                "..",
                "static",
                "assets",
                "img",
                "reddit",
                "avatars",
            )
        )
        if not os.path.isdir(avatars_dir):
            return []
        files = [
            name
            for name in os.listdir(avatars_dir)
            if os.path.isfile(os.path.join(avatars_dir, name))
            and name.lower().endswith(
                (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
            )
            and not name.startswith(".")
        ]
        files.sort()
        return [f"/static/assets/img/reddit/avatars/{name}" for name in files]
    except Exception:
        return []


def _deterministic_color(username: str) -> str:
    palette = [
        "#0f766e",
        "#1d4ed8",
        "#7c3aed",
        "#b45309",
        "#be123c",
        "#047857",
        "#4338ca",
        "#92400e",
    ]
    digest = hashlib.sha256(str(username or "forum").encode("utf-8")).hexdigest()
    return palette[int(digest[:8], 16) % len(palette)]


def _initials(username: str) -> str:
    cleaned = " ".join(
        str(username or "").replace("_", " ").replace("-", " ").split()
    ).strip()
    if not cleaned:
        return "?"
    parts = cleaned.split()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[1][:1]).upper()


def _fallback_avatar_data_url(username: str) -> str:
    initials = _initials(username)
    color = _deterministic_color(username)
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='96' height='96' viewBox='0 0 96 96'>
      <rect width='96' height='96' rx='48' fill='{color}'/>
      <text x='48' y='55' text-anchor='middle' font-family='Arial, sans-serif' font-size='34' font-weight='700' fill='white'>{initials}</text>
    </svg>
    """.strip()
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def deterministic_forum_avatar_url(username: str) -> str:
    """Return a deterministic avatar URL for a forum username."""
    urls = discover_forum_avatar_urls()
    if urls:
        digest = hashlib.sha256(str(username or "forum").encode("utf-8")).hexdigest()
        return urls[int(digest[:8], 16) % len(urls)]
    return _fallback_avatar_data_url(username)


def normalize_forum_avatar_mode(value: str) -> str:
    """Normalize forum avatar mode values."""
    mode = str(value or "").strip().lower()
    if mode in {"actual", "real", "real_pics", "profile_pics"}:
        return "actual"
    return DEFAULT_FORUM_AVATAR_MODE


def normalize_force_placeholder(value) -> bool:
    """Normalize the "force placeholders" flag (off by default)."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def _get_experiment_uid_from_db_name(db_name: str) -> str:
    if not db_name:
        return ""
    if db_name.startswith("experiments_"):
        return db_name.replace("experiments_", "")
    if db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
        parts = db_name.replace("\\", "/").split("/")
        if len(parts) >= 2:
            return parts[1]
    return ""


def _forum_experiment_config_path(exp_id: int) -> str:
    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    experiment = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
    if not experiment:
        return ""

    uid = _get_experiment_uid_from_db_name(getattr(experiment, "db_name", "") or "")
    if not uid:
        return ""

    base_dir = get_writable_path()
    return os.path.join(base_dir, "y_web", "experiments", uid, "config_server.json")


def _forum_settings(exp_id: int | None = None) -> dict:
    """Avatar settings of a forum experiment from config_server.json (mtime cached)."""
    default = {"mode": DEFAULT_FORUM_AVATAR_MODE, "force_placeholder": False}
    if exp_id is None:
        try:
            from y_web.src.experiment.context import get_current_experiment_id

            exp_id = get_current_experiment_id()
        except Exception:
            exp_id = None

    try:
        exp_id = int(exp_id or 0)
    except Exception:
        return default

    if exp_id <= 0:
        return default

    config_path = _forum_experiment_config_path(exp_id)
    if not config_path:
        return default

    try:
        mtime = os.path.getmtime(config_path)
    except OSError:
        return default

    cache_key = (exp_id, config_path)
    cached = _FORUM_AVATAR_MODE_CACHE.get(cache_key)
    if cached and cached.get("mtime") == mtime:
        return cached["settings"]

    settings = dict(default)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        settings["mode"] = normalize_forum_avatar_mode(config.get("avatar_mode"))
        settings["force_placeholder"] = normalize_force_placeholder(
            config.get("force_placeholder_avatars")
        )
    except Exception:
        settings = dict(default)

    _FORUM_AVATAR_MODE_CACHE[cache_key] = {"mtime": mtime, "settings": settings}
    return settings


def get_forum_avatar_mode(exp_id: int | None = None) -> str:
    """Load forum avatar mode from config_server.json with a lightweight mtime cache."""
    return _forum_settings(exp_id)["mode"]


def get_forum_force_placeholder(exp_id: int | None = None) -> bool:
    """True when the experiment forces the placeholders even for agents with a generated picture."""
    return bool(_forum_settings(exp_id)["force_placeholder"])


def resolve_forum_profile_pic(user, exp_id: int | None = None) -> str:
    """
    Resolve a forum actor avatar according to experiment avatar mode.

    A picture generated for an agent is used unless the experiment forces the placeholders
    (``force_placeholder_avatars``, off by default).
    In placeholder mode, every actor gets a deterministic Reddit-style avatar.
    In actual mode, page logos / agent profile pics / admin profile pics are used.
    """
    if not user:
        return ""

    username = str(getattr(user, "username", "") or "").strip()
    if not username:
        return ""

    if not bool(getattr(user, "is_page", False)) and not get_forum_force_placeholder(
        exp_id
    ):
        from y_web.src.agents.profile_pictures import picture_of_username

        # the picture generated for the agent wins, whatever the mode, unless the placeholders are forced
        generated = picture_of_username(username)
        if generated:
            return generated

    if normalize_forum_avatar_mode(get_forum_avatar_mode(exp_id)) != "actual":
        return deterministic_forum_avatar_url(username)

    try:
        from y_web.src.models import Admin_users, Agent, Page

        if bool(getattr(user, "is_page", False)):
            page = db.session.scalars(select(Page).filter_by(name=username)).first()
            if page and getattr(page, "logo", None):
                return page.logo
            return deterministic_forum_avatar_url(username)

        agent = db.session.scalars(select(Agent).filter_by(name=username)).first()
        if agent and getattr(agent, "profile_pic", None):
            return agent.profile_pic

        admin = db.session.scalars(
            select(Admin_users).filter_by(username=username)
        ).first()
        if admin and getattr(admin, "profile_pic", None):
            return admin.profile_pic
    except Exception:
        current_app.logger.debug(
            "forum avatar resolution fallback for %s", username, exc_info=True
        )

    user_id = getattr(user, "id", None)
    try:
        user_id = int(user_id)
    except Exception:
        user_id = None
    if user_id:
        return f"/static/assets/img/users/{user_id}.png"

    return deterministic_forum_avatar_url(username)


def resolve_forum_username_avatar(username: str, exp_id: int | None = None) -> str:
    """Resolve a forum avatar for the current principal when no experiment-side user exists."""
    username = str(username or "").strip()
    if not username:
        return ""

    if normalize_forum_avatar_mode(get_forum_avatar_mode(exp_id)) != "actual":
        return deterministic_forum_avatar_url(username)

    try:
        from y_web.src.models import Admin_users

        admin = db.session.scalars(
            select(Admin_users).filter_by(username=username)
        ).first()
        if admin and getattr(admin, "profile_pic", None):
            return admin.profile_pic
    except Exception:
        current_app.logger.debug(
            "forum username avatar resolution fallback for %s", username, exc_info=True
        )
    return deterministic_forum_avatar_url(username)
