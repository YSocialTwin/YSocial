from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from typing import Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import requests
from flask import current_app, g
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from y_web import db
from y_web.experiment_context import (
    get_db_bind_key_for_exp,
    register_experiment_database,
)
try:
    from y_web.llm_annotations import Annotator, ContentAnnotator
except Exception:
    Annotator = None
    ContentAnnotator = None
from y_web.models import (
    Admin_users,
    Articles,
    Emotions,
    Exps,
    Hashtags,
    Images,
    Interests,
    Mentions,
    Post,
    Post_emotions,
    Post_hashtags,
    Post_Sentiment,
    Post_topics,
    Reactions,
    Rounds,
    User_Experiment,
    User_interest,
    User_mgmt,
    Websites,
)
from y_web.utils.article_extractor import extract_article_info
from y_web.utils.text_utils import toxicity, vader_sentiment

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg")
_VIDEO_EXTENSIONS = (".mp4",)
_MEDIA_EXTENSIONS = _IMAGE_EXTENSIONS + _VIDEO_EXTENSIONS


def _normalize_comment_for_dedupe(text: str) -> str:
    """Normalize comment text for same-round duplicate detection."""
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    normalized = re.sub(r"[^\w\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _comment_dedupe_key(text: str) -> Optional[str]:
    normalized = _normalize_comment_for_dedupe(text)
    if not normalized:
        return None
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


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

        from y_web.utils.path_utils import get_writable_path

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


def _ensure_experiment_context(user) -> None:
    """
    Ensure the experiment database context is set up for the current user.

    This is needed for API routes that don't have exp_id in the URL.
    It looks up the user's active experiment and sets up the database binding.
    """
    # Check if context is already set up
    if hasattr(g, "current_exp_id") and g.current_exp_id is not None:
        return

    # Find the user's experiment - prefer active experiments (status=1)
    user_exp = (
        User_Experiment.query.join(Exps, User_Experiment.exp_id == Exps.idexp)
        .filter(User_Experiment.user_id == user.id, Exps.status == 1)
        .first()
    )
    if user_exp is None:
        # Fallback: any user experiment, or any active experiment
        user_exp = User_Experiment.query.filter_by(user_id=user.id).first()

    if user_exp is None:
        # Try to find any active experiment as fallback
        active_exp = Exps.query.filter_by(status=1).first()
        if active_exp is None:
            raise ValueError("No active experiment found")
        exp_id = active_exp.idexp
        db_name = active_exp.db_name
    else:
        exp = Exps.query.filter_by(idexp=user_exp.exp_id).first()
        if exp is None:
            raise ValueError("User's experiment not found")
        exp_id = exp.idexp
        db_name = exp.db_name

    # Register the experiment database if needed
    bind_key = get_db_bind_key_for_exp(exp_id)
    if bind_key not in current_app.config.get("SQLALCHEMY_BINDS", {}):
        register_experiment_database(current_app, exp_id, db_name)

    # Set up the context
    g.current_exp_id = exp_id
    g.current_db_bind = bind_key

    # Override db_exp bind to point to this experiment's database
    if bind_key in current_app.config["SQLALCHEMY_BINDS"]:
        if not hasattr(g, "original_db_exp_bind"):
            g.original_db_exp_bind = current_app.config["SQLALCHEMY_BINDS"].get(
                "db_exp"
            )
        current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
            "SQLALCHEMY_BINDS"
        ][bind_key]


def _get_current_round() -> int:
    """Get the current round ID, defaulting to 1 if none exist."""
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()
    return current_round.id if current_round else 1


def _calculate_vote_tallies(post_id: int) -> Tuple[int, int]:
    """Calculate like and dislike counts for a post."""
    likes = (
        db.session.query(func.count(Reactions.id))
        .filter(Reactions.post_id == post_id, Reactions.type == "like")
        .scalar()
        or 0
    )
    dislikes = (
        db.session.query(func.count(Reactions.id))
        .filter(Reactions.post_id == post_id, Reactions.type == "dislike")
        .scalar()
        or 0
    )
    return int(likes), int(dislikes)


def apply_vote(user, post_id: int, action: str) -> Tuple[int, int]:
    """
    Apply a vote (like/dislike/neutral) to a post.

    Args:
        user: Current user object (from flask_login)
        post_id: ID of the post to vote on
        action: One of "like", "dislike", or "neutral"

    Returns:
        Tuple of (likes, dislikes) counts after the vote

    Raises:
        ValueError: If post not found or action invalid
        RuntimeError: If database operation fails
    """
    if action not in {"like", "dislike", "neutral"}:
        raise ValueError(f"Invalid action: {action}")

    # Ensure experiment database context is set up
    _ensure_experiment_context(user)

    post = Post.query.filter_by(id=post_id).first()
    if post is None:
        raise ValueError(f"Post {post_id} not found")

    round_id = _get_current_round()

    try:
        existing_reaction = (
            Reactions.query.filter_by(post_id=post_id, user_id=user.id)
            .order_by(Reactions.id.desc())
            .first()
        )

        if action == "neutral":
            if existing_reaction is not None:
                db.session.delete(existing_reaction)
                db.session.commit()
            likes, dislikes = _calculate_vote_tallies(post_id)
            post.reaction_count = likes + dislikes
            db.session.commit()
            return likes, dislikes

        if existing_reaction is None:
            reaction = Reactions(
                post_id=post_id,
                user_id=user.id,
                round=round_id,
                type=action,
            )
            db.session.add(reaction)
        else:
            existing_reaction.type = action
            existing_reaction.round = round_id

        db.session.commit()

        likes, dislikes = _calculate_vote_tallies(post_id)
        post.reaction_count = likes + dislikes
        db.session.commit()

        # Get sentiment parent for tracking
        sentiment_parent = ""
        post_sentiment_record = Post_Sentiment.query.filter_by(post_id=post_id).first()
        if post_sentiment_record is not None:
            compound = post_sentiment_record.compound
            if compound > 0.05:
                sentiment_parent = "pos"
            elif compound < -0.05:
                sentiment_parent = "neg"
            else:
                sentiment_parent = "neu"

        # Create reaction sentiment records for each topic
        post_topics_list = Post_topics.query.filter_by(post_id=post_id).all()
        for post_topic in post_topics_list:
            topic_id = post_topic.topic_id

            reaction_sentiment = Post_Sentiment(
                post_id=post_id,
                user_id=user.id,
                pos=0 if action == "dislike" else 1,
                neg=0 if action == "like" else 1,
                neu=0,
                compound=1 if action == "like" else -1,
                sentiment_parent=sentiment_parent,
                round=round_id,
                is_reaction=1,
                topic_id=topic_id,
            )
            db.session.add(reaction_sentiment)
            db.session.commit()

    except Exception as exc:
        db.session.rollback()
        raise RuntimeError(f"Database operation failed: {exc}")

    # Calculate and return vote tallies
    return _calculate_vote_tallies(post_id)


def create_comment_reddit(
    user, parent_id: int, content: str, client_action_id: Optional[str] = None
) -> Tuple[Post, bool]:
    """
    Create a comment on a post or another comment.

    Args:
        user: Current user object (from flask_login)
        parent_id: ID of the post/comment to reply to
        content: Comment text content

    Returns:
        Tuple of (Post, deduped) where deduped=True means an existing row
        was reused instead of creating a new comment.

    Raises:
        ValueError: If parent not found or content invalid
    """
    if not content.strip():
        raise ValueError("Comment content is required")

    # Ensure experiment database context is set up
    _ensure_experiment_context(user)

    parent = Post.query.filter_by(id=parent_id).first()
    if parent is None:
        raise ValueError(f"Parent post {parent_id} not found")

    round_id = _get_current_round()
    thread_id = parent.thread_id or parent.id
    safe_action_id = (str(client_action_id or "").strip()[:96]) or None
    dedupe_key = _comment_dedupe_key(content)

    try:
        # Idempotency token guard (request-level dedupe)
        if safe_action_id:
            existing = Post.query.filter_by(
                user_id=user.id, client_action_id=safe_action_id
            ).first()
            if existing is not None:
                return existing, True

        # Same-parent/same-round/same-text guard
        if dedupe_key:
            existing = Post.query.filter_by(
                user_id=user.id,
                comment_to=parent_id,
                round=round_id,
                dedupe_key=dedupe_key,
            ).first()
            if existing is not None:
                return existing, True

        # Create comment
        comment = Post(
            tweet=content,
            round=round_id,
            user_id=user.id,
            comment_to=parent_id,
            thread_id=thread_id,
            dedupe_key=dedupe_key,
            client_action_id=safe_action_id,
        )
        db.session.add(comment)
        try:
            db.session.commit()
        except IntegrityError:
            # Concurrent duplicate request: re-query and reuse existing row.
            db.session.rollback()
            existing = None
            if safe_action_id:
                existing = Post.query.filter_by(
                    user_id=user.id, client_action_id=safe_action_id
                ).first()
            if existing is None and dedupe_key:
                existing = Post.query.filter_by(
                    user_id=user.id,
                    comment_to=parent_id,
                    round=round_id,
                    dedupe_key=dedupe_key,
                ).first()
            if existing is not None:
                return existing, True
            raise

        # Get parent sentiment for tracking
        sentiment_parent = ""
        parent_sentiment = Post_Sentiment.query.filter_by(post_id=parent_id).first()
        if parent_sentiment is not None:
            compound = parent_sentiment.compound
            if compound > 0.05:
                sentiment_parent = "pos"
            elif compound < -0.05:
                sentiment_parent = "neg"
            else:
                sentiment_parent = "neu"

        # Calculate sentiment for comment
        sentiment = vader_sentiment(content)

        # Process toxicity (handles API availability internally)
        toxicity(content, user.username, comment.id, db)

        # Get user's LLM for annotations
        admin_user = Admin_users.query.filter_by(username=user.username).first()
        llm = "llama3.2:latest"
        if admin_user and admin_user.llm:
            llm = admin_user.llm

        # LLM-based annotations are optional in this stack.
        if ContentAnnotator is not None:
            annotator = ContentAnnotator(llm=llm)
            emotions = annotator.annotate_emotions(content)
            hashtags = annotator.extract_components(content, c_type="hashtags")
            mentions = annotator.extract_components(content, c_type="mentions")
        else:
            emotions = []
            hashtags = []
            mentions = []

        # Inherit topics from thread root
        post_topics_list = Post_topics.query.filter_by(post_id=thread_id).all()
        for topic in post_topics_list:
            topic_id = topic.topic_id

            post_sentiment = Post_Sentiment(
                post_id=comment.id,
                user_id=user.id,
                pos=sentiment["pos"],
                neg=sentiment["neg"],
                neu=sentiment["neu"],
                compound=sentiment["compound"],
                sentiment_parent=sentiment_parent,
                round=round_id,
                is_comment=1,
                topic_id=topic_id,
            )
            db.session.add(post_sentiment)
            db.session.commit()

        # Process emotions
        for emotion_name in emotions:
            if len(emotion_name) < 1:
                continue
            emotion = Emotions.query.filter_by(emotion=emotion_name).first()
            if emotion is not None:
                post_emotion = Post_emotions(post_id=comment.id, emotion_id=emotion.id)
                db.session.add(post_emotion)
                db.session.commit()

        # Process hashtags (minimum length 4)
        for tag in hashtags:
            if len(tag) < 4:
                continue
            hashtag = Hashtags.query.filter_by(hashtag=tag).first()
            if hashtag is None:
                hashtag = Hashtags(hashtag=tag)
                db.session.add(hashtag)
                db.session.commit()
                hashtag = Hashtags.query.filter_by(hashtag=tag).first()

            post_hashtag = Post_hashtags(post_id=comment.id, hashtag_id=hashtag.id)
            db.session.add(post_hashtag)
            db.session.commit()

        # Process mentions (validate user exists and is not self)
        modified_content = content
        mentioned_user_ids = set()
        for mention in mentions:
            if len(mention) < 1:
                continue
            mentioned_user = User_mgmt.query.filter_by(
                username=mention.strip("@")
            ).first()

            if mentioned_user is not None and mentioned_user.id != user.id:
                if mentioned_user.id not in mentioned_user_ids:
                    mention_record = Mentions(
                        user_id=mentioned_user.id, post_id=comment.id, round=round_id
                    )
                    db.session.add(mention_record)
                    db.session.commit()
                    mentioned_user_ids.add(mentioned_user.id)
            else:
                # Remove invalid mentions from text
                modified_content = modified_content.replace(mention, "")

        # Mirror agent behavior for replies: notify parent author even without explicit @mention.
        # This keeps human replies visible in the mention-driven agent reply loop.
        parent_author_id = parent.user_id
        if parent_author_id != user.id and parent_author_id not in mentioned_user_ids:
            mention_record = Mentions(
                user_id=parent_author_id, post_id=comment.id, round=round_id
            )
            db.session.add(mention_record)
            db.session.commit()

        # Update comment text if mentions were removed
        if modified_content != content:
            comment.tweet = modified_content.lstrip().rstrip()
            db.session.commit()

        return comment, False

    except Exception as exc:
        db.session.rollback()
        raise ValueError(f"Failed to create comment: {exc}")


def create_post_reddit(user, content: str, url: Optional[str] = None) -> Post:
    """
    Create a new Reddit-style post.

    Args:
        user: Current user object (from flask_login)
        content: Post text content
        url: Optional external URL (article link or image URL) to attach

    Returns:
        Created Post object

    Raises:
        ValueError: If content invalid or processing fails
    """
    if not content.strip():
        raise ValueError("Post content is required")

    # Ensure experiment database context is set up
    _ensure_experiment_context(user)

    round_id = _get_current_round()

    # Check for recent duplicate from same user in same round
    existing = Post.query.filter(
        Post.user_id == user.id,
        Post.tweet == content,
        Post.round == round_id,
        Post.comment_to == -1,
    ).first()

    if existing:
        return existing

    img_id = None
    news_id = None
    normalized_url = _normalize_external_url(url or "")
    # DB columns for links are sized at 200 chars; cap to avoid insert failures.
    if normalized_url and len(normalized_url) > 200:
        normalized_url = normalized_url[:200]

    # Admin user is stored in the admin DB; used for optional LLM URL/model config.
    admin_user = Admin_users.query.filter_by(username=user.username).first()
    llm = "llama3.2:latest"
    llm_url = None
    if admin_user:
        if getattr(admin_user, "llm", None):
            llm = admin_user.llm
        llm_url = getattr(admin_user, "llm_url", None) or None

    try:
        if normalized_url:
            candidate_media_url = _extract_candidate_media_url(normalized_url)
            if len(candidate_media_url) > 200:
                candidate_media_url = candidate_media_url[:200]

            looks_like_media = _looks_like_media_url(candidate_media_url)
            if (
                not looks_like_media
                and candidate_media_url.startswith(("http://", "https://"))
                and _remote_looks_like_image(candidate_media_url)
            ):
                looks_like_media = True

            if looks_like_media:
                stored_url = candidate_media_url
                # Download only remote images to avoid CDN gated rendering issues.
                if _looks_like_image_url(
                    candidate_media_url
                ) and candidate_media_url.startswith(("http://", "https://")):
                    exp_id = getattr(g, "current_exp_id", None)
                    if exp_id is not None:
                        local_path = _download_image_to_uploads(
                            candidate_media_url, exp_id
                        )
                        if local_path:
                            stored_url = local_path

                # Create (or reuse) an Images row, with optional media description.
                annotation = None
                annotator_ref = stored_url
                if stored_url.startswith("/uploads/"):
                    from y_web.utils.path_utils import get_writable_path

                    annotator_ref = os.path.join(
                        get_writable_path(), "y_web", stored_url.lstrip("/")
                    )
                if annotator_ref.startswith(("http://", "https://")) or os.path.exists(
                    annotator_ref
                ):
                    if Annotator is not None:
                        try:
                            llm_v = "minicpm-v"
                            image_annotator = Annotator(llm_v, llm_url=llm_url)
                            annotation = image_annotator.annotate(annotator_ref)
                        except Exception:
                            # Image annotation is optional; proceed without it.
                            annotation = None

                img = Images.query.filter_by(url=stored_url).first()
                if img is None:
                    img = Images(
                        url=stored_url, description=annotation, article_id=None
                    )
                    db.session.add(img)
                    db.session.commit()
                img_id = img.id
            else:
                # Non-media URL: treat as an article link and store in Articles/Websites.
                existing_article = Articles.query.filter_by(link=normalized_url).first()
                if existing_article:
                    news_id = existing_article.id
                else:
                    article_info = extract_article_info(normalized_url)

                    source = (article_info.get("source") or "").strip() or urlparse(
                        normalized_url
                    ).netloc
                    website = Websites.query.filter_by(name=source).first()
                    if not website:
                        website = Websites(
                            name=source[:50],
                            rss="",
                            leaning="neutral",
                            category="user_shared",
                            last_fetched=int(time.time()),
                            language="en",
                            country="us",
                        )
                        db.session.add(website)
                        db.session.commit()

                    title = (
                        article_info.get("title") or f"Shared Link: {source}"
                    ).strip()
                    summary = (
                        article_info.get("summary") or "User shared article"
                    ).strip()

                    article = Articles(
                        title=title[:200],
                        summary=summary[:500],
                        website_id=website.id,
                        link=normalized_url[:200],
                        fetched_on=int(time.time()),
                    )
                    db.session.add(article)
                    db.session.commit()
                    news_id = article.id

                    image_url = (article_info.get("image") or "").strip()
                    if image_url and len(image_url) <= 200:
                        existing_image = Images.query.filter_by(
                            article_id=article.id
                        ).first()
                        if existing_image is None:
                            existing_image = Images.query.filter_by(
                                url=image_url
                            ).first()
                        if existing_image is None:
                            db.session.add(Images(url=image_url, article_id=article.id))
                            db.session.commit()

        # Create post
        post = Post(
            tweet=content,
            round=round_id,
            user_id=user.id,
            comment_to=-1,  # -1 indicates top-level post
            image_id=img_id,
            news_id=news_id,
        )
        db.session.add(post)
        db.session.commit()

        # Set thread_id to self for new posts
        post.thread_id = post.id
        db.session.commit()

        # Calculate sentiment
        sentiment = vader_sentiment(content)

        # Process toxicity (handles API availability internally)
        toxicity(content, user.username, post.id, db)

        # LLM-based annotations are optional in this stack.
        if ContentAnnotator is not None:
            annotator = ContentAnnotator(llm=llm, llm_url=llm_url)
            emotions = annotator.annotate_emotions(content)
            hashtags = annotator.extract_components(content, c_type="hashtags")
            mentions = annotator.extract_components(content, c_type="mentions")
            topics = annotator.annotate_topics(content)
        else:
            emotions = []
            hashtags = []
            mentions = []
            topics = []

        # Process topics (create if doesn't exist)
        for topic_name in topics:
            interest = Interests.query.filter_by(interest=topic_name).first()
            if interest is None:
                interest = Interests(interest=topic_name)
                db.session.add(interest)
                db.session.commit()
                interest = Interests.query.filter_by(interest=topic_name).first()

            topic_id = interest.iid

            # Track user interest
            user_interest = User_interest(
                user_id=user.id, interest_id=topic_id, round_id=round_id
            )
            db.session.add(user_interest)

            # Track post topic
            post_topic = Post_topics(post_id=post.id, topic_id=topic_id)
            db.session.add(post_topic)
            db.session.commit()

            # Track sentiment per topic
            post_sentiment = Post_Sentiment(
                post_id=post.id,
                user_id=user.id,
                topic_id=topic_id,
                pos=sentiment["pos"],
                neg=sentiment["neg"],
                neu=sentiment["neu"],
                compound=sentiment["compound"],
                round=round_id,
                is_post=1,
            )
            db.session.add(post_sentiment)
            db.session.commit()

        # Process emotions
        for emotion_name in emotions:
            if len(emotion_name) < 1:
                continue
            emotion = Emotions.query.filter_by(emotion=emotion_name).first()
            if emotion is not None:
                post_emotion = Post_emotions(post_id=post.id, emotion_id=emotion.id)
                db.session.add(post_emotion)
                db.session.commit()

        # Process hashtags (minimum length 4)
        for tag in hashtags:
            if len(tag) < 4:
                continue
            hashtag = Hashtags.query.filter_by(hashtag=tag).first()
            if hashtag is None:
                hashtag = Hashtags(hashtag=tag)
                db.session.add(hashtag)
                db.session.commit()
                hashtag = Hashtags.query.filter_by(hashtag=tag).first()

            post_hashtag = Post_hashtags(post_id=post.id, hashtag_id=hashtag.id)
            db.session.add(post_hashtag)
            db.session.commit()

        # Process mentions (validate user exists and is not self)
        modified_content = content
        for mention in mentions:
            if len(mention) < 1:
                continue
            mentioned_user = User_mgmt.query.filter_by(
                username=mention.strip("@")
            ).first()

            if mentioned_user is not None and mentioned_user.id != user.id:
                mention_record = Mentions(
                    user_id=mentioned_user.id, post_id=post.id, round=round_id
                )
                db.session.add(mention_record)
                db.session.commit()
            else:
                # Remove invalid mentions from text
                modified_content = modified_content.replace(mention, "")

        # Update post text if mentions were removed
        if modified_content != content:
            post.tweet = modified_content.lstrip().rstrip()
            db.session.commit()

        return post

    except Exception as exc:
        db.session.rollback()
        raise ValueError(f"Failed to create post: {exc}")
