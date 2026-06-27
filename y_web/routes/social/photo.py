"""
Photo sharing platform routes.

Provides an Instagram-like feed for YPhotoSharing experiments while keeping the
same routing conventions used by the microblogging and forum frontends.
"""

import hashlib
import html
import json
import os
import mimetypes
import sqlite3
import re
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

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
from y_web.src.models.experiment import Rounds
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


def _photo_latest_round_id() -> str:
    current_round = Rounds.query.order_by(Rounds.day.desc(), Rounds.hour.desc()).first()
    if current_round is not None and getattr(current_round, "id", None) is not None:
        return str(current_round.id)
    return "1"


def _photo_media_root(exp: Exps) -> Optional[Path]:
    db_path = _photo_db_path(exp)
    if not db_path:
        return None
    return Path(db_path).parent / "media"


def _photo_store_uploaded_media(exp: Exps, upload_file) -> tuple[str, str]:
    media_root = _photo_media_root(exp)
    if media_root is None:
        raise ValueError("media_root_unavailable")

    media_root.mkdir(parents=True, exist_ok=True)

    original_name = secure_filename(getattr(upload_file, "filename", "") or "photo")
    suffix = Path(original_name).suffix.lower()
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}
    if suffix not in allowed_suffixes:
        guessed = mimetypes.guess_extension(getattr(upload_file, "mimetype", "") or "")
        if guessed in {".jpe", ".jpeg"}:
            suffix = ".jpg"
        elif guessed in allowed_suffixes:
            suffix = guessed
        else:
            suffix = ".jpg"

    filename = f"{uuid.uuid4()}{suffix}"
    file_path = media_root / filename
    upload_file.save(file_path)
    media_url = f"/{exp.idexp}/photo/media/{filename}"
    return str(file_path), media_url


def _photo_media_url(exp: Exps, raw_url: Optional[str]) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/static/") or value.startswith("/assets/"):
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


def _photo_profile_href(exp: Exps, user_id) -> str:
    user_key = quote(str(user_id or "").strip(), safe="")
    if not user_key:
        return ""
    return f"/{exp.idexp}/photo/profile/{user_key}/recent/1"


def _photo_search_hashtag_href(exp: Exps, hashtag: str) -> str:
    tag = str(hashtag or "").strip().lstrip("#")
    if not tag:
        return ""
    return f"/{exp.idexp}/photo/search?q=%23{quote(tag, safe='')}&kind=hashtags"


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
    is_page: int = 0,
) -> str:
    value = _photo_media_url(exp, raw_profile_pic)
    if value:
        return value

    safe_profile_pic = get_safe_profile_pic(username, 1 if int(is_page or 0) == 1 else 0)
    value = _photo_media_url(exp, safe_profile_pic)
    if value:
        return value

    return _photo_user_avatar_url(user_id or username)


def _photo_story_image_urls(exp: Exps, row: dict) -> list[str]:
    raw_urls = row.get("image_urls")
    parsed_urls: list[str] = []
    if isinstance(raw_urls, str) and raw_urls.strip():
        try:
            loaded = json.loads(raw_urls)
        except json.JSONDecodeError:
            loaded = [raw_urls]
        if isinstance(loaded, list):
            parsed_urls = [str(item).strip() for item in loaded if str(item).strip()]
        elif loaded:
            parsed_urls = [str(loaded).strip()]
    elif isinstance(raw_urls, list):
        parsed_urls = [str(item).strip() for item in raw_urls if str(item).strip()]

    if not parsed_urls:
        fallback_url = _photo_media_url(exp, row.get("media_url"))
        if fallback_url:
            parsed_urls = [fallback_url]

    return [_photo_media_url(exp, url) for url in parsed_urls if _photo_media_url(exp, url)]


def _photo_story_payload(exp: Exps, row: dict, *, user_id: str, author_name: str, index: int = 0) -> dict:
    story_id = str(row.get("id") or "").strip()
    image_urls = _photo_story_image_urls(exp, row)
    preview_url = image_urls[0] if image_urls else _photo_media_url(exp, row.get("media_url"))
    if not story_id or not preview_url:
        return {}

    title = str(row.get("title") or row.get("caption") or "Story").strip()
    description = str(row.get("description") or row.get("caption") or title).strip()
    return {
        "id": story_id,
        "story_id": story_id,
        "user_id": str(user_id or "").strip(),
        "username": author_name,
        "profile_pic": _photo_profile_pic_url(
            exp,
            username=author_name,
            user_id=user_id,
            raw_profile_pic=row.get("author_profile_picture_url"),
            is_page=int(row.get("author_is_page") or 0),
        ),
        "title": title,
        "description": description,
        "caption": _photo_linkify_text(exp, row.get("caption") or ""),
        "image_urls": image_urls,
        "image": {
            "url": preview_url,
            "description": description or title,
        },
        "display_time": _format_photo_time(row.get("created_at")),
        "view_count": int(row.get("view_count") or 0),
        "duration_seconds": int(row.get("duration_seconds") or 5),
        "index": index,
    }


def _photo_story_viewed_ids(exp: Exps, viewer_id) -> set[str]:
    viewer_key = str(viewer_id or "").strip()
    if not viewer_key:
        return set()

    rows = _photo_db_rows(
        exp,
        """
        SELECT DISTINCT story_id
        FROM story_views
        WHERE viewer_id = ?
        """,
        (viewer_key,),
    )
    return {str(row.get("story_id") or "").strip() for row in rows if str(row.get("story_id") or "").strip()}


def _photo_sidebar_context(
    exp: Exps,
    *,
    logged_user,
    logged_id,
    photo_home_url: str,
    photo_active_nav: str,
    photo_sidebar_collapsed: bool = True,
) -> dict:
    raw_profile_pic = getattr(logged_user, "profile_picture_url", "") if logged_user else ""
    is_page = getattr(logged_user, "is_page", 0) if logged_user else 0
    profile_pic = get_safe_profile_pic(current_user.username, is_page) or _photo_profile_pic_url(
        exp,
        username=str(current_user.username),
        user_id=logged_id,
        raw_profile_pic=raw_profile_pic,
        is_page=is_page,
    )
    return {
        "logged_id": logged_id,
        "logged_username": str(current_user.username),
        "photo_home_url": photo_home_url,
        "profile_pic": profile_pic,
        "sidebar_profile_pic": profile_pic,
        "is_admin": is_admin(current_user.username),
        "photo_active_nav": photo_active_nav,
        "photo_sidebar_collapsed": photo_sidebar_collapsed,
    }


def _photo_user_href_by_name(exp: Exps, username: str) -> str:
    user_key = str(username or "").strip()
    if not user_key:
        return ""
    record = _photo_user_record(exp, user_key)
    target_id = str(record.get("id") or "").strip()
    if not target_id:
        return ""
    return _photo_profile_href(exp, target_id)


_PHOTO_LINK_PATTERN = re.compile(r"(?<![\w/])(@[A-Za-z0-9_.]+|#[A-Za-z0-9_]+)")


def _photo_linkify_text(exp: Exps, text) -> str:
    raw_text = str(text or "")
    if not raw_text:
        return ""

    parts = []
    last_index = 0
    for match in _PHOTO_LINK_PATTERN.finditer(raw_text):
        start, end = match.span()
        if start > last_index:
            parts.append(html.escape(raw_text[last_index:start]))

        token = match.group(0)
        if token.startswith("@"):
            mention_name = token[1:]
            href = _photo_user_href_by_name(exp, mention_name)
            if href:
                parts.append(
                    f'<a class="photo-inline-link" href="{html.escape(href, quote=True)}">@{html.escape(mention_name)}</a>'
                )
            else:
                parts.append(html.escape(token))
        else:
            tag_name = token[1:]
            href = _photo_search_hashtag_href(exp, tag_name)
            if href:
                parts.append(
                    f'<a class="photo-inline-link" href="{html.escape(href, quote=True)}">#{html.escape(tag_name)}</a>'
                )
            else:
                parts.append(html.escape(token))
        last_index = end

    if last_index < len(raw_text):
        parts.append(html.escape(raw_text[last_index:]))

    return "".join(parts).replace("\n", "<br/>")


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
    author_name = str(row.get("author_username") or "").strip() or author_id or "Unknown"
    author_is_page = int(row.get("author_is_page") or 0)
    parent_photo_id = str(row.get("parent_photo_id") or "").strip()
    shared_from = -1
    if parent_photo_id:
        shared_from = [
            parent_photo_id,
            str(row.get("parent_author_username") or row.get("parent_author") or "Shared post").strip(),
        ]
    return {
        "post_id": row.get("id"),
        "author_id": author_id,
        "author": author_name,
        "author_href": _photo_profile_href(exp, author_id),
        "profile_pic": _photo_profile_pic_url(
            exp,
            username=author_name,
            user_id=author_id,
            raw_profile_pic=row.get("author_profile_picture_url"),
            is_page=author_is_page,
        ),
        "display_time": _format_photo_time(row.get("created_at")),
        "thread_id": row.get("id"),
        "post": (row.get("caption") or row.get("alt_text") or ""),
        "post_html": _photo_linkify_text(exp, row.get("caption") or row.get("alt_text") or ""),
        "image": {
            "url": _photo_media_url(exp, raw_media),
            "description": row.get("caption") or row.get("alt_text") or "",
        },
        "likes": row.get("num_likes") or 0,
        "t_comments": row.get("num_comments") or 0,
        "is_shared": row.get("num_shares") or 0,
        "shared_from": shared_from,
        "is_liked": bool(row.get("is_liked")),
        "is_bookmarked": bool(row.get("is_bookmarked")),
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


def _photo_viewer_photo_state(exp: Exps, photo_id: str, viewer_id) -> dict:
    viewer_key = str(viewer_id or "").strip()
    photo_key = str(photo_id or "").strip()
    if not viewer_key or not photo_key:
        return {"is_liked": False, "is_bookmarked": False}

    liked_rows = _photo_db_rows(
        exp,
        """
        SELECT id, reaction_type
        FROM reactions
        WHERE user_id = ? AND photo_id = ?
        LIMIT 1
        """,
        (viewer_key, photo_key),
    )
    bookmarked_rows = _photo_db_rows(
        exp,
        """
        SELECT id
        FROM saved_photos
        WHERE user_id = ? AND photo_id = ?
        LIMIT 1
        """,
        (viewer_key, photo_key),
    )
    return {
        "is_liked": bool(liked_rows),
        "is_bookmarked": bool(bookmarked_rows),
    }


def _build_photo_items_from_rows(exp: Exps, rows: list[dict], viewer_id=None) -> list[dict]:
    items = []
    for row in rows:
        item = _photo_build_item(exp, row)
        item.update(_photo_viewer_photo_state(exp, item.get("post_id"), viewer_id))
        items.append(item)
    return items


def _build_photo_items(exp: Exps, page: int, page_size: int, viewer_id=None) -> list[dict]:
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
    return _build_photo_items_from_rows(exp, rows, viewer_id=viewer_id)


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
    return _build_photo_items_from_rows(exp, ordered_rows, viewer_id=logged_user_id)


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
    return _build_photo_items_from_rows(exp, rows, viewer_id=logged_user_id)


def _build_photo_story_previews(
    exp: Exps,
    viewer_id,
    fallback_users,
    limit: int = 8,
    allowed_author_ids: Optional[list[str]] = None,
):
    viewer_key = str(viewer_id or "").strip()
    viewed_story_ids = _photo_story_viewed_ids(exp, viewer_key)
    author_ids = None
    if allowed_author_ids is not None:
        author_ids = [str(author_id or "").strip() for author_id in allowed_author_ids if str(author_id or "").strip()]
        if not author_ids:
            return []
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
        LEFT JOIN story_views sv
            ON sv.story_id = s.id
           AND sv.viewer_id = ?
        WHERE sv.story_id IS NULL
        {author_clause}
        ORDER BY s.created_at DESC, s.id DESC
        """.format(
            author_clause=(
                "AND s.user_id IN ({})".format(",".join("?" for _ in author_ids))
                if author_ids is not None
                else ""
            )
        ),
        tuple([viewer_key] + author_ids) if author_ids is not None else (viewer_key,),
    )

    stories = []
    seen_ids = set()
    for row in rows:
        user_id = str(row.get("user_id") or "")
        story_id = str(row.get("id") or "").strip()
        if not user_id or user_id in seen_ids or not story_id or story_id in viewed_story_ids:
            continue
        seen_ids.add(user_id)
        author_name = row.get("author_username") or user_id
        payload = _photo_story_payload(
            exp,
            row,
            user_id=user_id,
            author_name=author_name,
        )
        if not payload:
            continue
        payload["label"] = "Recent story"
        stories.append(payload)
        if len(stories) >= limit:
            return stories

    return stories


def _photo_profile_story_items(exp: Exps, user_id, limit: int = 12) -> list[dict]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return []

    rows = _photo_db_rows(
        exp,
        """
        SELECT
            s.*,
            u.username AS author_username,
            u.profile_picture_url AS author_profile_picture_url,
            u.cover_image AS author_cover_image,
            u.is_page AS author_is_page
        FROM stories s
        LEFT JOIN user_mgmt u ON u.id = s.user_id
        WHERE s.user_id = ?
        ORDER BY s.created_at DESC, s.id DESC
        LIMIT ?
        """,
        (user_key, limit),
    )
    items = []
    for index, row in enumerate(rows):
        author_name = str(row.get("author_username") or user_key).strip() or user_key
        payload = _photo_story_payload(
            exp,
            row,
            user_id=user_key,
            author_name=author_name,
            index=index,
        )
        if payload:
            items.append(payload)
    return items


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
                        is_page=int(getattr(row, "is_page", 0) or 0),
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
    exp: Exps, user_id, mode: str, page: int, page_size: int, viewer_id=None
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
        return _build_photo_items_from_rows(exp, rows, viewer_id=viewer_id or user_key)

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
        return _build_photo_items_from_rows(exp, rows, viewer_id=viewer_id or user_key)

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
    return _build_photo_items_from_rows(exp, rows, viewer_id=viewer_id or user_key)


def _photo_post_comment_rows(exp: Exps, photo_id: str, limit: int = 12) -> list[dict]:
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
            u.cover_image AS commenter_cover_image,
            u.is_page AS commenter_is_page
        FROM comments c
        LEFT JOIN user_mgmt u ON u.id = c.user_id
        WHERE c.photo_id = ? AND COALESCE(c.is_removed, 0) = 0
        ORDER BY COALESCE(c.created_at, c.timestamp, '') DESC, c.id DESC
        LIMIT ?
        """,
        (photo_key, limit),
    )
    return rows


def _photo_comment_payload(exp: Exps, row: dict) -> dict:
    commenter_id = str(row.get("user_id") or "").strip()
    commenter_name = str(row.get("commenter_username") or commenter_id or "Unknown").strip()
    body = str(row.get("body") or "").strip()
    return {
        "id": row.get("id"),
        "user_id": commenter_id,
        "username": commenter_name,
        "user_href": _photo_profile_href(exp, commenter_id),
        "profile_pic": _photo_profile_pic_url(
            exp,
            username=commenter_name,
            user_id=commenter_id,
            raw_profile_pic=row.get("commenter_profile_picture_url"),
            is_page=int(row.get("commenter_is_page") or 0),
        ),
        "body": body,
        "body_html": _photo_linkify_text(exp, body),
        "created_at": row.get("created_at") or row.get("timestamp") or "",
        "likes": row.get("num_likes") or 0,
        "parent_comment_id": row.get("parent_comment_id"),
        "replies": [],
        "reply_count": int(row.get("reply_count") or 0),
    }


def _photo_post_comment_tree(exp: Exps, photo_id: str, limit: int = 200) -> list[dict]:
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
            u.cover_image AS commenter_cover_image,
            u.is_page AS commenter_is_page
        FROM comments c
        LEFT JOIN user_mgmt u ON u.id = c.user_id
        WHERE c.photo_id = ? AND COALESCE(c.is_removed, 0) = 0
        ORDER BY COALESCE(c.created_at, c.timestamp, '') ASC, c.id ASC
        LIMIT ?
        """,
        (photo_key, limit),
    )
    if not rows:
        return []

    nodes: dict[str, dict] = {}
    roots: list[dict] = []
    for row in rows:
        payload = _photo_comment_payload(exp, row)
        comment_id = str(payload.get("id") or "").strip()
        if not comment_id:
            continue
        nodes[comment_id] = payload

    for row in rows:
        payload = nodes.get(str(row.get("id") or "").strip())
        if not payload:
            continue
        parent_id = str(row.get("parent_comment_id") or "").strip()
        if parent_id and parent_id in nodes:
            parent = nodes[parent_id]
            parent["replies"].append(payload)
            parent["reply_count"] = len(parent["replies"])
        else:
            roots.append(payload)

    return roots


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
    item.update(_photo_viewer_photo_state(exp, photo_key, _photo_logged_user_id()))
    comments = _photo_post_comment_tree(exp, photo_key)
    likers = _photo_post_likers(exp, photo_key)
    likes_count = int(row.get("num_likes") or 0)
    comments_count = int(row.get("num_comments") or 0)
    if not comments_count:
        comments_count = len(_photo_db_rows(
            exp,
            """
            SELECT id FROM comments
            WHERE photo_id = ? AND COALESCE(is_removed, 0) = 0
            """,
            (photo_key,),
        ))
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
        "author_href": item.get("author_href"),
        "profile_pic": item.get("profile_pic"),
        "display_time": item.get("display_time"),
        "post": item.get("post"),
        "post_html": item.get("post_html"),
        "image": item.get("image"),
        "likes": likes_count,
        "comments": comments_count,
        "shares": shares_count,
        "likers": likers,
        "comments_list": comments,
        "likes_label": f"{likes_count} likes",
        "liked_by_label": liked_by_label,
        "is_liked": bool(item.get("is_liked")),
        "is_bookmarked": bool(item.get("is_bookmarked")),
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
            u.profile_picture_url,
            u.is_page
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
                    is_page=int(row.get("is_page") or 0),
                ),
                "subtitle": (
                    "Follower" if normalized_kind == "followers" else "Following"
                ),
                "action_label": action_label,
            }
        )
    return items


def _photo_search_recent_photo_rows(exp: Exps, limit: int = 24) -> list[dict]:
    return _photo_db_rows(
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
        LIMIT ?
        """,
        (limit,),
    )


def _photo_search_user_rows(exp: Exps, query: str, limit: int = 12) -> list[dict]:
    normalized_query = str(query or "").strip().lower()
    if normalized_query:
        like = f"%{normalized_query}%"
        return _photo_db_rows(
            exp,
            """
            SELECT
                u.id,
                u.username,
                u.profile_picture_url,
                u.cover_image,
                u.is_page,
                COUNT(DISTINCT p.id) AS photo_count
            FROM user_mgmt u
            LEFT JOIN photos p ON p.user_id = u.id AND COALESCE(p.is_removed, 0) = 0
            WHERE LOWER(COALESCE(u.username, '')) LIKE ?
               OR LOWER(COALESCE(u.id, '')) LIKE ?
            GROUP BY u.id, u.username, u.profile_picture_url, u.cover_image, u.is_page
            ORDER BY photo_count DESC, u.username ASC
            LIMIT ?
            """,
            (like, like, limit),
        )

    return _photo_db_rows(
        exp,
        """
        SELECT
            u.id,
            u.username,
            u.profile_picture_url,
            u.cover_image,
            u.is_page,
            COUNT(DISTINCT p.id) AS photo_count
        FROM user_mgmt u
        LEFT JOIN photos p ON p.user_id = u.id AND COALESCE(p.is_removed, 0) = 0
        GROUP BY u.id, u.username, u.profile_picture_url, u.cover_image, u.is_page
        ORDER BY photo_count DESC, u.username ASC
        LIMIT ?
        """,
        (limit,),
    )


def _photo_search_hashtag_rows(exp: Exps, query: str, limit: int = 12) -> list[dict]:
    normalized_query = str(query or "").strip().lower().lstrip("#")
    if normalized_query:
        like = f"%{normalized_query}%"
        return _photo_db_rows(
            exp,
            """
            SELECT
                h.id,
                h.hashtag,
                COUNT(ph.photo_id) AS photo_count
            FROM hashtags h
            LEFT JOIN photo_hashtags ph ON ph.hashtag_id = h.id
            WHERE LOWER(COALESCE(h.hashtag, '')) LIKE ?
            GROUP BY h.id, h.hashtag
            ORDER BY photo_count DESC, h.hashtag ASC
            LIMIT ?
            """,
            (like, limit),
        )

    return _photo_db_rows(
        exp,
        """
        SELECT
            h.id,
            h.hashtag,
            COUNT(ph.photo_id) AS photo_count
        FROM hashtags h
        LEFT JOIN photo_hashtags ph ON ph.hashtag_id = h.id
        GROUP BY h.id, h.hashtag
        ORDER BY photo_count DESC, h.hashtag ASC
        LIMIT ?
        """,
        (limit,),
    )


def _photo_search_photo_rows(exp: Exps, query: str, limit: int = 24) -> list[dict]:
    normalized_query = str(query or "").strip().lower().lstrip("#")
    if normalized_query:
        like = f"%{normalized_query}%"
        return _photo_db_rows(
            exp,
            """
            SELECT DISTINCT
                p.*,
                u.username AS author_username,
                u.profile_picture_url AS author_profile_picture_url,
                u.cover_image AS author_cover_image,
                u.is_page AS author_is_page
            FROM photos p
            LEFT JOIN user_mgmt u ON u.id = p.user_id
            LEFT JOIN photo_hashtags ph ON ph.photo_id = p.id
            LEFT JOIN hashtags h ON h.id = ph.hashtag_id
            WHERE COALESCE(p.is_removed, 0) = 0
              AND (
                    LOWER(COALESCE(p.caption, '')) LIKE ?
                 OR LOWER(COALESCE(p.alt_text, '')) LIKE ?
                 OR LOWER(COALESCE(p.location_name, '')) LIKE ?
                 OR LOWER(COALESCE(u.username, '')) LIKE ?
                 OR LOWER(COALESCE(h.hashtag, '')) LIKE ?
              )
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT ?
            """,
            (like, like, like, like, like, limit),
        )

    return _photo_search_recent_photo_rows(exp, limit=limit)


def _photo_search_payload(exp: Exps, query: str, kind: str, logged_id, *, limit: int = 24) -> dict:
    normalized_query = str(query or "").strip()
    normalized_kind = str(kind or "all").strip().lower()
    if normalized_kind not in {"all", "photos", "users", "hashtags"}:
        normalized_kind = "all"

    photo_rows = _photo_search_photo_rows(exp, normalized_query, limit=limit)
    user_rows = _photo_search_user_rows(exp, normalized_query, limit=max(8, limit // 2))
    hashtag_rows = _photo_search_hashtag_rows(exp, normalized_query, limit=max(8, limit // 2))

    photo_items = _build_photo_items_from_rows(exp, photo_rows)
    user_items = []
    for row in user_rows:
        user_id = str(row.get("id") or "").strip()
        username = str(row.get("username") or user_id or "").strip()
        if not user_id:
            continue
        user_items.append(
            {
                "id": user_id,
                "username": username,
                "profile_pic": _photo_profile_pic_url(
                    exp,
                    username=username,
                    user_id=user_id,
                    raw_profile_pic=row.get("profile_picture_url"),
                    is_page=int(row.get("is_page") or 0),
                ),
                "photo_count": int(row.get("photo_count") or 0),
                "kind": "page" if int(row.get("is_page") or 0) == 1 else "user",
            }
        )

    hashtag_items = []
    for row in hashtag_rows:
        tag = str(row.get("hashtag") or "").strip()
        if not tag:
            continue
        hashtag_items.append(
            {
                "id": row.get("id"),
                "hashtag": tag,
                "photo_count": int(row.get("photo_count") or 0),
            }
        )

    if not normalized_query and not photo_items:
        photo_items = _build_photo_items_from_rows(exp, _photo_search_recent_photo_rows(exp, limit=limit))

    return {
        "query": normalized_query,
        "kind": normalized_kind,
        "photos": photo_items,
        "users": user_items,
        "hashtags": hashtag_items,
        "counts": {
            "photos": len(photo_items),
            "users": len(user_items),
            "hashtags": len(hashtag_items),
        },
        "logged_id": str(logged_id or ""),
    }


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
        followed_contact_ids=followed_contact_ids,
        **_photo_sidebar_context(
            exp,
            logged_user=logged_user,
            logged_id=logged_id,
            photo_home_url=f"/{exp_id}/photo/feed/all/feed/rf/1",
            photo_active_nav="home",
        ),
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
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
        is_page=int(profile_user.get("is_page") or 0),
    )
    sidebar_profile_pic = get_safe_profile_pic(
        current_user.username, getattr(logged_user, "is_page", 0) if logged_user else 0
    ) or _photo_profile_pic_url(
        exp,
        username=str(current_user.username),
        user_id=getattr(logged_user, "id", _photo_logged_user_id()),
        raw_profile_pic=getattr(logged_user, "profile_picture_url", "") if logged_user else "",
        is_page=getattr(logged_user, "is_page", 0) if logged_user else 0,
    )

    total_posts, total_followers, total_followees = _photo_profile_totals(
        exp, profile_user_id
    )
    is_following = profile_user_id in set(_photo_active_contact_ids(exp, logged_id))
    can_follow_profile = str(profile_user_id) != str(logged_id)
    active_mode = str(mode or "recent").strip().lower()
    if active_mode not in {"recent", "saved", "tagged"}:
        active_mode = "recent"
    profile_items = _photo_profile_photo_items(exp, profile_user_id, active_mode, page, 12, viewer_id=logged_id)
    profile_cover = _photo_media_url(exp, profile_user.get("cover_image"))
    if not profile_cover:
        profile_cover = profile_user.get("cover_image") or ""
    profile_stories = _photo_profile_story_items(exp, profile_user_id, limit=12)
    is_self_profile = str(profile_user_id) == str(logged_id)

    return render_template(
        "photo/profile.html",
        exp_id=exp_id,
        user=profile_user,
        user_id=profile_user_id,
        profile_cover=profile_cover,
        profile_stories=profile_stories,
        is_self_profile=is_self_profile,
        total_posts=total_posts,
        total_followers=total_followers,
        total_followees=total_followees,
        is_following=is_following,
        can_follow_profile=can_follow_profile,
        items=profile_items,
        page=page,
        mode=active_mode,
        profile_pic_feed=profile_pic,
        enumerate=enumerate,
        len=len,
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
        followers_overlay_items=_photo_connection_items(
            exp, profile_user_id, "followers", logged_id
        ),
        following_overlay_items=_photo_connection_items(
            exp, profile_user_id, "following", logged_id
        ),
        **_photo_sidebar_context(
            exp,
            logged_user=logged_user,
            logged_id=logged_id,
            photo_home_url=f"/{exp_id}/photo/feed/all/feed/rf/1",
            photo_active_nav="profile",
        ),
    )


@main.get("/<int:exp_id>/photo/search")
@login_required
def photo_search(exp_id):
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

    logged_id = getattr(logged_user, "id", _photo_logged_user_id())
    query = str(request.args.get("q", "") or "").strip()
    kind = str(request.args.get("kind", "all") or "all").strip().lower()
    payload = _photo_search_payload(exp, query, kind, logged_id, limit=24)

    return render_template(
        "photo/search.html",
        exp_id=exp_id,
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
        search_query=payload["query"],
        search_kind=payload["kind"],
        search_photos=payload["photos"],
        search_users=payload["users"],
        search_hashtags=payload["hashtags"],
        search_counts=payload["counts"],
        **_photo_sidebar_context(
            exp,
            logged_user=logged_user,
            logged_id=logged_id,
            photo_home_url=f"/{exp_id}/photo/feed/all/feed/rf/1",
            photo_active_nav="search",
        ),
    )


@main.get("/<int:exp_id>/api/photo/search")
@login_required
def api_photo_search(exp_id):
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

    logged_user = exp_user
    if logged_user is None:
        try:
            logged_user = User_mgmt.query.filter_by(
                username=current_user.username
            ).first()
        except Exception:
            logged_user = None

    logged_id = getattr(logged_user, "id", _photo_logged_user_id())
    query = str(request.args.get("q", "") or "").strip()
    kind = str(request.args.get("kind", "all") or "all").strip().lower()
    payload = _photo_search_payload(exp, query, kind, logged_id, limit=24)
    payload["ok"] = True
    return payload


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

    exp_user, _created = ensure_experiment_user(
        exp,
        user_id=getattr(current_user, "id", 0) or 0,
        username=str(current_user.username),
        email=str(getattr(current_user, "email", "") or ""),
        password=str(getattr(current_user, "password", "") or ""),
        joined_on=0,
    )
    viewer_id = getattr(exp_user, "id", _photo_logged_user_id())
    details = _photo_post_details(exp, photo_id)
    if not details:
        return {"ok": False, "error": "not_found"}, 404

    viewer_state = _photo_viewer_photo_state(exp, photo_id, viewer_id)
    details["is_liked"] = viewer_state.get("is_liked", False)
    details["is_bookmarked"] = viewer_state.get("is_bookmarked", False)
    return {"ok": True, "post": details}


@main.post("/<int:exp_id>/api/photo/post/<photo_id>/comments")
@login_required
def api_photo_create_comment(exp_id, photo_id):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "photo_sharing":
        return {"ok": False, "error": "not_found"}, 404

    payload = request.get_json(silent=True) or request.form.to_dict(flat=True)
    body = str(payload.get("body") or "").strip()
    if not body:
        return {"ok": False, "error": "empty_body"}, 400

    parent_comment_id = str(payload.get("parent_comment_id") or "").strip() or None

    exp_user, _created = ensure_experiment_user(
        exp,
        user_id=getattr(current_user, "id", 0) or 0,
        username=str(current_user.username),
        email=str(getattr(current_user, "email", "") or ""),
        password=str(getattr(current_user, "password", "") or ""),
        joined_on=0,
    )
    commenter_id = str(getattr(exp_user, "id", _photo_logged_user_id()) or "").strip()
    if not commenter_id:
        return {"ok": False, "error": "missing_user"}, 400

    round_id = str(_photo_latest_round_id()).strip()
    db_path = _photo_db_path(exp)
    if not db_path:
        return {"ok": False, "error": "database_unavailable"}, 500

    comment_id = str(uuid.uuid4())
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO comments (
                id, photo_id, user_id, parent_comment_id, body, sentiment_score,
                num_likes, is_deleted, round, timestamp, is_removed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (
                comment_id,
                str(photo_id),
                commenter_id,
                parent_comment_id,
                body,
                None,
                0,
                0,
                round_id,
                0,
            ),
        )
        conn.execute(
            """
            UPDATE photos
            SET num_comments = COALESCE(num_comments, 0) + 1
            WHERE id = ?
            """,
            (str(photo_id),),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT
                c.*,
                u.username AS commenter_username,
                u.profile_picture_url AS commenter_profile_picture_url,
                u.cover_image AS commenter_cover_image,
                u.is_page AS commenter_is_page
            FROM comments c
            LEFT JOIN user_mgmt u ON u.id = c.user_id
            WHERE c.id = ?
            LIMIT 1
            """,
            (comment_id,),
        ).fetchone()

    if row is None:
        return {"ok": False, "error": "comment_not_created"}, 500

    comment = _photo_comment_payload(exp, dict(row))
    comments_count = _photo_db_rows(
        exp,
        """
        SELECT COALESCE(num_comments, 0) AS num_comments
        FROM photos
        WHERE id = ?
        LIMIT 1
        """,
        (str(photo_id),),
    )
    return {
        "ok": True,
        "photo_id": str(photo_id),
        "comment": comment,
        "comments": int(comments_count[0].get("num_comments") or 0) if comments_count else 0,
    }


@main.post("/<int:exp_id>/api/photo/post/<photo_id>/like")
@login_required
def api_photo_toggle_like(exp_id, photo_id):
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
    viewer_id = str(getattr(exp_user, "id", _photo_logged_user_id()) or "").strip()
    if not viewer_id:
        return {"ok": False, "error": "missing_user"}, 400

    photo_key = str(photo_id or "").strip()
    db_path = _photo_db_path(exp)
    if not db_path:
        return {"ok": False, "error": "database_unavailable"}, 500

    liked = False
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        photo = conn.execute(
            """
            SELECT id, COALESCE(num_likes, 0) AS num_likes
            FROM photos
            WHERE id = ?
            LIMIT 1
            """,
            (photo_key,),
        ).fetchone()
        if photo is None:
            return {"ok": False, "error": "not_found"}, 404

        reaction = conn.execute(
            """
            SELECT id, reaction_type
            FROM reactions
            WHERE user_id = ? AND photo_id = ?
            LIMIT 1
            """,
            (viewer_id, photo_key),
        ).fetchone()

        if reaction is not None and str(reaction["reaction_type"] or "").upper() == "LIKE":
            conn.execute("DELETE FROM reactions WHERE id = ?", (reaction["id"],))
            conn.execute(
                """
                UPDATE photos
                SET num_likes = CASE WHEN COALESCE(num_likes, 0) > 0 THEN num_likes - 1 ELSE 0 END
                WHERE id = ?
                """,
                (photo_key,),
            )
            liked = False
        elif reaction is not None:
            conn.execute(
                """
                UPDATE reactions
                SET reaction_type = 'LIKE', round = ?
                WHERE id = ?
                """,
                (str(_photo_latest_round_id()), reaction["id"]),
            )
            liked = True
        else:
            conn.execute(
                """
                INSERT INTO reactions (id, user_id, photo_id, reaction_type, round, created_at)
                VALUES (?, ?, ?, 'LIKE', ?, CURRENT_TIMESTAMP)
                """,
                (str(uuid.uuid4()), viewer_id, photo_key, str(_photo_latest_round_id())),
            )
            conn.execute(
                """
                UPDATE photos
                SET num_likes = COALESCE(num_likes, 0) + 1
                WHERE id = ?
                """,
                (photo_key,),
            )
            liked = True

        conn.commit()
        updated = conn.execute(
            """
            SELECT COALESCE(num_likes, 0) AS num_likes
            FROM photos
            WHERE id = ?
            LIMIT 1
            """,
            (photo_key,),
        ).fetchone()

    return {
        "ok": True,
        "photo_id": photo_key,
        "liked": liked,
        "likes": int(updated["num_likes"] or 0) if updated else 0,
    }


@main.post("/<int:exp_id>/api/photo/post/<photo_id>/bookmark")
@login_required
def api_photo_toggle_bookmark(exp_id, photo_id):
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
    viewer_id = str(getattr(exp_user, "id", _photo_logged_user_id()) or "").strip()
    if not viewer_id:
        return {"ok": False, "error": "missing_user"}, 400

    photo_key = str(photo_id or "").strip()
    db_path = _photo_db_path(exp)
    if not db_path:
        return {"ok": False, "error": "database_unavailable"}, 500

    bookmarked = False
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            """
            SELECT id
            FROM saved_photos
            WHERE user_id = ? AND photo_id = ?
            LIMIT 1
            """,
            (viewer_id, photo_key),
        ).fetchone()
        if existing is not None:
            conn.execute("DELETE FROM saved_photos WHERE id = ?", (existing["id"],))
            bookmarked = False
        else:
            conn.execute(
                """
                INSERT INTO saved_photos (id, user_id, photo_id, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (str(uuid.uuid4()), viewer_id, photo_key),
            )
            bookmarked = True
        conn.commit()

    return {
        "ok": True,
        "photo_id": photo_key,
        "bookmarked": bookmarked,
    }


@main.post("/<int:exp_id>/api/photo/post/<photo_id>/share")
@login_required
def api_photo_share_post(exp_id, photo_id):
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
    viewer_id = str(getattr(exp_user, "id", _photo_logged_user_id()) or "").strip()
    if not viewer_id:
        return {"ok": False, "error": "missing_user"}, 400

    photo_key = str(photo_id or "").strip()
    db_path = _photo_db_path(exp)
    if not db_path:
        return {"ok": False, "error": "database_unavailable"}, 500

    round_id = _photo_latest_round_id()
    new_photo_id = str(uuid.uuid4())
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        original = conn.execute(
            """
            SELECT
                p.*,
                u.username AS author_username,
                u.profile_picture_url AS author_profile_picture_url,
                u.cover_image AS author_cover_image,
                u.is_page AS author_is_page
            FROM photos p
            LEFT JOIN user_mgmt u ON u.id = p.user_id
            WHERE p.id = ?
            LIMIT 1
            """,
            (photo_key,),
        ).fetchone()
        if original is None:
            return {"ok": False, "error": "not_found"}, 404

        conn.execute(
            """
            INSERT INTO photos (
                id, user_id, round, image_url, thumbnail_url, caption, alt_text,
                filter_name, location_name, latitude, longitude, is_carousel,
                carousel_index, parent_photo_id, num_likes, num_comments,
                num_shares, is_sponsored, embedding, aesthetic_score,
                viral_score, sentiment_score, is_removed, media_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_photo_id,
                viewer_id,
                round_id,
                original["image_url"],
                original["thumbnail_url"] or original["image_url"],
                original["caption"],
                original["alt_text"],
                original["filter_name"],
                original["location_name"],
                original["latitude"],
                original["longitude"],
                original["is_carousel"],
                original["carousel_index"] or 0,
                photo_key,
                0,
                0,
                0,
                original["is_sponsored"] or 0,
                original["embedding"],
                original["aesthetic_score"],
                original["viral_score"],
                original["sentiment_score"],
                0,
                original["media_url"] or original["image_url"],
            ),
        )
        conn.execute(
            """
            UPDATE photos
            SET num_shares = COALESCE(num_shares, 0) + 1
            WHERE id = ?
            """,
            (photo_key,),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT
                p.*,
                u.username AS author_username,
                u.profile_picture_url AS author_profile_picture_url,
                u.cover_image AS author_cover_image,
                u.is_page AS author_is_page
            FROM photos p
            LEFT JOIN user_mgmt u ON u.id = p.user_id
            WHERE p.id = ?
            LIMIT 1
            """,
            (new_photo_id,),
        ).fetchone()
        updated_original = conn.execute(
            """
            SELECT COALESCE(num_shares, 0) AS num_shares
            FROM photos
            WHERE id = ?
            LIMIT 1
            """,
            (photo_key,),
        ).fetchone()

    if row is None:
        return {"ok": False, "error": "photo_not_created"}, 500

    item = _photo_build_item(exp, dict(row))
    item["shared_from"] = [photo_key, str(original["author_username"] or original["user_id"] or "Shared post")]
    item.update(_photo_viewer_photo_state(exp, new_photo_id, viewer_id))
    html = render_template(
        "photo/components/posts.html",
        items=[item],
        exp_id=exp_id,
        user_id="all",
        enumerate=enumerate,
        len=len,
        active_tab="for_you",
    )
    return {
        "ok": True,
        "photo_id": new_photo_id,
        "source_photo_id": photo_key,
        "post": item,
        "html": html,
        "shares": int(updated_original["num_shares"] or 0) if updated_original else 0,
    }


@main.post("/<int:exp_id>/api/photo/story/<story_id>/view")
@login_required
def api_photo_story_view(exp_id, story_id):
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
    viewer_id = str(getattr(exp_user, "id", _photo_logged_user_id()) or "").strip()
    if not viewer_id:
        return {"ok": False, "error": "missing_user"}, 400

    story_key = str(story_id or "").strip()
    if not story_key:
        return {"ok": False, "error": "not_found"}, 404

    db_path = _photo_db_path(exp)
    if not db_path:
        return {"ok": False, "error": "database_unavailable"}, 500

    viewed = False
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        story = conn.execute(
            """
            SELECT id, view_count
            FROM stories
            WHERE id = ?
            LIMIT 1
            """,
            (story_key,),
        ).fetchone()
        if story is None:
            return {"ok": False, "error": "not_found"}, 404

        existing = conn.execute(
            """
            SELECT 1
            FROM story_views
            WHERE story_id = ? AND viewer_id = ?
            LIMIT 1
            """,
            (story_key, viewer_id),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO story_views (id, story_id, viewer_id, viewed_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (str(uuid.uuid4()), story_key, viewer_id),
            )
            conn.execute(
                """
                UPDATE stories
                SET view_count = COALESCE(view_count, 0) + 1
                WHERE id = ?
                """,
                (story_key,),
            )
            conn.commit()
            viewed = True

        updated_story = conn.execute(
            """
            SELECT id, view_count
            FROM stories
            WHERE id = ?
            LIMIT 1
            """,
            (story_key,),
        ).fetchone()

    return {
        "ok": True,
        "story_id": story_key,
        "viewed": viewed,
        "view_count": int(updated_story["view_count"] or 0) if updated_story else int(story["view_count"] or 0),
    }


@main.post("/<int:exp_id>/api/photo/share")
@login_required
def api_photo_share(exp_id):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "photo_sharing":
        return {"ok": False, "error": "not_found"}, 404

    upload_file = request.files.get("image") or request.files.get("media")
    if upload_file is None or not getattr(upload_file, "filename", ""):
        return {"ok": False, "error": "missing_file"}, 400

    caption = str(request.form.get("caption") or "").strip()
    alt_text = str(request.form.get("alt_text") or "").strip()
    if not caption and not alt_text:
        return {"ok": False, "error": "missing_text"}, 400

    exp_user, _created = ensure_experiment_user(
        exp,
        user_id=getattr(current_user, "id", 0) or 0,
        username=str(current_user.username),
        email=str(getattr(current_user, "email", "") or ""),
        password=str(getattr(current_user, "password", "") or ""),
        joined_on=0,
    )
    user_id = str(getattr(exp_user, "id", _photo_logged_user_id()) or "").strip()
    if not user_id:
        return {"ok": False, "error": "missing_user"}, 400

    try:
        _, media_url = _photo_store_uploaded_media(exp, upload_file)
    except ValueError:
        return {"ok": False, "error": "media_root_unavailable"}, 500

    round_id = _photo_latest_round_id()
    photo_id = str(uuid.uuid4())
    db_path = _photo_db_path(exp)
    if not db_path:
        return {"ok": False, "error": "database_unavailable"}, 500

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO photos (
                id, user_id, round, image_url, thumbnail_url, caption, alt_text,
                filter_name, location_name, latitude, longitude, is_carousel,
                carousel_index, parent_photo_id, num_likes, num_comments,
                num_shares, is_sponsored, embedding, aesthetic_score,
                viral_score, sentiment_score, is_removed, media_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                photo_id,
                user_id,
                round_id,
                media_url,
                media_url,
                caption or alt_text,
                alt_text or caption,
                None,
                None,
                None,
                None,
                0,
                0,
                None,
                0,
                0,
                0,
                0,
                None,
                None,
                None,
                None,
                0,
                media_url,
            ),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT
                p.*,
                u.username AS author_username,
                u.profile_picture_url AS author_profile_picture_url,
                u.cover_image AS author_cover_image,
                u.is_page AS author_is_page
            FROM photos p
            LEFT JOIN user_mgmt u ON u.id = p.user_id
            WHERE p.id = ?
            LIMIT 1
            """,
            (photo_id,),
        ).fetchone()

    if row is None:
        return {"ok": False, "error": "photo_not_created"}, 500

    item = _photo_build_item(exp, dict(row))
    html = render_template(
        "photo/components/posts.html",
        items=[item],
        exp_id=exp_id,
        user_id="all",
        enumerate=enumerate,
        len=len,
        active_tab="for_you",
    )
    return {"ok": True, "post": item, "html": html}


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
    followed_contact_ids = set(
        _photo_active_contact_ids(
            exp, getattr(logged_user, "id", _photo_logged_user_id())
        )
    )
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
    story_author_filter = list(followed_contact_ids) if active_tab == "follower" else None
    stories = _build_photo_story_previews(
        exp,
        getattr(logged_user, "id", _photo_logged_user_id()),
        list(followed_contact_ids),
        allowed_author_ids=story_author_filter,
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
        user_id=user_id,
        timeline=timeline,
        username=username,
        mode=mode,
        enumerate=enumerate,
        len=len,
        mentions=mentions,
        sfollow=sfollow,
        spages=spages,
        suggested_contacts=suggested_contacts,
        followed_contact_ids=followed_contact_ids,
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
        **_photo_sidebar_context(
            exp,
            logged_user=logged_user,
            logged_id=getattr(logged_user, "id", _photo_logged_user_id()),
            photo_home_url=f"/{exp_id}/photo/feed/all/feed/rf/1?tab={active_tab}",
            photo_active_nav="home",
        ),
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
