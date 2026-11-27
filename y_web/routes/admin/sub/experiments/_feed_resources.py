"""
Reusable feed libraries, image-feed assignment and feed limits.

Any platform whose experiments read external feeds uses these pages. The shared RSS and image resources live
in the dashboard database; an experiment is given a selection of them, written as ``rss_feeds.json`` /
``image_feeds.json`` in its folder. Reddit stays a supported feed source (see the declared exceptions).
"""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.sdk.feeds import normalize_subreddit_input
from y_web.src.models import ImageFeedResource, RssFeedResource
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import DEFAULT_FEED_LIMITS, experiments
from ._feeds import _parse_admin_feed_metadata as parse_admin_feed_metadata
from ._helpers import _load_feed_experiment_context
from ._helpers import _normalize_image_feed_item as normalize_image_feed_item
from ._helpers import _normalize_image_feeds_payload as normalize_image_feeds_payload
from ._helpers import _normalize_rss_feed_item as normalize_rss_feed_item
from ._helpers import _parse_required_feed_limit as parse_required_feed_limit
from ._helpers import _read_feed_with_headers as read_feed_with_headers

IMAGE_FEED_INTERESTS = sorted(
    [
        "animals",
        "art",
        "books",
        "celebrities",
        "cooking",
        "creative",
        "cute",
        "design",
        "education",
        "entertainment",
        "fitness",
        "food",
        "fun",
        "gaming",
        "general",
        "geek",
        "history",
        "humor",
        "memes",
        "movies",
        "music",
        "nature",
        "news",
        "pets",
        "photography",
        "politics",
        "science",
        "sports",
        "technology",
        "travel",
        "tv",
        "wholesome",
    ]
)


def _image_resource_payload(resource):
    try:
        interests = json.loads(resource.interests or "[]")
        if not isinstance(interests, list):
            interests = []
    except Exception:
        interests = []
    return {
        "id": resource.id,
        "subreddit": str(resource.subreddit or "").strip().lower(),
        "interests": [str(label).strip() for label in interests if str(label).strip()],
    }


def _write_experiment_image_feed_file(experiment_dir, resources):
    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    payload = [_image_resource_payload(resource) for resource in resources]
    with open(image_feeds_path, "w") as handle:
        json.dump(payload, handle, indent=2)


def _selected_image_resource_ids(experiment_dir, resources):
    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    if not os.path.exists(image_feeds_path):
        return []
    try:
        with open(image_feeds_path, "r") as handle:
            persisted = json.load(handle)
    except Exception:
        return []

    resource_by_subreddit = {
        str(resource.subreddit or "").strip().lower(): resource.id
        for resource in resources
    }
    selected = []
    for item in persisted if isinstance(persisted, list) else []:
        subreddit = str((item or {}).get("subreddit") or "").strip().lower()
        resource_id = resource_by_subreddit.get(subreddit)
        if resource_id is not None:
            selected.append(resource_id)
    return selected


def _parse_image_feed_metadata(subreddit):
    import re

    import feedparser

    normalized = normalize_subreddit_input(subreddit)
    if not normalized:
        raise ValueError(
            "Provide a subreddit slug, r/<name>, or a Reddit subreddit URL."
        )

    feed_url = f"https://www.reddit.com/r/{quote(normalized)}.rss"
    feed_content = read_feed_with_headers(feed_url)
    feed = feedparser.parse(feed_content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"Could not parse r/{normalized}.")
    if not feed.entries:
        raise ValueError(f"No posts found in r/{normalized}")

    image_pattern = re.compile(r"\.(jpg|jpeg|png|gif|webp)(\?.*)?$", re.IGNORECASE)
    image_hosts = ["i.redd.it", "i.imgur.com", "preview.redd.it"]
    images = []
    nsfw_count = 0

    for entry in feed.entries[:50]:
        is_nsfw = False
        if getattr(entry, "over_18", False):
            is_nsfw = True
        elif "[nsfw]" in entry.get("title", "").lower():
            is_nsfw = True
        elif hasattr(entry, "tags"):
            for tag in entry.tags:
                if tag.get("term", "").lower() == "nsfw":
                    is_nsfw = True
                    break

        if is_nsfw:
            nsfw_count += 1
            continue

        image_url = None
        link = entry.get("link", "")
        if image_pattern.search(link) or any(host in link for host in image_hosts):
            image_url = link

        if not image_url and hasattr(entry, "media_content"):
            for media in entry.media_content:
                media_url = media.get("url", "")
                if image_pattern.search(media_url) or any(
                    host in media_url for host in image_hosts
                ):
                    image_url = media_url
                    break

        if not image_url and hasattr(entry, "media_thumbnail"):
            for thumb in entry.media_thumbnail:
                media_url = thumb.get("url", "")
                if media_url:
                    image_url = media_url
                    break

        if image_url:
            images.append(image_url)

        if len(images) >= 6:
            break

    return {
        "subreddit": normalized,
        "feed_url": feed_url,
        "image_count": len(images),
        "nsfw_filtered": nsfw_count,
        "sample_images": images[:6],
    }


@experiments.route("/admin/rss_resources")
@login_required
def rss_resources():
    """Manage reusable RSS feed resources."""
    check_privileges(current_user.username)
    resources = db.session.scalars(
        select(RssFeedResource).order_by(
            RssFeedResource.name.asc(), RssFeedResource.id.asc()
        )
    ).all()
    return render_template(
        "admin/rss_resources.html",
        resources=resources,
    )


@experiments.route("/admin/create_rss_resource", methods=["POST"])
@login_required
def create_rss_resource():
    """Validate and create or update a reusable RSS resource."""
    check_privileges(current_user.username)

    feed_url = str(request.form.get("feed_url", "")).strip()
    if not feed_url:
        flash(_("RSS feed URL is required."), "error")
        return redirect("/admin/rss_resources")
    if "://" not in feed_url:
        feed_url = f"https://{feed_url}"

    try:
        feed_content = read_feed_with_headers(feed_url)
        parsed_feed = parse_admin_feed_metadata(feed_url, feed_content)
        if parsed_feed is None:
            raise ValueError("Invalid RSS feed URL")
        normalized = normalize_rss_feed_item(parsed_feed)
    except HTTPError as exc:
        flash(_("Feed source returned HTTP %(code)s.", code=exc.code), "error")
        return redirect("/admin/rss_resources")
    except URLError:
        flash(_("Feed source could not be reached."), "error")
        return redirect("/admin/rss_resources")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect("/admin/rss_resources")
    except Exception as exc:
        flash(str(exc), "error")
        return redirect("/admin/rss_resources")

    existing = db.session.scalars(
        select(RssFeedResource).filter_by(feed_url=normalized["feed_url"])
    ).first()
    if existing is None:
        existing = RssFeedResource(feed_url=normalized["feed_url"])
        db.session.add(existing)

    existing.name = normalized["name"]
    existing.url_site = normalized["url_site"]
    existing.description = normalized["description"]
    db.session.commit()

    flash(_("Reusable RSS feed saved."), "success")
    return redirect("/admin/rss_resources")


@experiments.route("/admin/delete_rss_resource/<int:resource_id>", methods=["POST"])
@login_required
def delete_rss_resource(resource_id):
    """Delete a reusable RSS resource."""
    check_privileges(current_user.username)
    resource = db.session.get(RssFeedResource, resource_id)
    if resource is None:
        flash(_("RSS feed resource not found."), "error")
        return redirect("/admin/rss_resources")

    db.session.delete(resource)
    db.session.commit()
    flash(_("Reusable RSS feed deleted."), "success")
    return redirect("/admin/rss_resources")


@experiments.route("/admin/image_feeds/<int:uid>")
@login_required
def image_feeds(uid):
    """Display and assign reusable image feeds to an experiment."""
    experiment, experiment_dir, error_response = _load_feed_experiment_context(uid)
    if error_response is not None:
        return error_response

    available_image_resources = db.session.scalars(
        select(ImageFeedResource).order_by(
            ImageFeedResource.subreddit.asc(), ImageFeedResource.id.asc()
        )
    ).all()
    selected_image_resource_ids = _selected_image_resource_ids(
        experiment_dir, available_image_resources
    )

    return render_template(
        "admin/image_feeds.html",
        experiment=experiment,
        available_image_resources=[
            _image_resource_payload(resource) for resource in available_image_resources
        ],
        selected_image_resource_ids=selected_image_resource_ids,
    )


@experiments.route("/admin/update_image_feeds/<int:uid>", methods=["POST"])
@login_required
def update_image_feeds(uid):
    """Persist assigned reusable image feeds."""
    experiment, experiment_dir, error_response = _load_feed_experiment_context(uid)
    if error_response is not None:
        return error_response

    selected_ids = []
    for raw_id in request.form.getlist("image_feed_resource_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    resources = (
        db.session.scalars(
            select(ImageFeedResource).filter(ImageFeedResource.id.in_(selected_ids))
        ).all()
        if selected_ids
        else []
    )
    resource_order = {
        resource_id: index for index, resource_id in enumerate(selected_ids)
    }
    resources = sorted(
        resources,
        key=lambda resource: resource_order.get(resource.id, len(resource_order)),
    )
    _write_experiment_image_feed_file(experiment_dir, resources)

    if int(getattr(experiment, "running", 0) or 0) == 1:
        flash(
            _(
                "The updated image feed assignment has been saved. Running clients will use the new feeds after they are restarted."
            ),
            "info",
        )
    flash(_("Image feeds updated successfully."), "success")
    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/upload_image_feeds/<int:uid>", methods=["POST"])
@login_required
def upload_image_feeds(uid):
    """Bulk upload image feeds from JSON."""
    experiment, experiment_dir, error_response = _load_feed_experiment_context(uid)
    if error_response is not None:
        return error_response

    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    if "file" not in request.files:
        return jsonify({"error": _("No file provided")}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": _("No file selected")}), 400

    try:
        content = upload.read().decode("utf-8")
        normalized_feeds = normalize_image_feeds_payload(json.loads(content))

        mode = request.form.get("mode", "replace")
        if mode == "merge" and os.path.exists(image_feeds_path):
            with open(image_feeds_path, "r") as handle:
                existing_feeds = normalize_image_feeds_payload(json.load(handle))

            merged = []
            by_subreddit = {}
            for feed in existing_feeds:
                if not isinstance(feed, dict):
                    continue
                subreddit = str(feed.get("subreddit", "")).strip().lower()
                if not subreddit:
                    continue
                merged_feed = {
                    "subreddit": subreddit,
                    "interests": list(feed.get("interests") or []),
                }
                merged.append(merged_feed)
                by_subreddit[subreddit] = merged_feed

            for feed in normalized_feeds:
                subreddit = feed["subreddit"]
                if subreddit in by_subreddit:
                    combined = []
                    seen = set()
                    for label in list(
                        by_subreddit[subreddit].get("interests") or []
                    ) + list(feed.get("interests") or []):
                        label = str(label).strip()
                        if not label or label in seen:
                            continue
                        seen.add(label)
                        combined.append(label)
                    by_subreddit[subreddit]["interests"] = combined
                else:
                    merged.append(feed)
                    by_subreddit[subreddit] = feed
            normalized_feeds = merged

        with open(image_feeds_path, "w") as handle:
            json.dump(normalized_feeds, handle, indent=2)
        return jsonify({"success": True, "count": len(normalized_feeds)})
    except json.JSONDecodeError:
        return jsonify({"error": _("Invalid JSON format")}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/image_resources")
@login_required
def image_resources():
    """Manage reusable image feed resources."""
    check_privileges(current_user.username)
    resources = db.session.scalars(
        select(ImageFeedResource).order_by(
            ImageFeedResource.subreddit.asc(), ImageFeedResource.id.asc()
        )
    ).all()
    return render_template(
        "admin/image_resources.html",
        resources=[_image_resource_payload(resource) for resource in resources],
        available_interests=IMAGE_FEED_INTERESTS,
    )


@experiments.route("/admin/create_image_resource", methods=["POST"])
@login_required
def create_image_resource():
    """Validate and create or update a reusable image feed resource."""
    check_privileges(current_user.username)

    subreddit_input = str(request.form.get("subreddit", "")).strip()
    selected_interests = [
        label.strip()
        for label in request.form.getlist("interests")
        if str(label).strip()
    ]

    if not selected_interests:
        flash(_("Select at least one interest for the image feed."), "error")
        return redirect("/admin/image_resources")

    try:
        parsed = _parse_image_feed_metadata(subreddit_input)
        normalized = normalize_image_feed_item(
            {
                "subreddit": parsed["subreddit"],
                "interests": selected_interests,
            }
        )
    except HTTPError as exc:
        if exc.code == 404:
            flash(
                _(
                    "r/%(subreddit_input)s does not exist.",
                    subreddit_input=subreddit_input,
                ),
                "error",
            )
        else:
            flash(_("Reddit returned HTTP %(code)s.", code=exc.code), "error")
        return redirect("/admin/image_resources")
    except URLError:
        flash(_("Reddit could not be reached. Retry later."), "error")
        return redirect("/admin/image_resources")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect("/admin/image_resources")
    except Exception as exc:
        flash(str(exc), "error")
        return redirect("/admin/image_resources")

    existing = db.session.scalars(
        select(ImageFeedResource).filter_by(subreddit=normalized["subreddit"])
    ).first()
    if existing is None:
        existing = ImageFeedResource(subreddit=normalized["subreddit"])
        db.session.add(existing)

    existing.interests = json.dumps(normalized["interests"])
    db.session.commit()

    flash(_("Reusable image feed saved."), "success")
    return redirect("/admin/image_resources")


@experiments.route("/admin/delete_image_resource/<int:resource_id>", methods=["POST"])
@login_required
def delete_image_resource(resource_id):
    """Delete a reusable image feed resource."""
    check_privileges(current_user.username)
    resource = db.session.get(ImageFeedResource, resource_id)
    if resource is None:
        flash(_("Image feed resource not found."), "error")
        return redirect("/admin/image_resources")

    db.session.delete(resource)
    db.session.commit()
    flash(_("Reusable image feed deleted."), "success")
    return redirect("/admin/image_resources")


@experiments.route("/admin/api/parse_image_feed", methods=["POST"])
@login_required
def parse_image_feed():
    """Parse a subreddit RSS feed and extract sample image URLs."""
    check_privileges(current_user.username)

    payload = request.get_json(silent=True) or {}
    subreddit = payload.get("subreddit", "")

    try:
        parsed = _parse_image_feed_metadata(subreddit)
        parsed["sample_images"] = parsed["sample_images"][:5]
        return jsonify(parsed)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except HTTPError as exc:
        if exc.code == 404:
            return (
                jsonify(
                    {"error": _("r/%(subreddit)s does not exist.", subreddit=subreddit)}
                ),
                400,
            )
        return (
            jsonify(
                {
                    "error": (
                        _(
                            "Reddit returned HTTP %(code)s while loading r/%(subreddit)s. Retry later.",
                            code=exc.code,
                            subreddit=subreddit,
                        )
                    )
                }
            ),
            400,
        )
    except URLError:
        return jsonify({"error": _("Reddit could not be reached. Retry later.")}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/feed_limits/<int:uid>", methods=["GET"])
@login_required
def feed_limits(uid):
    """Display and edit feed retrieval limits for an experiment."""
    experiment, experiment_dir, error_response = _load_feed_experiment_context(uid)
    if error_response is not None:
        return error_response

    config_path = os.path.join(experiment_dir, "config_server.json")
    feed_limits_data = dict(DEFAULT_FEED_LIMITS)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as handle:
                config = json.load(handle)
            if isinstance(config.get("feed_limits"), dict):
                feed_limits_data.update(config["feed_limits"])
        except (json.JSONDecodeError, IOError):
            pass

    return render_template(
        "admin/feed_limits.html",
        experiment=experiment,
        feed_limits=feed_limits_data,
    )


@experiments.route("/admin/update_feed_limits/<int:uid>", methods=["POST"])
@login_required
def update_feed_limits(uid):
    """Update feed retrieval limits for an experiment."""
    experiment, experiment_dir, error_response = _load_feed_experiment_context(uid)
    if error_response is not None:
        return error_response

    config_path = os.path.join(experiment_dir, "config_server.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as handle:
                config = json.load(handle)
        except (json.JSONDecodeError, IOError):
            config = {}

    try:
        config["feed_limits"] = {
            "rss_entries_per_feed": parse_required_feed_limit(
                "rss_entries_per_feed", int, "RSS entries per feed", minimum=1
            ),
            "reddit_entries_per_feed": parse_required_feed_limit(
                "reddit_entries_per_feed", int, "Reddit entries per feed", minimum=1
            ),
            "reddit_pages": parse_required_feed_limit(
                "reddit_pages", int, "Reddit pages", minimum=1
            ),
            "reddit_rate_limit_seconds": parse_required_feed_limit(
                "reddit_rate_limit_seconds",
                float,
                "Reddit rate limit seconds",
                minimum=0,
            ),
            "db_fallback_limit": parse_required_feed_limit(
                "db_fallback_limit", int, "Database fallback limit", minimum=1
            ),
            "image_entries_per_feed": parse_required_feed_limit(
                "image_entries_per_feed", int, "Image entries per feed", minimum=1
            ),
        }
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("experiments.feed_limits", uid=uid))

    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    flash(_("Feed limits updated successfully."), "success")
    return redirect(request.referrer or url_for("experiments.feed_limits", uid=uid))
