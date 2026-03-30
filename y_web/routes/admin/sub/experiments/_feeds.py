"""
Experiment management routes.

Administrative routes for creating, configuring, launching, and managing
social media simulation experiments including database setup, population
assignment, and experiment lifecycle control.
"""

import json
import os
import pathlib
import random
import re
import shutil
import socket
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user

from y_web import db  # , app
from y_web.src.content.avatars import normalize_forum_avatar_mode
from y_web.src.experiment.access import (
    get_visible_experiment_query,
    user_can_manage_experiment,
    user_can_view_experiment,
)
from y_web.src.hpc.population_backup import restore_population_for_hpc_client
from y_web.src.models import (
    ActivityProfile,
    Admin_users,
    AgeClass,
    Agent,
    Agent_Population,
    Agent_Profile,
    Client,
    Client_Execution,
    ClientLogMetrics,
    DownloadNotification,
    Education,
    Exp_stats,
    Exp_Topic,
    ExperimentScheduleGroup,
    ExperimentScheduleItem,
    ExperimentScheduleLog,
    ExperimentScheduleStatus,
    Exps,
    HpcMonitorSettings,
    Jupyter_instances,
    Languages,
    Leanings,
    LogFileOffset,
    Nationalities,
    Ollama_Pull,
    OpinionDistribution,
    OpinionEvolutionCache,
    OpinionEvolutionSampledAgents,
    OpinionGroup,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    Profession,
    Rounds,
    ServerLogMetrics,
    Topic_List,
    Toxicity_Levels,
    User_Experiment,
    User_mgmt,
)
from y_web.src.simulation.execution_backend import (
    start_client_for_experiment,
    start_server_for_experiment,
    stop_client_for_experiment,
    stop_server_for_experiment,
)
from y_web.src.system.desktop_file_handler import send_file_desktop
from y_web.src.system.jupyter_utils import stop_process
from y_web.src.system.miscellanea import (
    check_privileges,
    llm_backend_status,
    ollama_status,
    reload_current_user,
)
from y_web.src.system.path_utils import get_resource_path

from ._blueprint import (
    _EXP_IDS_MARKER_RE,
    DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS,
    DEFAULT_FEED_LIMITS,
    DEFAULT_FORUM_AVATAR_SETTINGS,
    DEFAULT_FORUM_EMBEDDING_SETTINGS,
    FORUM_FEED_REQUEST_HEADERS,
    MAX_HPC_PER_GROUP,
    OPINION_CACHE_EXPIRY_MINUTES,
    _schedule_check_lock,
    experiments,
)
from ._helpers import *  # noqa: F401,F403
from ._helpers import (
    _load_forum_experiment_context,
    _load_memory_capable_experiment_context,
    _normalize_embedding_host,
    _normalize_embedding_service,
    _normalize_image_feeds_payload,
    _normalize_rss_feeds_payload,
    _normalize_subreddit_input,
    _parse_required_feed_limit,
    _read_experiment_embedding_settings,
    _read_feed_with_headers,
)


@experiments.route("/admin/rss_feeds/<int:uid>")
@login_required
def rss_feeds(uid):
    """Display and edit forum RSS and URL feeds."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    url_feeds_path = os.path.join(experiment_dir, "url_feeds.txt")

    rss_feeds_data = []
    if os.path.exists(rss_feeds_path):
        try:
            with open(rss_feeds_path, "r") as handle:
                rss_feeds_data = json.load(handle)
        except (json.JSONDecodeError, IOError):
            rss_feeds_data = []

    url_feeds_data = []
    if os.path.exists(url_feeds_path):
        try:
            with open(url_feeds_path, "r") as handle:
                url_feeds_data = [line.strip() for line in handle if line.strip()]
        except IOError:
            url_feeds_data = []

    return render_template(
        "admin/rss_feeds.html",
        experiment=experiment,
        rss_feeds=rss_feeds_data,
        url_feeds=url_feeds_data,
    )


@experiments.route("/admin/update_rss_feeds/<int:uid>", methods=["POST"])
@login_required
def update_rss_feeds(uid):
    """Persist forum RSS feeds configuration."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    feeds_json = request.form.get("rss_feeds_json", "[]")

    try:
        feeds = _normalize_rss_feeds_payload(json.loads(feeds_json))
    except json.JSONDecodeError:
        flash("Invalid RSS feeds payload; changes were not saved.", "error")
        return redirect(request.referrer or url_for("experiments.rss_feeds", uid=uid))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("experiments.rss_feeds", uid=uid))

    with open(rss_feeds_path, "w") as handle:
        json.dump(feeds, handle, indent=2)

    flash("RSS feeds updated successfully.", "success")
    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/update_url_feeds/<int:uid>", methods=["POST"])
@login_required
def update_url_feeds(uid):
    """Persist forum URL feeds configuration."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    url_feeds_path = os.path.join(experiment_dir, "url_feeds.txt")
    urls_text = request.form.get("url_feeds_text", "")
    urls = [line.strip() for line in urls_text.splitlines() if line.strip()]

    with open(url_feeds_path, "w") as handle:
        handle.write("\n".join(urls))

    flash("URL feeds updated successfully.", "success")
    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/api/parse_rss_feed", methods=["POST"])
@login_required
def parse_rss_feed():
    """Parse an RSS URL and return basic feed metadata."""
    check_privileges(current_user.username)

    import feedparser

    payload = request.get_json(silent=True) or {}
    feed_url = str(payload.get("feed_url", "")).strip()
    if not feed_url:
        return jsonify({"error": "No URL provided"}), 400

    if "://" not in feed_url:
        feed_url = f"https://{feed_url}"

    try:
        feed_content = _read_feed_with_headers(feed_url)
        feed = feedparser.parse(feed_content)
        if feed.bozo and not feed.entries:
            return jsonify({"error": "Invalid RSS feed URL"}), 400
        parsed_feed_url = getattr(feed, "href", "") or feed_url
        parsed_url = urlparse(parsed_feed_url)
        site_url = str(feed.feed.get("link") or "").strip()
        site_host = urlparse(site_url).netloc or parsed_url.netloc
        return jsonify(
            {
                "name": feed.feed.get(
                    "title", site_host or parsed_url.netloc or feed_url
                ),
                "feed_url": parsed_feed_url,
                "url_site": site_url or site_host,
                "description": feed.feed.get("description", ""),
                "entries_count": len(feed.entries),
            }
        )
    except HTTPError as exc:
        return jsonify({"error": f"Feed source returned HTTP {exc.code}."}), 400
    except URLError:
        return jsonify({"error": "Feed source could not be reached."}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/upload_rss_feeds/<int:uid>", methods=["POST"])
@login_required
def upload_rss_feeds(uid):
    """Bulk upload RSS feeds from JSON."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = upload.read().decode("utf-8")
        new_feeds = _normalize_rss_feeds_payload(json.loads(content))

        mode = request.form.get("mode", "replace")
        if mode == "merge" and os.path.exists(rss_feeds_path):
            with open(rss_feeds_path, "r") as handle:
                existing_feeds = _normalize_rss_feeds_payload(json.load(handle))
            new_feeds = _normalize_rss_feeds_payload(existing_feeds + new_feeds)

        with open(rss_feeds_path, "w") as handle:
            json.dump(new_feeds, handle, indent=2)
        return jsonify({"success": True, "count": len(new_feeds)})
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format"}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/upload_url_feeds/<int:uid>", methods=["POST"])
@login_required
def upload_url_feeds(uid):
    """Bulk upload URL feeds from text or JSON."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    url_feeds_path = os.path.join(experiment_dir, "url_feeds.txt")
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = upload.read().decode("utf-8")
        try:
            urls = json.loads(content)
            if isinstance(urls, list):
                urls = [str(item).strip() for item in urls if str(item).strip()]
            else:
                urls = [line.strip() for line in content.splitlines() if line.strip()]
        except json.JSONDecodeError:
            urls = [line.strip() for line in content.splitlines() if line.strip()]

        mode = request.form.get("mode", "replace")
        if mode == "merge" and os.path.exists(url_feeds_path):
            with open(url_feeds_path, "r") as handle:
                existing_urls = {line.strip() for line in handle if line.strip()}
            urls = sorted(existing_urls | set(urls))

        with open(url_feeds_path, "w") as handle:
            handle.write("\n".join(urls))
        return jsonify({"success": True, "count": len(urls)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/image_feeds/<int:uid>")
@login_required
def image_feeds(uid):
    """Display and edit forum image feeds."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    image_feeds_data = []
    if os.path.exists(image_feeds_path):
        try:
            with open(image_feeds_path, "r") as handle:
                image_feeds_data = json.load(handle)
        except (json.JSONDecodeError, IOError):
            image_feeds_data = []

    available_interests = sorted(
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

    return render_template(
        "admin/image_feeds.html",
        experiment=experiment,
        image_feeds=image_feeds_data,
        available_interests=available_interests,
    )


@experiments.route("/admin/update_image_feeds/<int:uid>", methods=["POST"])
@login_required
def update_image_feeds(uid):
    """Persist forum image feeds configuration."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    feeds_json = request.form.get("image_feeds_json", "[]")
    try:
        feeds = _normalize_image_feeds_payload(json.loads(feeds_json))
    except json.JSONDecodeError:
        flash("Invalid image feeds payload; changes were not saved.", "error")
        return redirect(request.referrer or url_for("experiments.image_feeds", uid=uid))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("experiments.image_feeds", uid=uid))

    with open(image_feeds_path, "w") as handle:
        json.dump(feeds, handle, indent=2)

    flash("Image feeds updated successfully.", "success")
    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/upload_image_feeds/<int:uid>", methods=["POST"])
@login_required
def upload_image_feeds(uid):
    """Bulk upload image feeds from JSON."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = upload.read().decode("utf-8")
        normalized_feeds = _normalize_image_feeds_payload(json.loads(content))

        mode = request.form.get("mode", "replace")
        if mode == "merge" and os.path.exists(image_feeds_path):
            with open(image_feeds_path, "r") as handle:
                existing_feeds = _normalize_image_feeds_payload(json.load(handle))

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
        return jsonify({"error": "Invalid JSON format"}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/api/parse_image_feed", methods=["POST"])
@login_required
def parse_image_feed():
    """Parse a subreddit RSS feed and extract sample image URLs."""
    check_privileges(current_user.username)

    import re

    import feedparser

    payload = request.get_json(silent=True) or {}
    subreddit = _normalize_subreddit_input(payload.get("subreddit", ""))
    if not subreddit:
        return (
            jsonify(
                {
                    "error": (
                        "Provide a subreddit slug, r/<name>, or a Reddit subreddit URL."
                    )
                }
            ),
            400,
        )
    feed_url = f"https://www.reddit.com/r/{quote(subreddit)}.rss"

    try:
        feed_content = _read_feed_with_headers(feed_url)
        feed = feedparser.parse(feed_content)
        if feed.bozo and not feed.entries:
            return jsonify({"error": f"Could not parse r/{subreddit}."}), 400
        if not feed.entries:
            return jsonify({"error": f"No posts found in r/{subreddit}"}), 400

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

        return jsonify(
            {
                "subreddit": subreddit,
                "feed_url": feed_url,
                "image_count": len(images),
                "nsfw_filtered": nsfw_count,
                "sample_images": images[:5],
            }
        )
    except HTTPError as exc:
        if exc.code == 404:
            return jsonify({"error": f"r/{subreddit} does not exist."}), 400
        return (
            jsonify(
                {
                    "error": (
                        f"Reddit returned HTTP {exc.code} while loading r/{subreddit}. "
                        "Retry later."
                    )
                }
            ),
            400,
        )
    except URLError:
        return jsonify({"error": "Reddit could not be reached. Retry later."}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/feed_limits/<int:uid>", methods=["GET"])
@login_required
def feed_limits(uid):
    """Display and edit feed retrieval limits for a forum experiment."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
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


@experiments.route("/admin/embedding_settings/<int:uid>", methods=["GET"])
@login_required
def embedding_settings(uid):
    """Display and edit memory embedding backend settings for standard/forum experiments."""
    experiment, experiment_dir, error_response = (
        _load_memory_capable_experiment_context(uid)
    )
    if error_response is not None:
        return error_response

    return render_template(
        "admin/embedding_settings.html",
        experiment=experiment,
        embedding_settings=_read_experiment_embedding_settings(experiment_dir),
        platform_label=(
            "Forum" if experiment.platform_type == "forum" else "Microblogging"
        ),
        server_label=(
            "YServerReddit" if experiment.platform_type == "forum" else "YServer"
        ),
    )


@experiments.route("/admin/update_embedding_settings/<int:uid>", methods=["POST"])
@login_required
def update_embedding_settings(uid):
    """Persist memory embedding backend settings to config_server.json."""
    experiment, experiment_dir, error_response = (
        _load_memory_capable_experiment_context(uid)
    )
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

    service = _normalize_embedding_service(request.form.get("embedding_service"))
    host = _normalize_embedding_host(request.form.get("embedding_host"))
    model = str(request.form.get("embedding_model") or "").strip()

    if service == "ollama":
        if not host:
            flash(
                "An Ollama host is required when memory embeddings are enabled.",
                "error",
            )
            return redirect(
                request.referrer or url_for("experiments.embedding_settings", uid=uid)
            )
        if not model:
            flash("Select an embedding model before saving the configuration.", "error")
            return redirect(
                request.referrer or url_for("experiments.embedding_settings", uid=uid)
            )
        config["memory_embeddings"] = {
            "service": service,
            "host": host,
            "model": model,
        }
    else:
        config["memory_embeddings"] = dict(DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS)

    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    flash("Embedding settings updated successfully.", "success")
    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/update_forum_avatar_mode/<int:uid>", methods=["POST"])
@login_required
def update_forum_avatar_mode(uid):
    """Persist forum avatar mode to config_server.json."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
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

    enabled_flag = (
        str(request.form.get("use_actual_profile_pics") or "").strip().lower()
    )
    requested_mode = request.form.get("avatar_mode")
    mode = normalize_forum_avatar_mode(requested_mode)
    if enabled_flag in {"1", "true", "on", "yes"}:
        mode = "actual"

    config["avatar_mode"] = mode

    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    flash("Forum avatar mode updated successfully.", "success")
    return redirect(
        request.referrer or url_for("experiments.experiment_details", uid=uid)
    )


@experiments.route("/admin/update_feed_limits/<int:uid>", methods=["POST"])
@login_required
def update_feed_limits(uid):
    """Update feed retrieval limits for a forum experiment."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
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
            "rss_entries_per_feed": _parse_required_feed_limit(
                "rss_entries_per_feed", int, "RSS entries per feed", minimum=1
            ),
            "reddit_entries_per_feed": _parse_required_feed_limit(
                "reddit_entries_per_feed", int, "Reddit entries per feed", minimum=1
            ),
            "reddit_pages": _parse_required_feed_limit(
                "reddit_pages", int, "Reddit pages", minimum=1
            ),
            "reddit_rate_limit_seconds": _parse_required_feed_limit(
                "reddit_rate_limit_seconds",
                float,
                "Reddit rate limit seconds",
                minimum=0,
            ),
            "db_fallback_limit": _parse_required_feed_limit(
                "db_fallback_limit", int, "Database fallback limit", minimum=1
            ),
            "image_entries_per_feed": _parse_required_feed_limit(
                "image_entries_per_feed", int, "Image entries per feed", minimum=1
            ),
        }
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("experiments.feed_limits", uid=uid))

    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    flash("Feed limits updated successfully.", "success")
    return redirect(request.referrer or url_for("experiments.feed_limits", uid=uid))
