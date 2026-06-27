"""
Photo sharing platform routes.

Provides an Instagram-like feed for YPhotoSharing experiments while keeping the
same routing conventions used by the microblogging and forum frontends.
"""

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from y_web.routes.social._blueprint import main
from y_web.routes.social.helpers import (
    _experiment_memory_enabled,
    get_safe_profile_pic,
    is_admin,
)
from y_web.src.data_access import get_unanswered_mentions
from y_web.src.experiment.helpers import (
    ensure_experiment_user,
    get_experiment_engine_uri,
    open_experiment_session,
)
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


def _photo_media_root(exp: Exps) -> Optional[Path]:
    db_path = _photo_db_path(exp)
    if not db_path:
        return None
    return Path(db_path).parent / "media"


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


def _photo_user_avatar_url(user_id) -> str:
    value = str(user_id or "").strip()
    if not value:
        value = "1"
    try:
        image_id = str(int(value))
    except (TypeError, ValueError):
        hashed = int(hashlib.md5(value.encode("utf-8")).hexdigest(), 16)
        image_id = str((hashed % 1000) + 1)
    return f"/static/assets/img/users/{image_id}.png"


def _photo_profile_pic_url(
    exp: Exps,
    *,
    username: str,
    user_id,
    raw_profile_pic: Optional[str] = "",
) -> str:
    value = _photo_media_url(exp, raw_profile_pic)
    if value:
        return value

    safe_profile_pic = get_safe_profile_pic(username, 0)
    value = _photo_media_url(exp, safe_profile_pic)
    if value:
        return value

    return _photo_user_avatar_url(user_id or username)


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


def _photo_build_item(exp: Exps, row: dict) -> dict:
    raw_media = row.get("image_url") or row.get("media_url") or ""
    author_id = str(row.get("user_id") or "")
    author_name = (
        str(row.get("author_username") or "").strip() or author_id or "Unknown"
    )
    return {
        "post_id": row.get("id"),
        "author_id": author_id,
        "author": author_name,
        "profile_pic": _photo_profile_pic_url(
            exp,
            username=author_name,
            user_id=author_id,
            raw_profile_pic=row.get("author_profile_picture_url"),
        ),
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


def _format_photo_time(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text


def _photo_latest_recommendation_ids(exp: Exps, user_id) -> list[str]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return []
    rows = _photo_db_rows(
        exp,
        """
        SELECT
            r.photo_ids
        FROM recommendations r
        LEFT JOIN rounds rd ON rd.id = r.round
        WHERE r.user_id = ?
        ORDER BY COALESCE(rd.day, 0) DESC, COALESCE(rd.hour, 0) DESC, r.id DESC
        LIMIT 1
        """,
        (user_key,),
    )
    if not rows:
        return []
    raw_photo_ids = rows[0].get("photo_ids") or "[]"
    try:
        photo_ids = json.loads(raw_photo_ids)
    except Exception:
        photo_ids = []
    return [str(photo_id) for photo_id in photo_ids if str(photo_id or "").strip()]


def _photo_active_contact_ids(exp: Exps, user_id) -> list[str]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return []

    rows = _photo_db_rows(
        exp,
        """
        SELECT
            f.user_id AS source_user_id,
            f.follower_id AS target_user_id,
            COALESCE(f.action, 'follow') AS action,
            COALESCE(rd.day, 0) AS day,
            COALESCE(rd.hour, 0) AS hour,
            f.id AS follow_row_id
        FROM follow f
        LEFT JOIN rounds rd ON rd.id = f.round
        ORDER BY COALESCE(rd.day, 0) ASC, COALESCE(rd.hour, 0) ASC, f.id ASC
        """,
    )
    latest = {}
    for row in rows:
        source_id = str(row.get("source_user_id") or "").strip()
        target_id = str(row.get("target_user_id") or "").strip()
        action = str(row.get("action") or "").strip().lower()
        if not source_id or not target_id:
            continue
        latest[(source_id, target_id)] = action

    return [
        target_id
        for (source_id, target_id), action in latest.items()
        if source_id == user_key and action == "follow" and target_id != user_key
    ]


def _photo_ordered_unique_ids(*groups: list[str]) -> list[str]:
    ordered = []
    seen = set()
    for group in groups:
        for value in group or []:
            value = str(value or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            ordered.append(value)
    return ordered


def _photo_post_rows_by_ids(exp: Exps, photo_ids: list[str]) -> list[dict]:
    ordered_ids = [
        str(photo_id or "").strip()
        for photo_id in photo_ids
        if str(photo_id or "").strip()
    ]
    if not ordered_ids:
        return []

    placeholders = ",".join("?" for _ in ordered_ids)
    rows = _photo_db_rows(
        exp,
        f"""
        SELECT
            p.*,
            u.username AS author_username,
            u.profile_picture_url AS author_profile_picture_url,
            u.cover_image AS author_cover_image,
            u.is_page AS author_is_page
        FROM photos p
        LEFT JOIN user_mgmt u ON u.id = p.user_id
        WHERE p.id IN ({placeholders}) AND COALESCE(p.is_removed, 0) = 0
        """,
        tuple(ordered_ids),
    )
    rows_by_id = {str(row.get("id")): row for row in rows}
    return [rows_by_id[photo_id] for photo_id in ordered_ids if photo_id in rows_by_id]


def _photo_photo_ids_by_author_ids(exp: Exps, author_ids: list[str]) -> list[str]:
    ordered_author_ids = [
        str(author_id or "").strip()
        for author_id in (author_ids or [])
        if str(author_id or "").strip()
    ]
    if not ordered_author_ids:
        return []

    placeholders = ",".join("?" for _ in ordered_author_ids)
    rows = _photo_db_rows(
        exp,
        f"""
        SELECT p.id
        FROM photos p
        WHERE p.user_id IN ({placeholders}) AND COALESCE(p.is_removed, 0) = 0
        ORDER BY p.created_at DESC, p.id DESC
        """,
        tuple(ordered_author_ids),
    )
    return [
        str(row.get("id") or "").strip()
        for row in rows
        if str(row.get("id") or "").strip()
    ]


def _photo_all_photo_ids(exp: Exps) -> list[str]:
    rows = _photo_db_rows(
        exp,
        """
        SELECT p.id
        FROM photos p
        WHERE COALESCE(p.is_removed, 0) = 0
        ORDER BY p.created_at DESC, p.id DESC
        """,
    )
    return [
        str(row.get("id") or "").strip()
        for row in rows
        if str(row.get("id") or "").strip()
    ]


def _build_photo_items_from_rows(exp: Exps, rows: list[dict]) -> list[dict]:
    return [_photo_build_item(exp, row) for row in rows]


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
    return _build_photo_items_from_rows(exp, rows)


def _build_photo_recommended_items(
    exp: Exps, logged_user_id, page: int, page_size: int
) -> list[dict]:
    page = max(1, page)
    rec_photo_ids = _photo_latest_recommendation_ids(exp, logged_user_id)
    start = (page - 1) * page_size
    end = start + page_size
    followee_ids = _photo_active_contact_ids(exp, logged_user_id)

    combined_ids = []
    if followee_ids:
        combined_ids.extend(_photo_photo_ids_by_author_ids(exp, followee_ids))
    combined_ids.extend(rec_photo_ids)
    if len(combined_ids) < end:
        combined_ids.extend(_photo_all_photo_ids(exp))

    slice_ids = _photo_ordered_unique_ids(combined_ids)[start:end]
    if not slice_ids:
        return []

    ordered_rows = _photo_post_rows_by_ids(exp, slice_ids)
    return _build_photo_items_from_rows(exp, ordered_rows)


def _build_photo_follower_items(
    exp: Exps, logged_user_id, page: int, page_size: int
) -> list[dict]:
    contact_ids = _photo_active_contact_ids(exp, logged_user_id)
    if not contact_ids:
        return []

    offset = max(0, (page - 1) * page_size)
    placeholders = ",".join("?" for _ in contact_ids)
    rows = _photo_db_rows(
        exp,
        f"""
        SELECT
            p.*,
            u.username AS author_username,
            u.profile_picture_url AS author_profile_picture_url,
            u.cover_image AS author_cover_image,
            u.is_page AS author_is_page
        FROM photos p
        LEFT JOIN user_mgmt u ON u.id = p.user_id
        WHERE p.user_id IN ({placeholders}) AND COALESCE(p.is_removed, 0) = 0
        ORDER BY p.created_at DESC, p.id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(contact_ids + [page_size, offset]),
    )
    return _build_photo_items_from_rows(exp, rows)


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
        stories.append(
            {
                "id": user_id,
                "username": row.get("author_username") or user_id,
                "profile_pic": _photo_profile_pic_url(
                    exp,
                    username=row.get("author_username") or user_id,
                    user_id=user_id,
                    raw_profile_pic=row.get("author_profile_picture_url"),
                ),
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


def _photo_suggested_contacts(
    exp: Exps,
    logged_username: str,
    limit: int = 7,
    exclude_ids: Optional[set[str]] = None,
):
    contacts = []
    seen_ids = set()
    excluded_ids = {
        str(value or "").strip()
        for value in (exclude_ids or set())
        if str(value or "").strip()
    }

    try:
        suggested_users = get_suggested_users(logged_username, pages=False)
    except Exception:
        suggested_users = []

    try:
        suggested_pages = get_suggested_users(logged_username, pages=True)
    except Exception:
        suggested_pages = []

    for user in suggested_users[:5]:
        user_id = str(user.get("id") or "").strip()
        if not user_id or user_id in seen_ids or user_id in excluded_ids:
            continue
        seen_ids.add(user_id)
        contacts.append(
            {
                "id": user_id,
                "username": user.get("username", ""),
                "profile_pic": user.get("profile_pic", ""),
                "kind": "contact",
            }
        )
        if len(contacts) >= limit:
            return contacts

    for page in suggested_pages[:2]:
        user_id = str(page.get("id") or "").strip()
        if not user_id or user_id in seen_ids or user_id in excluded_ids:
            continue
        seen_ids.add(user_id)
        contacts.append(
            {
                "id": user_id,
                "username": page.get("username", ""),
                "profile_pic": page.get("profile_pic", ""),
                "kind": "page",
            }
        )
        if len(contacts) >= limit:
            return contacts

    if contacts:
        return contacts

    session, engine = open_experiment_session(exp)
    if session is None or engine is None:
        return contacts

    try:
        rows = (
            session.query(User_mgmt)
            .filter(User_mgmt.username != logged_username)
            .order_by(User_mgmt.username.asc())
            .limit(limit)
            .all()
        )
        for row in rows:
            user_id = str(getattr(row, "id", "") or "").strip()
            if not user_id or user_id in seen_ids or user_id in excluded_ids:
                continue
            seen_ids.add(user_id)
            contacts.append(
                {
                    "id": user_id,
                    "username": getattr(row, "username", "") or user_id,
                    "profile_pic": _photo_profile_pic_url(
                        exp,
                        username=getattr(row, "username", "") or user_id,
                        user_id=user_id,
                        raw_profile_pic=getattr(row, "profile_picture_url", ""),
                    ),
                    "kind": "fallback",
                }
            )
    finally:
        session.close()
        engine.dispose()

    return contacts


def _photo_user_record(exp: Exps, user_id) -> dict:
    user_key = str(user_id or "").strip()
    if not user_key:
        return {}

    rows = _photo_db_rows(
        exp,
        "SELECT * FROM user_mgmt WHERE id = ? LIMIT 1",
        (user_key,),
    )
    if rows:
        return rows[0]

    rows = _photo_db_rows(
        exp,
        "SELECT * FROM user_mgmt WHERE username = ? LIMIT 1",
        (user_key,),
    )
    return rows[0] if rows else {}


def _photo_follow_relations(exp: Exps) -> dict[tuple[str, str], dict]:
    rows = _photo_db_rows(
        exp,
        """
        SELECT
            f.user_id AS source_user_id,
            f.follower_id AS target_user_id,
            COALESCE(f.action, 'follow') AS action,
            COALESCE(rd.day, 0) AS day,
            COALESCE(rd.hour, 0) AS hour,
            f.id AS follow_row_id
        FROM follow f
        LEFT JOIN rounds rd ON rd.id = f.round
        ORDER BY COALESCE(rd.day, 0) ASC, COALESCE(rd.hour, 0) ASC, f.id ASC
        """,
    )
    latest = {}
    for order, row in enumerate(rows):
        source_id = str(row.get("source_user_id") or "").strip()
        target_id = str(row.get("target_user_id") or "").strip()
        action = str(row.get("action") or "").strip().lower()
        if not source_id or not target_id:
            continue
        latest[(source_id, target_id)] = {
            "action": action,
            "order": order,
            "row_id": row.get("follow_row_id"),
        }
    return latest


def _photo_follow_stats(exp: Exps, user_id) -> tuple[int, int]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return 0, 0

    latest = _photo_follow_relations(exp)

    followers = {
        source_id
        for (source_id, target_id), meta in latest.items()
        if target_id == user_key
        and meta.get("action") == "follow"
        and source_id != user_key
    }
    followees = {
        target_id
        for (source_id, target_id), meta in latest.items()
        if source_id == user_key
        and meta.get("action") == "follow"
        and target_id != user_key
    }
    return len(followers), len(followees)


def _photo_profile_photo_items(
    exp: Exps, user_id, mode: str, page: int, page_size: int
) -> list[dict]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return []

    page = max(1, page)
    offset = max(0, (page - 1) * page_size)
    normalized_mode = str(mode or "recent").strip().lower()

    if normalized_mode == "saved":
        rows = _photo_db_rows(
            exp,
            """
            SELECT
                p.*,
                u.username AS author_username,
                u.profile_picture_url AS author_profile_picture_url,
                u.cover_image AS author_cover_image,
                u.is_page AS author_is_page
            FROM saved_photos sp
            JOIN photos p ON p.id = sp.photo_id
            LEFT JOIN user_mgmt u ON u.id = p.user_id
            WHERE sp.user_id = ? AND COALESCE(p.is_removed, 0) = 0
            ORDER BY sp.created_at DESC, sp.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_key, page_size, offset),
        )
        return _build_photo_items_from_rows(exp, rows)

    if normalized_mode == "tagged":
        rows = _photo_db_rows(
            exp,
            """
            SELECT
                p.*,
                u.username AS author_username,
                u.profile_picture_url AS author_profile_picture_url,
                u.cover_image AS author_cover_image,
                u.is_page AS author_is_page
            FROM mentions m
            JOIN photos p ON p.id = m.photo_id
            LEFT JOIN user_mgmt u ON u.id = p.user_id
            WHERE m.user_id = ? AND COALESCE(p.is_removed, 0) = 0
            ORDER BY m.id DESC
            LIMIT ? OFFSET ?
            """,
            (user_key, page_size, offset),
        )
        return _build_photo_items_from_rows(exp, rows)

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
        WHERE p.user_id = ? AND COALESCE(p.is_removed, 0) = 0
        ORDER BY p.created_at DESC, p.id DESC
        LIMIT ? OFFSET ?
        """,
        (user_key, page_size, offset),
    )
    return _build_photo_items_from_rows(exp, rows)


def _photo_post_comments(exp: Exps, photo_id: str, limit: int = 12) -> list[dict]:
    photo_key = str(photo_id or "").strip()
    if not photo_key:
        return []

    rows = _photo_db_rows(
        exp,
        """
        SELECT
            c.*,
            u.username AS commenter_username,
            u.profile_picture_url AS commenter_profile_picture_url,
            u.cover_image AS commenter_cover_image
        FROM comments c
        LEFT JOIN user_mgmt u ON u.id = c.user_id
        WHERE c.photo_id = ? AND COALESCE(c.is_removed, 0) = 0
        ORDER BY COALESCE(c.created_at, c.timestamp, '') DESC, c.id DESC
        LIMIT ?
        """,
        (photo_key, limit),
    )
    comments = []
    for row in rows:
        commenter_id = str(row.get("user_id") or "").strip()
        commenter_name = str(
            row.get("commenter_username") or commenter_id or "Unknown"
        ).strip()
        comments.append(
            {
                "id": row.get("id"),
                "user_id": commenter_id,
                "username": commenter_name,
                "profile_pic": _photo_profile_pic_url(
                    exp,
                    username=commenter_name,
                    user_id=commenter_id,
                    raw_profile_pic=row.get("commenter_profile_picture_url"),
                ),
                "body": row.get("body") or "",
                "created_at": row.get("created_at") or row.get("timestamp") or "",
                "likes": row.get("num_likes") or 0,
            }
        )
    return comments


def _photo_post_likers(exp: Exps, photo_id: str, limit: int = 3) -> list[dict]:
    photo_key = str(photo_id or "").strip()
    if not photo_key:
        return []

    rows = _photo_db_rows(
        exp,
        """
        SELECT
            u.id AS user_id,
            u.username AS username,
            u.profile_picture_url AS profile_picture_url
        FROM reactions r
        LEFT JOIN user_mgmt u ON u.id = r.user_id
        WHERE r.photo_id = ?
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT ?
        """,
        (photo_key, limit),
    )
    likers = []
    for row in rows:
        liker_id = str(row.get("user_id") or "").strip()
        liker_name = str(row.get("username") or liker_id or "Unknown").strip()
        likers.append(
            {
                "id": liker_id,
                "username": liker_name,
                "profile_pic": _photo_profile_pic_url(
                    exp,
                    username=liker_name,
                    user_id=liker_id,
                    raw_profile_pic=row.get("profile_picture_url"),
                ),
            }
        )
    return likers


def _photo_post_details(exp: Exps, photo_id: str) -> dict:
    photo_key = str(photo_id or "").strip()
    if not photo_key:
        return {}

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
        WHERE p.id = ? AND COALESCE(p.is_removed, 0) = 0
        LIMIT 1
        """,
        (photo_key,),
    )
    if not rows:
        return {}

    row = rows[0]
    item = _photo_build_item(exp, row)
    comments = _photo_post_comments(exp, photo_key)
    likers = _photo_post_likers(exp, photo_key)
    likes_count = int(row.get("num_likes") or 0)
    comments_count = int(row.get("num_comments") or len(comments))
    shares_count = int(row.get("num_shares") or 0)
    liked_by_label = ""
    if likers and likes_count > 1:
        liked_by_label = (
            f"Liked by {likers[0]['username']} and {max(0, likes_count - 1)} others"
        )
    elif likers:
        liked_by_label = f"Liked by {likers[0]['username']}"

    return {
        "photo_id": photo_key,
        "author_id": item.get("author_id"),
        "author": item.get("author"),
        "profile_pic": item.get("profile_pic"),
        "display_time": item.get("display_time"),
        "post": item.get("post"),
        "image": item.get("image"),
        "likes": likes_count,
        "comments": comments_count,
        "shares": shares_count,
        "likers": likers,
        "comments_list": comments,
        "likes_label": f"{likes_count} likes",
        "liked_by_label": liked_by_label,
    }


def _photo_profile_totals(exp: Exps, user_id) -> tuple[int, int, int]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return 0, 0, 0

    posts_count_rows = _photo_db_rows(
        exp,
        """
        SELECT COUNT(*) AS total_posts
        FROM photos
        WHERE user_id = ? AND COALESCE(is_removed, 0) = 0
        """,
        (user_key,),
    )
    followers_count, followees_count = _photo_follow_stats(exp, user_key)
    total_posts = (
        int(posts_count_rows[0].get("total_posts") or 0) if posts_count_rows else 0
    )
    return total_posts, followers_count, followees_count


def _photo_connection_items(
    exp: Exps, user_id, kind: str, viewer_id=None
) -> list[dict]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return []

    normalized_kind = str(kind or "").strip().lower()
    latest = _photo_follow_relations(exp)
    if normalized_kind == "followers":
        connection_ids = [
            source_id
            for (source_id, target_id), meta in latest.items()
            if target_id == user_key
            and meta.get("action") == "follow"
            and source_id != user_key
        ]
    else:
        connection_ids = [
            target_id
            for (source_id, target_id), meta in latest.items()
            if source_id == user_key
            and meta.get("action") == "follow"
            and target_id != user_key
        ]

    connection_ids = _photo_ordered_unique_ids(connection_ids)
    if not connection_ids:
        return []

    placeholders = ",".join("?" for _ in connection_ids)
    rows = _photo_db_rows(
        exp,
        f"""
        SELECT
            u.id,
            u.username,
            u.profile_picture_url
        FROM user_mgmt u
        WHERE u.id IN ({placeholders})
        """,
        tuple(connection_ids),
    )
    rows_by_id = {str(row.get("id") or "").strip(): row for row in rows}
    viewer_key = str(viewer_id or "").strip()
    items = []
    for connection_id in connection_ids:
        row = rows_by_id.get(connection_id)
        if not row:
            continue
        username = str(row.get("username") or connection_id).strip()
        viewer_follows = (viewer_key, connection_id) in latest and latest[
            (viewer_key, connection_id)
        ].get("action") == "follow"
        if viewer_key == user_key and normalized_kind == "followers":
            action_label = "Remove"
        elif viewer_key == user_key and normalized_kind == "following":
            action_label = "Unfollow" if viewer_follows else "Follow"
        else:
            action_label = "Following" if viewer_follows else "Follow"
        items.append(
            {
                "id": connection_id,
                "username": username,
                "profile_pic": _photo_profile_pic_url(
                    exp,
                    username=username,
                    user_id=connection_id,
                    raw_profile_pic=row.get("profile_picture_url"),
                ),
                "subtitle": (
                    "Follower" if normalized_kind == "followers" else "Following"
                ),
                "action_label": action_label,
            }
        )
    return items


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


@main.get("/<int:exp_id>/photo/suggestions")
@login_required
def photo_suggestions(exp_id):
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

    logged_user = exp_user
    if logged_user is None:
        try:
            logged_user = User_mgmt.query.filter_by(
                username=current_user.username
            ).first()
        except Exception:
            logged_user = None

    if logged_user is not None:
        logged_id = logged_user.id
    else:
        logged_id = _photo_logged_user_id()
    followed_contact_ids = set(_photo_active_contact_ids(exp, logged_id))
    try:
        suggestions = _photo_suggested_contacts(
            exp,
            logged_user.username if logged_user else current_user.username,
            limit=30,
            exclude_ids=followed_contact_ids | {str(logged_id)},
        )
    except Exception:
        suggestions = []

    return render_template(
        "photo/suggestions.html",
        exp_id=exp_id,
        suggestions=suggestions,
        logged_id=logged_id,
        logged_username=current_user.username,
        profile_pic=_photo_user_avatar_url(logged_id),
        followed_contact_ids=followed_contact_ids,
        photo_active_nav="home",
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
        photo_sidebar_collapsed=True,
    )


@main.get("/<int:exp_id>/photo/profile/<user_id>/<string:mode>/<int:page>")
@login_required
def photo_profile(exp_id, user_id, mode="recent", page=1):
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

    logged_user = exp_user
    if logged_user is None:
        try:
            logged_user = User_mgmt.query.filter_by(
                username=current_user.username
            ).first()
        except Exception:
            logged_user = None

    profile_user = _photo_user_record(exp, user_id)
    if not profile_user:
        try:
            profile_user = _photo_user_record(
                exp, getattr(logged_user, "id", _photo_logged_user_id())
            )
        except Exception:
            profile_user = {}

    if not profile_user:
        return redirect(f"/{exp_id}/photo/feed/all/feed/rf/1")

    profile_user_id = str(profile_user.get("id") or "").strip()
    profile_username = str(
        profile_user.get("username") or profile_user_id or ""
    ).strip()
    logged_id = getattr(logged_user, "id", _photo_logged_user_id())
    profile_pic = _photo_profile_pic_url(
        exp,
        username=profile_username,
        user_id=profile_user_id,
        raw_profile_pic=profile_user.get("profile_picture_url"),
    )

    total_posts, total_followers, total_followees = _photo_profile_totals(
        exp, profile_user_id
    )
    is_following = profile_user_id in set(_photo_active_contact_ids(exp, logged_id))
    can_follow_profile = str(profile_user_id) != str(logged_id)
    active_mode = str(mode or "recent").strip().lower()
    if active_mode not in {"recent", "saved", "tagged"}:
        active_mode = "recent"
    profile_items = _photo_profile_photo_items(
        exp, profile_user_id, active_mode, page, 12
    )
    profile_cover = _photo_media_url(exp, profile_user.get("cover_image"))
    if not profile_cover:
        profile_cover = profile_user.get("cover_image") or ""

    return render_template(
        "photo/profile.html",
        exp_id=exp_id,
        user=profile_user,
        user_id=profile_user_id,
        logged_id=logged_id,
        logged_username=current_user.username,
        profile_pic=profile_pic,
        profile_cover=profile_cover,
        total_posts=total_posts,
        total_followers=total_followers,
        total_followees=total_followees,
        is_following=is_following,
        can_follow_profile=can_follow_profile,
        items=profile_items,
        page=page,
        mode=active_mode,
        photo_active_nav="profile",
        profile_pic_feed=profile_pic,
        is_admin=is_admin(current_user.username),
        enumerate=enumerate,
        len=len,
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
        photo_sidebar_collapsed=True,
        followers_overlay_items=_photo_connection_items(
            exp, profile_user_id, "followers", logged_id
        ),
        following_overlay_items=_photo_connection_items(
            exp, profile_user_id, "following", logged_id
        ),
    )


@main.get("/<int:exp_id>/photo/media/<path:filename>")
@login_required
def photo_media(exp_id, filename):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "photo_sharing":
        abort(404)

    media_root_path = _photo_media_root(exp)
    if media_root_path is None:
        abort(404)
    media_root = str(media_root_path)
    return send_from_directory(media_root, filename)


@main.get("/<int:exp_id>/api/photo/post/<photo_id>")
@login_required
def api_photo_post(exp_id, photo_id):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "photo_sharing":
        return {"ok": False, "error": "not_found"}, 404

    details = _photo_post_details(exp, photo_id)
    if not details:
        return {"ok": False, "error": "not_found"}, 404

    return {"ok": True, "post": details}


@main.get("/<int:exp_id>/api/photo/profile/<user_id>/connections/<kind>")
@login_required
def api_photo_profile_connections(exp_id, user_id, kind):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "photo_sharing":
        return {"ok": False, "error": "not_found"}, 404

    exp_user, _created = ensure_experiment_user(
        exp,
        user_id=getattr(current_user, "id", 0) or 0,
        username=str(current_user.username),
        email=str(getattr(current_user, "email", "") or ""),
        password=str(getattr(current_user, "password", "") or ""),
        joined_on=0,
    )

    viewer_id = getattr(exp_user, "id", _photo_logged_user_id())
    items = _photo_connection_items(exp, user_id, kind, viewer_id)
    return {"ok": True, "kind": kind, "items": items}


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
    active_tab = str(request.args.get("tab", "for_you") or "for_you").strip().lower()
    if active_tab not in {"for_you", "follower"}:
        active_tab = "for_you"

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

    if active_tab == "follower":
        res = _build_photo_follower_items(
            exp,
            exp_user.id if exp_user else _photo_logged_user_id(),
            page,
            max_post_per_page,
        )
    else:
        res = _build_photo_recommended_items(
            exp,
            exp_user.id if exp_user else _photo_logged_user_id(),
            page,
            max_post_per_page,
        )
    if len(res) == 0 and page > 1:
        return redirect(
            f"/{exp_id}/photo/feed/{user_id}/{timeline}/{mode}/{page - 1}?tab={active_tab}"
        )

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
    if not profile_pic:
        profile_pic = _photo_user_avatar_url(
            getattr(logged_user, "id", _photo_logged_user_id())
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
    followed_contact_ids = set(
        _photo_active_contact_ids(
            exp, getattr(logged_user, "id", _photo_logged_user_id())
        )
    )
    suggested_contacts = _photo_suggested_contacts(
        exp,
        logged_user.username if logged_user else current_user.username,
        exclude_ids=followed_contact_ids
        | {str(getattr(logged_user, "id", _photo_logged_user_id()))},
    )

    return render_template(
        "photo/feed.html",
        items=res,
        stories=stories,
        page=page,
        active_tab=active_tab,
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
        suggested_contacts=suggested_contacts,
        followed_contact_ids=followed_contact_ids,
        photo_active_nav="home",
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
        photo_sidebar_collapsed=True,
    )


@main.get(
    "/<int:exp_id>/api/photo/feed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>"
)
@login_required
def api_photo_feed(exp_id, user_id="all", timeline="timeline", mode="rf", page=1):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "photo_sharing":
        return {"html": "", "has_more": False}, 404

    if page < 1:
        page = 1

    max_post_per_page = 10
    active_tab = str(request.args.get("tab", "for_you") or "for_you").strip().lower()
    if active_tab not in {"for_you", "follower"}:
        active_tab = "for_you"

    exp_user, _created = ensure_experiment_user(
        exp,
        user_id=getattr(current_user, "id", 0) or 0,
        username=str(current_user.username),
        email=str(getattr(current_user, "email", "") or ""),
        password=str(getattr(current_user, "password", "") or ""),
        joined_on=0,
    )

    logged_id = exp_user.id if exp_user else _photo_logged_user_id()
    if active_tab == "follower":
        items = _build_photo_follower_items(exp, logged_id, page, max_post_per_page)
        has_more = len(items) >= max_post_per_page
    else:
        items = _build_photo_recommended_items(exp, logged_id, page, max_post_per_page)
        has_more = len(items) >= max_post_per_page

    html = render_template(
        "photo/components/posts.html",
        items=items,
        exp_id=exp_id,
        user_id=user_id,
        enumerate=enumerate,
        len=len,
        active_tab=active_tab,
    )
    return {"html": html, "has_more": has_more}
