from __future__ import annotations

import os
import struct
import uuid
from io import BytesIO

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.utils import safe_join

from y_web import db
from y_web.src.data_access import get_elicited_emotions, get_topics

try:
    from y_web.src.llm import Annotator
except Exception:
    Annotator = None
try:
    from y_web.src.llm.url_summarizer import UrlSummarizer
except Exception:
    UrlSummarizer = None
from y_web.src.forum.actions import (
    apply_vote,
    create_comment_reddit,
    create_post_reddit,
)
from y_web.src.forum.service import (
    _format_display_time,
    _format_display_time_from_created_at,
    _get_profile_pic,
    build_user_feed_posts,
    fetch_feed_page,
    fetch_thread,
)
from y_web.src.models import (
    Admin_users,
    Articles,
    Images,
    Mentions,
    Post,
    Post_emotions,
    Post_hashtags,
    Post_Sentiment,
    Post_topics,
    Post_Toxicity,
    Reactions,
    Rounds,
    User_mgmt,
)
from y_web.src.system.path_utils import get_writable_path

try:
    from y_web.src.models import ContentShown
except ImportError:
    ContentShown = None

api_reddit = Blueprint("api_reddit", __name__)

_ALLOWED_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
_ALLOWED_VIDEO_EXTS = (".mp4",)
_ALLOWED_MEDIA_EXTS = _ALLOWED_IMAGE_EXTS + _ALLOWED_VIDEO_EXTS
_MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
_MAX_VIDEO_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB
_MAX_VIDEO_DURATION_SECONDS = 30.0


def _json_success(data=None, meta=None, status=200):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def _json_error(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def _upload_dir_for_exp(exp_id: int) -> str:
    return os.path.join(get_writable_path(), "y_web", "uploads", "reddit", str(exp_id))


def _guess_extension(file: FileStorage) -> str:
    filename = (file.filename or "").lower()
    for ext in _ALLOWED_MEDIA_EXTS:
        if filename.endswith(ext):
            return ext
    return ""


def _is_image_ext(ext: str) -> bool:
    return ext in _ALLOWED_IMAGE_EXTS


def _is_video_ext(ext: str) -> bool:
    return ext in _ALLOWED_VIDEO_EXTS


def _upload_limit_for_ext(ext: str) -> int:
    return _MAX_VIDEO_UPLOAD_BYTES if _is_video_ext(ext) else _MAX_IMAGE_UPLOAD_BYTES


def _iter_mp4_boxes(raw: bytes, start: int, end: int):
    cursor = start
    while cursor + 8 <= end:
        size = struct.unpack(">I", raw[cursor : cursor + 4])[0]
        box_type = raw[cursor + 4 : cursor + 8]
        header_size = 8
        if size == 1:
            if cursor + 16 > end:
                return
            size = struct.unpack(">Q", raw[cursor + 8 : cursor + 16])[0]
            header_size = 16
        elif size == 0:
            size = end - cursor

        if size < header_size:
            return
        next_cursor = cursor + size
        if next_cursor > end:
            return
        yield box_type, cursor + header_size, size - header_size
        cursor = next_cursor


def _extract_mp4_duration_seconds(raw: bytes) -> float | None:
    total_size = len(raw)
    for box_type, payload_offset, payload_size in _iter_mp4_boxes(raw, 0, total_size):
        if box_type != b"moov":
            continue
        moov_end = payload_offset + payload_size
        for child_type, child_payload_offset, child_payload_size in _iter_mp4_boxes(
            raw, payload_offset, moov_end
        ):
            if child_type != b"mvhd":
                continue
            payload = raw[
                child_payload_offset : child_payload_offset + child_payload_size
            ]
            if len(payload) < 20:
                return None

            version = payload[0]
            if version == 0:
                if len(payload) < 20:
                    return None
                timescale = struct.unpack(">I", payload[12:16])[0]
                duration = struct.unpack(">I", payload[16:20])[0]
            elif version == 1:
                if len(payload) < 32:
                    return None
                timescale = struct.unpack(">I", payload[20:24])[0]
                duration = struct.unpack(">Q", payload[24:32])[0]
            else:
                return None

            if timescale <= 0:
                return None
            if duration <= 0:
                return None
            return float(duration) / float(timescale)
    return None


def _validate_mp4_payload(raw: bytes) -> None:
    if len(raw) < 12 or raw[4:8] != b"ftyp":
        raise ValueError("Invalid MP4 file.")

    duration_seconds = _extract_mp4_duration_seconds(raw)
    if duration_seconds is None:
        raise ValueError("Invalid MP4 file.")
    if duration_seconds > _MAX_VIDEO_DURATION_SECONDS:
        raise ValueError(
            f"Video too long (max {int(_MAX_VIDEO_DURATION_SECONDS)} seconds)."
        )


def _validate_and_persist_upload(file: FileStorage, exp_id: int) -> str:
    ext = _guess_extension(file)
    if not ext:
        raise ValueError(
            "Unsupported file type. Allowed: jpg, jpeg, png, gif, webp, mp4."
        )

    max_bytes = _upload_limit_for_ext(ext)
    max_mb = max_bytes // (1024 * 1024)
    if request.content_length is not None and request.content_length > max_bytes:
        raise ValueError(f"File too large (max {max_mb}MB).")

    raw = file.read()
    if not raw:
        raise ValueError("Empty file.")
    if len(raw) > max_bytes:
        raise ValueError(f"File too large (max {max_mb}MB).")

    if _is_image_ext(ext):
        try:
            img = Image.open(BytesIO(raw))
            img.verify()
        except Exception as exc:
            raise ValueError("Invalid image file.") from exc
    elif _is_video_ext(ext):
        _validate_mp4_payload(raw)

    out_dir = _upload_dir_for_exp(exp_id)
    os.makedirs(out_dir, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "wb") as f:
        f.write(raw)

    # Return URL to the served upload route.
    return f"/uploads/reddit/{exp_id}/{filename}"


def _upload_media_response(exp_id: int):
    file = request.files.get("file")
    if file is None or not isinstance(file, FileStorage) or not file.filename:
        return _json_error("No file provided.", 400)

    try:
        url = _validate_and_persist_upload(file, exp_id)
    except ValueError as exc:
        message = str(exc) or "Invalid upload."
        status = 400
        lowered = message.lower()
        if "too large" in lowered or "too long" in lowered:
            status = 413
        elif "unsupported file type" in lowered:
            status = 415
        return _json_error(message, status)

    return _json_success({"url": url})


def _forum_posts_html(exp_id: int, items, user_id=None):
    logged_user = User_mgmt.query.filter_by(
        username=getattr(current_user, "username", "")
    ).first()
    logged_id = logged_user.id if logged_user else current_user.id
    admin_user = Admin_users.query.filter_by(
        username=getattr(current_user, "username", "")
    ).first()
    is_admin_user = bool(admin_user and getattr(admin_user, "role", "") == "admin")
    return render_template(
        "forum/components/posts.html",
        items=items,
        enumerate=enumerate,
        user_id=(user_id if user_id is not None else logged_id),
        logged_id=logged_id,
        is_admin=is_admin_user,
        exp_id=exp_id,
        str=str,
        bool=bool,
        len=len,
    )


@api_reddit.post("/<int:exp_id>/upload_image")
@login_required
def api_upload_image(exp_id: int):
    return _upload_media_response(exp_id)


@api_reddit.post("/<int:exp_id>/upload_media")
@login_required
def api_upload_media(exp_id: int):
    return _upload_media_response(exp_id)


def _uploads_base_dir() -> str:
    return os.path.join(get_writable_path(), "y_web", "uploads")


def _resolve_image_ref_for_annotation(url_or_path: str) -> str:
    """
    Map a stored image reference to a VLM-fetchable input:
    - http(s) URLs: return as-is
    - /uploads/...: map to local path under the uploads base dir
    - filesystem path: return as-is if exists
    """
    ref = (url_or_path or "").strip()
    if not ref:
        return ""
    if ref.startswith(("http://", "https://")):
        return ref
    if ref.startswith("/uploads/"):
        rel = ref[len("/uploads/") :]
        base_dir = _uploads_base_dir()
        safe_path = safe_join(base_dir, rel)
        return safe_path or ""
    if os.path.exists(ref):
        return ref
    return ""


def _get_admin_llm_settings(username: str) -> tuple[str, str]:
    """
    Return (model, llm_url) for the current logged-in dashboard user, if present.
    llm_url may be empty.
    """
    admin_user = Admin_users.query.filter_by(username=username).first()
    model = "llama3.2:latest"
    llm_url = ""
    if admin_user:
        model = (getattr(admin_user, "llm", "") or "").strip() or model
        llm_url = (getattr(admin_user, "llm_url", "") or "").strip()
    return model, llm_url


def _llm_backend_configured(llm_url: str) -> bool:
    if llm_url:
        return True
    return bool(os.getenv("LLM_URL") or os.getenv("LLM_BACKEND"))


def _article_summary_needs_enrichment(summary: str) -> bool:
    s = (summary or "").strip()
    if not s:
        return True
    lowered = s.lower()
    if lowered == "user shared article":
        return True
    if lowered.startswith("shared link:"):
        return True
    return len(s) < 60


@api_reddit.post("/<int:exp_id>/enrich/article/<int:article_id>")
@login_required
def api_enrich_article(exp_id: int, article_id: int):
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get("force"))

    article = Articles.query.filter_by(id=article_id).first()
    if not article:
        return _json_error("Article not found.", 404)

    if not force and not _article_summary_needs_enrichment(
        getattr(article, "summary", "")
    ):
        return _json_success(
            {
                "ok": True,
                "enabled": True,
                "article_id": article_id,
                "summary": article.summary,
                "cached": True,
            }
        )

    model, llm_url = _get_admin_llm_settings(getattr(current_user, "username", ""))
    cfg = (
        UrlSummarizer.build_config(model=model, base_url=llm_url or None)
        if UrlSummarizer is not None
        else None
    )
    if not cfg:
        return _json_success(
            {
                "ok": False,
                "enabled": False,
                "reason": "llm_not_configured",
                "article_id": article_id,
            }
        )

    try:
        summarizer = UrlSummarizer(cfg) if UrlSummarizer is not None else None
        if summarizer is None:
            return _json_success(
                {
                    "ok": False,
                    "enabled": False,
                    "article_id": article_id,
                    "summary": getattr(article, "summary", ""),
                }
            )
        summary = summarizer.summarize_url(getattr(article, "link", "") or "")
    except Exception as exc:
        return _json_success(
            {
                "ok": False,
                "enabled": True,
                "reason": "summarization_failed",
                "detail": str(exc),
                "article_id": article_id,
            }
        )

    if not summary:
        return _json_success(
            {
                "ok": False,
                "enabled": True,
                "reason": "empty_summary",
                "article_id": article_id,
            }
        )

    article.summary = summary[:500]
    db.session.commit()

    return _json_success(
        {
            "ok": True,
            "enabled": True,
            "article_id": article_id,
            "summary": article.summary,
            "cached": False,
        }
    )


@api_reddit.post("/<int:exp_id>/enrich/image/<int:image_id>")
@login_required
def api_enrich_image(exp_id: int, image_id: int):
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get("force"))

    image = Images.query.filter_by(id=image_id).first()
    if not image:
        return _json_error("Image not found.", 404)

    existing = (getattr(image, "description", "") or "").strip()
    if existing and not force:
        return _json_success(
            {
                "ok": True,
                "enabled": True,
                "image_id": image_id,
                "description": existing,
                "cached": True,
            }
        )

    model, llm_url = _get_admin_llm_settings(getattr(current_user, "username", ""))
    if Annotator is None or not _llm_backend_configured(llm_url):
        return _json_success(
            {
                "ok": False,
                "enabled": False,
                "reason": "llm_not_configured",
                "image_id": image_id,
            }
        )

    ref = _resolve_image_ref_for_annotation(getattr(image, "url", "") or "")
    if not ref:
        return _json_error("Invalid image reference.", 400)

    try:
        # Vision model is fixed in the current UI stack.
        llm_v = "minicpm-v"
        annotator = Annotator(llm_v, llm_url=llm_url or None)
        descr = annotator.annotate(ref)
    except Exception as exc:
        return _json_success(
            {
                "ok": False,
                "enabled": True,
                "reason": "annotation_failed",
                "detail": str(exc),
                "image_id": image_id,
            }
        )

    descr = (descr or "").strip()
    if not descr:
        return _json_success(
            {
                "ok": False,
                "enabled": True,
                "reason": "empty_description",
                "image_id": image_id,
            }
        )

    # Column is 400 chars.
    image.description = descr[:400]
    db.session.commit()

    return _json_success(
        {
            "ok": True,
            "enabled": True,
            "image_id": image_id,
            "description": image.description,
            "cached": False,
        }
    )


@api_reddit.post("/<int:exp_id>/enrich/pending")
@login_required
def api_enrich_pending(exp_id: int):
    payload = request.get_json(silent=True) or {}
    max_articles = int(payload.get("max_articles") or 0)
    max_images = int(payload.get("max_images") or 0)
    max_articles = max(0, min(max_articles, 25))
    max_images = max(0, min(max_images, 25))

    model, llm_url = _get_admin_llm_settings(getattr(current_user, "username", ""))
    cfg = (
        UrlSummarizer.build_config(model=model, base_url=llm_url or None)
        if UrlSummarizer is not None
        else None
    )
    summarizer = UrlSummarizer(cfg) if (cfg and UrlSummarizer is not None) else None

    vision_enabled = _llm_backend_configured(llm_url)
    annotator = None
    if vision_enabled and Annotator is not None:
        try:
            annotator = Annotator("minicpm-v", llm_url=llm_url or None)
        except Exception:
            annotator = None

    enriched_articles = 0
    enriched_images = 0

    if summarizer and max_articles:
        candidates = Articles.query.order_by(Articles.id.desc()).limit(200).all()
        for art in candidates:
            if enriched_articles >= max_articles:
                break
            if not _article_summary_needs_enrichment(getattr(art, "summary", "")):
                continue
            try:
                s = summarizer.summarize_url(getattr(art, "link", "") or "")
            except Exception:
                s = None
            if s:
                art.summary = s[:500]
                db.session.commit()
                enriched_articles += 1

    if annotator and max_images:
        candidates = Images.query.order_by(Images.id.desc()).limit(200).all()
        for img in candidates:
            if enriched_images >= max_images:
                break
            if (getattr(img, "description", "") or "").strip():
                continue
            ref = _resolve_image_ref_for_annotation(getattr(img, "url", "") or "")
            if not ref:
                continue
            try:
                d = annotator.annotate(ref)
            except Exception:
                d = None
            d = (d or "").strip()
            if d:
                img.description = d[:400]
                db.session.commit()
                enriched_images += 1

    return _json_success(
        {
            "ok": True,
            "enabled": {
                "summary": bool(summarizer),
                "vision": bool(annotator),
            },
            "enriched": {"articles": enriched_articles, "images": enriched_images},
        }
    )


def _serialize_comment(comment: Post, skip_metadata: bool = False) -> dict:
    """Serialize a comment Post object into frontend-compatible dict.

    Args:
        comment: The Post object to serialize
        skip_metadata: If True, skip expensive queries for emotions/topics (use for new comments)
    """
    author = User_mgmt.query.filter_by(id=comment.user_id).first()
    author_username = author.username if author else "Unknown"
    author_profile_pic = _get_profile_pic(author) if author else ""

    # Get round info
    round_obj = Rounds.query.filter_by(id=comment.round).first()
    day = str(round_obj.day) if round_obj else "None"
    hour = f"{round_obj.hour:02d}" if round_obj else "00"
    comment_created_at = getattr(comment, "created_at", None)
    display_time = _format_display_time_from_created_at(
        comment_created_at
    ) or _format_display_time(day, hour)

    # Get emotions and topics (skip for new comments to improve performance)
    if skip_metadata:
        emotions = []
        topics = []
    else:
        emotions = get_elicited_emotions(comment.id)
        topics = get_topics(comment.id, comment.user_id)

    return {
        "post_id": comment.id,
        "thread_id": comment.thread_id or comment.id,
        "author": author_username,
        "author_id": comment.user_id,
        "profile_pic": author_profile_pic,
        "post": comment.tweet,
        "title": None,
        "day": day,
        "hour": hour,
        "display_time": display_time,
        "created_at": comment_created_at.isoformat() if comment_created_at else None,
        "likes": 0,
        "dislikes": 0,
        "is_liked": False,
        "is_disliked": False,
        "emotions": emotions,
        "topics": topics,
        "children": [],  # New comments have no children yet
    }


@api_reddit.get("/<int:exp_id>/feed")
@login_required
def api_feed(exp_id: int):
    page = max(request.args.get("page", type=int, default=1), 1)
    per_page = request.args.get("per_page", type=int, default=10)
    per_page = max(1, min(per_page or 10, 50))
    feed_type = request.args.get("feed_type", default="new")
    search_query = (request.args.get("q") or "").strip()
    target_user_id = request.args.get("user_id", type=int)

    if target_user_id:
        user = User_mgmt.query.filter_by(id=target_user_id).first()
        if user is None:
            return _json_error("User not found.", 404)

        # Use fetch_feed_page for all feed types to ensure proper pagination
        page_obj = fetch_feed_page(
            viewer_id=current_user.id,
            page=page,
            per_page=per_page,
            feed_user_id=target_user_id,
            feed_type=feed_type,
            search_query=search_query,
        )
        items = [post.to_dict() for post in page_obj.posts]
        has_more = page_obj.page * page_obj.per_page < page_obj.total
        meta = {
            "page": page_obj.page,
            "per_page": page_obj.per_page,
            "has_more": has_more,
            "total": page_obj.total,
        }
        return jsonify(
            {
                "success": True,
                "data": items,
                "meta": meta,
                "html": _forum_posts_html(exp_id, items, target_user_id),
            }
        )

    page_obj = fetch_feed_page(
        viewer_id=current_user.id,
        page=page,
        per_page=per_page,
        feed_type=feed_type,
        search_query=search_query,
    )
    items = [post.to_dict() for post in page_obj.posts]
    has_more = page_obj.page * page_obj.per_page < page_obj.total
    meta = {
        "page": page_obj.page,
        "per_page": page_obj.per_page,
        "has_more": has_more,
        "total": page_obj.total,
    }
    return jsonify(
        {
            "success": True,
            "data": items,
            "meta": meta,
            "html": _forum_posts_html(exp_id, items, target_user_id),
        }
    )


@api_reddit.get("/<int:exp_id>/search")
@login_required
def api_search(exp_id: int):
    page = max(request.args.get("page", type=int, default=1), 1)
    per_page = request.args.get("per_page", type=int, default=10)
    per_page = max(1, min(per_page or 10, 50))
    feed_type = request.args.get("feed_type", default="new")
    search_query = (request.args.get("q") or "").strip()
    if not search_query:
        meta = {
            "page": 1,
            "per_page": per_page,
            "has_more": False,
            "total": 0,
            "query": "",
        }
        return _json_success([], meta)

    page_obj = fetch_feed_page(
        viewer_id=current_user.id,
        page=page,
        per_page=per_page,
        feed_type=feed_type,
        search_query=search_query,
    )
    items = [post.to_dict() for post in page_obj.posts]
    has_more = page_obj.page * page_obj.per_page < page_obj.total
    meta = {
        "page": page_obj.page,
        "per_page": page_obj.per_page,
        "has_more": has_more,
        "total": page_obj.total,
        "query": search_query,
    }
    return jsonify(
        {
            "success": True,
            "data": items,
            "meta": meta,
            "html": _forum_posts_html(exp_id, items),
        }
    )


@api_reddit.get("/<int:exp_id>/thread/<int:post_id>")
@login_required
def api_thread(exp_id: int, post_id: int):
    try:
        thread = fetch_thread(post_id, viewer_id=current_user.id)
    except ValueError:
        return _json_error("Thread not found.", 404)
    return _json_success(thread)


@api_reddit.post("/<int:exp_id>/vote")
@login_required
def api_vote(exp_id: int):
    payload = request.get_json(silent=True) or {}
    post_id = payload.get("post_id")
    action = payload.get("action")

    if not isinstance(post_id, int) or action not in {"like", "dislike", "neutral"}:
        return _json_error("Invalid payload.", 400)

    try:
        likes, dislikes = apply_vote(current_user, post_id, action)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except RuntimeError as exc:
        return _json_error(str(exc), 500)

    return _json_success(
        {
            "post_id": post_id,
            "likes": likes,
            "dislikes": dislikes,
            "score": likes - dislikes,
            "action": action,
        }
    )


@api_reddit.post("/<int:exp_id>/comment")
@login_required
def api_comment(exp_id: int):
    payload = request.get_json(silent=True) or {}
    parent_id = payload.get("parent_id")
    content = (payload.get("content") or "").strip()
    client_action_id = (payload.get("client_action_id") or "").strip() or None

    if not isinstance(parent_id, int) or not content:
        return _json_error("parent_id and content are required.", 400)

    try:
        comment, deduped = create_comment_reddit(
            current_user,
            parent_id,
            content,
            client_action_id=client_action_id,
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)

    # Return full comment data for immediate rendering
    # Skip expensive metadata queries since new comments won't have emotions/topics yet
    comment_data = _serialize_comment(comment, skip_metadata=True)
    comment_data["deduped"] = bool(deduped)
    return _json_success(comment_data)


@api_reddit.post("/<int:exp_id>/post")
@login_required
def api_post(exp_id: int):
    payload = request.get_json(silent=True) or {}
    legacy_content = (payload.get("content") or "").strip()
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    url = payload.get("url")

    if title:
        content = f"TITLE: {title}"
        if body:
            content += f"\n\n{body}"
    elif legacy_content:
        content = legacy_content
    elif body:
        content = body
    else:
        content = ""

    if not content:
        return _json_error("content is required.", 400)

    try:
        post = create_post_reddit(current_user, content, url)
    except ValueError as exc:
        return _json_error(str(exc), 400)

    return _json_success({"post_id": post.id})


@api_reddit.post("/<int:exp_id>/post/<int:post_id>/delete")
@login_required
def api_delete_post(exp_id: int, post_id: int):
    post = Post.query.filter_by(id=post_id).first()
    if post is None:
        return _json_error("Post not found.", 404)

    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    is_admin_user = (
        Admin_users.query.filter_by(
            username=current_user.username, role="admin"
        ).first()
        is not None
    )
    actor_ids = {int(current_user.id)}
    if exp_user is not None:
        actor_ids.add(int(exp_user.id))

    if not is_admin_user and int(post.user_id) not in actor_ids:
        return _json_error("Not authorized to delete this post.", 403)

    target_post_ids = set()
    if int(getattr(post, "comment_to", -1)) == -1:
        rows = (
            db.session.query(Post.id)
            .filter((Post.id == post.id) | (Post.thread_id == post.id))
            .all()
        )
        target_post_ids = {int(row[0]) for row in rows}
    else:
        target_post_ids = {int(post.id)}
        frontier = [int(post.id)]
        while frontier:
            parent_id = frontier.pop()
            child_rows = (
                db.session.query(Post.id).filter(Post.comment_to == parent_id).all()
            )
            for row in child_rows:
                child_id = int(row[0])
                if child_id in target_post_ids:
                    continue
                target_post_ids.add(child_id)
                frontier.append(child_id)

    if not target_post_ids:
        target_post_ids = {int(post.id)}

    try:
        Reactions.query.filter(Reactions.post_id.in_(target_post_ids)).delete(
            synchronize_session=False
        )
        Mentions.query.filter(Mentions.post_id.in_(target_post_ids)).delete(
            synchronize_session=False
        )
        Post_emotions.query.filter(Post_emotions.post_id.in_(target_post_ids)).delete(
            synchronize_session=False
        )
        Post_hashtags.query.filter(Post_hashtags.post_id.in_(target_post_ids)).delete(
            synchronize_session=False
        )
        Post_topics.query.filter(Post_topics.post_id.in_(target_post_ids)).delete(
            synchronize_session=False
        )
        Post_Sentiment.query.filter(Post_Sentiment.post_id.in_(target_post_ids)).delete(
            synchronize_session=False
        )
        Post_Toxicity.query.filter(Post_Toxicity.post_id.in_(target_post_ids)).delete(
            synchronize_session=False
        )
        if ContentShown is not None:
            ContentShown.query.filter(
                ContentShown.content_id.in_(target_post_ids)
            ).delete(synchronize_session=False)
        Post.query.filter(Post.id.in_(target_post_ids)).delete(
            synchronize_session=False
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return _json_error(f"Failed to delete post: {exc}", 500)

    return _json_success(
        {
            "post_id": post_id,
            "deleted": True,
            "deleted_post_count": len(target_post_ids),
        }
    )
