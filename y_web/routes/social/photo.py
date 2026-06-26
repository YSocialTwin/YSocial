"""
Photo sharing platform routes.

Provides an Instagram-like feed for YPhotoSharing experiments while keeping the
same routing conventions used by the microblogging and forum frontends.
"""

import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

from flask import abort, flash, redirect, render_template, send_from_directory, url_for
from flask_login import current_user, login_required

from y_web.routes.social._blueprint import main
from y_web.routes.social.helpers import (
    _experiment_memory_enabled,
    get_safe_profile_pic,
    is_admin,
)
from y_web.src.data_access import get_unanswered_mentions
from y_web.src.experiment.helpers import ensure_experiment_user, get_experiment_dir, get_experiment_engine_uri
from y_web.src.models import Exps, User_mgmt
from y_web.src.recsys.follow_recsys import get_suggested_users


def _photo_logged_user_id():
    logged_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if logged_user is not None:
        return logged_user.id
    return getattr(current_user, "id", 0) or 0


def _photo_db_path(exp: Exps) -> Optional[str]:
    uri = get_experiment_engine_uri(exp)
    if not uri or not uri.startswith("sqlite:///"):
        return None
    return uri.replace("sqlite:///", "", 1)


def _photo_media_url(exp: Exps, raw_url: Optional[str]) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("file://"):
        parsed = urlparse(value)
        filename = Path(parsed.path).name
        if filename:
            return f"/{exp.idexp}/photo/media/{filename}"
    if os.path.isabs(value):
        filename = Path(value).name
        if filename:
            return f"/{exp.idexp}/photo/media/{filename}"
    return value


def _photo_db_rows(exp: Exps, query: str, params: tuple = ()) -> list[dict]:
    db_path = _photo_db_path(exp)
    if not db_path or not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _format_photo_time(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text


def _build_photo_items(exp: Exps, page: int, page_size: int) -> list[dict]:
    offset = max(0, (page - 1) * page_size)
    rows = _photo_db_rows(
        exp,
        """
        SELECT
            p.*,
            u.username AS author_username,
            u.profile_picture_url AS author_profile_picture_url,
            u.cover_image AS author_cover_image,
            u.is_page AS author_is_page
        FROM photos p
        LEFT JOIN user_mgmt u ON u.id = p.user_id
        WHERE COALESCE(p.is_removed, 0) = 0
        ORDER BY p.created_at DESC, p.id DESC
        LIMIT ? OFFSET ?
        """,
        (page_size, offset),
    )

    items: list[dict] = []
    for row in rows:
        raw_media = row.get("image_url") or row.get("media_url") or ""
        author_id = str(row.get("user_id") or "")
        author_name = (
            str(row.get("author_username") or "").strip() or author_id or "Unknown"
        )
        profile_pic = (
            row.get("author_profile_picture_url")
            or row.get("author_cover_image")
            or ""
        )
        items.append(
            {
                "post_id": row.get("id"),
                "author_id": author_id,
                "author": author_name,
                "profile_pic": _photo_media_url(exp, profile_pic),
                "display_time": _format_photo_time(row.get("created_at")),
                "thread_id": row.get("id"),
                "post": (row.get("caption") or row.get("alt_text") or ""),
                "image": {
                    "url": _photo_media_url(exp, raw_media),
                    "description": row.get("caption") or row.get("alt_text") or "",
                },
                "likes": row.get("num_likes") or 0,
                "t_comments": row.get("num_comments") or 0,
                "is_shared": row.get("num_shares") or 0,
                "shared_from": -1,
            }
        )
    return items


def _build_photo_story_previews(exp: Exps, fallback_users, limit: int = 8):
    rows = _photo_db_rows(
        exp,
        """
        SELECT
            s.*,
            u.username AS author_username,
            u.profile_picture_url AS author_profile_picture_url,
            u.cover_image AS author_cover_image
        FROM stories s
        LEFT JOIN user_mgmt u ON u.id = s.user_id
        ORDER BY s.created_at DESC, s.id DESC
        """,
    )

    stories = []
    seen_ids = set()
    for row in rows:
        user_id = str(row.get("user_id") or "")
        if not user_id or user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        profile_pic = (
            row.get("author_profile_picture_url")
            or row.get("author_cover_image")
            or _photo_media_url(exp, row.get("media_url"))
        )
        stories.append(
            {
                "id": user_id,
                "username": row.get("author_username") or user_id,
                "profile_pic": profile_pic,
                "label": "Recent story",
            }
        )
        if len(stories) >= limit:
            return stories

    for user in fallback_users or []:
        user_id = user.get("id")
        if user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        stories.append(
            {
                "id": user_id,
                "username": user.get("username", ""),
                "profile_pic": user.get("profile_pic", ""),
                "label": "Suggested",
            }
        )
        if len(stories) >= limit:
            break

    return stories


def _build_photo_stories(items, fallback_users):
    stories = []
    seen_ids = set()

    for item in items or []:
        author_id = item.get("author_id")
        if author_id in seen_ids:
            continue
        seen_ids.add(author_id)
        stories.append(
            {
                "id": author_id,
                "username": item.get("author", ""),
                "profile_pic": item.get("profile_pic", ""),
                "label": "Recent post",
            }
        )
        if len(stories) >= 8:
            return stories

    for user in fallback_users or []:
        user_id = user.get("id")
        if user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        stories.append(
            {
                "id": user_id,
                "username": user.get("username", ""),
                "profile_pic": user.get("profile_pic", ""),
                "label": "Suggested",
            }
        )
        if len(stories) >= 8:
            break

    return stories


@main.get("/photo/feed")
@login_required
def photo_feed_logged():
    """
    Legacy landing page for photo-sharing simulations.

    Redirects the logged-in participant to the first active photo-sharing
    experiment.
    """
    exps = Exps.query.filter(
        Exps.status != 0, Exps.platform_type == "photo_sharing"
    ).all()
    if not exps:
        flash("No active photo-sharing experiment. Please activate one first.")
        return redirect("/admin/experiments")

    if len(exps) > 1:
        return redirect("/admin/join_simulation")

    exp = exps[0]
    return redirect(f"/{exp.idexp}/photo/feed/all/feed/rf/1")


@main.get("/<int:exp_id>/photo/media/<path:filename>")
@login_required
def photo_media(exp_id, filename):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "photo_sharing":
        abort(404)

    media_root = get_experiment_dir(exp) / "media"
    return send_from_directory(media_root, filename)


@main.get(
    "/<int:exp_id>/photo/feed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>"
)
@login_required
def photo_feed(exp_id, user_id="all", timeline="timeline", mode="rf", page=1):
    """
    Render the photo-sharing feed.

    The feed keeps the microblogging/forum data contract but presents the
    content in a photo-first layout.
    """
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "photo_sharing":
        abort(404)

    exp_user, _created = ensure_experiment_user(
        exp,
        user_id=getattr(current_user, "id", 0) or 0,
        username=str(current_user.username),
        email=str(getattr(current_user, "email", "") or ""),
        password=str(getattr(current_user, "password", "") or ""),
        joined_on=0,
    )

    if page < 1:
        page = 1

    max_post_per_page = 10
    username = ""

    if user_id != "all":
        try:
            user = User_mgmt.query.filter_by(id=user_id).first()
            if not user:
                user = User_mgmt.query.filter_by(username=current_user.username).first()
        except Exception:
            user = None
        if not user:
            return redirect(f"/{exp_id}/photo/feed/all/feed/rf/1")
        username = user.username

    res = _build_photo_items(exp, page, max_post_per_page)
    if len(res) == 0 and page > 1:
        return redirect(f"/{exp_id}/photo/feed/{user_id}/{timeline}/{mode}/{page - 1}")

    logged_user = exp_user
    if logged_user is None:
        try:
            logged_user = User_mgmt.query.filter_by(
                username=current_user.username
            ).first()
        except Exception:
            logged_user = None

    profile_pic = get_safe_profile_pic(
        current_user.username, getattr(logged_user, "is_page", 0) if logged_user else 0
    )
    try:
        mentions = get_unanswered_mentions(current_user.username)
    except Exception:
        mentions = []
    try:
        sfollow = (
            get_suggested_users(logged_user.username, pages=False)
            if logged_user
            else []
        )
        spages = (
            get_suggested_users(logged_user.username, pages=True) if logged_user else []
        )
    except Exception:
        sfollow = []
        spages = []
    stories = _build_photo_story_previews(exp, sfollow + spages)

    return render_template(
        "photo/feed.html",
        items=res,
        stories=stories,
        page=page,
        profile_pic=profile_pic,
        profile_pic_feed=profile_pic,
        user_id=user_id,
        timeline=timeline,
        username=username,
        mode=mode,
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        logged_id=getattr(logged_user, "id", _photo_logged_user_id()),
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        sfollow=sfollow,
        spages=spages,
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
        photo_sidebar_collapsed=True,
    )
