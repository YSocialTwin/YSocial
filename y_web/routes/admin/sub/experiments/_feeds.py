"""
Experiment management routes.

Administrative routes for creating, configuring, launching, and managing
social media simulation experiments including database setup, population
assignment, and experiment lifecycle control.
"""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db  # , app
from y_web.i18n import gettext as _
from y_web.platforms import registry
from y_web.src.commons import reddit_feeds
from y_web.src.models import ForumRssFeedResource
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS, experiments
from ._helpers import *  # noqa: F401,F403
from ._helpers import (
    _load_forum_experiment_context,
    _load_memory_capable_experiment_context,
    _normalize_embedding_host,
    _normalize_embedding_service,
    _normalize_rss_feeds_payload,
    _read_experiment_embedding_settings,
    _read_feed_with_headers,
)


def _forum_rss_resource_payload(resource):
    return {
        "id": resource.id,
        "name": str(resource.name or "").strip(),
        "feed_url": str(resource.feed_url or "").strip(),
        "url_site": str(resource.url_site or "").strip(),
        "description": str(resource.description or "").strip(),
    }


def _write_experiment_rss_feed_file(experiment_dir, resources):
    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    payload = [_forum_rss_resource_payload(resource) for resource in resources]
    with open(rss_feeds_path, "w") as handle:
        json.dump(payload, handle, indent=2)


def _selected_rss_resource_ids(experiment_dir, resources):
    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    if not os.path.exists(rss_feeds_path):
        return []
    try:
        with open(rss_feeds_path, "r") as handle:
            persisted = json.load(handle)
    except Exception:
        return []

    resource_by_url = {
        str(resource.feed_url or "").strip(): resource.id for resource in resources
    }
    selected = []
    for item in persisted if isinstance(persisted, list) else []:
        feed_url = str((item or {}).get("feed_url") or "").strip()
        resource_id = resource_by_url.get(feed_url)
        if resource_id is not None:
            selected.append(resource_id)
    return selected


@experiments.route("/admin/rss_feeds/<int:uid>")
@login_required
def rss_feeds(uid):
    """Display and assign reusable RSS feeds to an experiment."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    url_feeds_path = os.path.join(experiment_dir, "url_feeds.txt")
    available_rss_resources = db.session.scalars(
        select(ForumRssFeedResource).order_by(
            ForumRssFeedResource.name.asc(), ForumRssFeedResource.id.asc()
        )
    ).all()
    selected_rss_resource_ids = _selected_rss_resource_ids(
        experiment_dir, available_rss_resources
    )

    url_feeds_data = []
    if os.path.exists(url_feeds_path):
        try:
            with open(url_feeds_path, "r") as handle:
                url_feeds_data = [line.strip() for line in handle if line.strip()]
        except IOError:
            url_feeds_data = []

    provider = registry.resolve(experiment)
    is_im = provider.news_page_feeds
    snapshot = provider.feeds_context(experiment, experiment_dir) if is_im else None
    return render_template(
        "admin/rss_feeds.html",
        experiment=experiment,
        available_rss_resources=available_rss_resources,
        selected_rss_resource_ids=selected_rss_resource_ids,
        url_feeds=url_feeds_data,
        is_im=is_im,
        snapshot=snapshot,
    )


@experiments.route("/admin/update_rss_feeds/<int:uid>", methods=["POST"])
@login_required
def update_rss_feeds(uid):
    """Persist assigned reusable RSS feeds and local URL feeds."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    url_feeds_path = os.path.join(experiment_dir, "url_feeds.txt")
    selected_ids = []
    for raw_id in request.form.getlist("rss_feed_resource_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    resources = (
        db.session.scalars(
            select(ForumRssFeedResource).filter(
                ForumRssFeedResource.id.in_(selected_ids)
            )
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
    _write_experiment_rss_feed_file(experiment_dir, resources)

    if not registry.resolve(
        experiment
    ).news_page_feeds:  # direct article URLs belong to the platforms that read feeds themselves
        urls_text = request.form.get("url_feeds_text", "")
        urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
        with open(url_feeds_path, "w") as handle:
            handle.write("\n".join(urls))

    if (
        registry.resolve(experiment).feeds_read_at_client_start
        and int(getattr(experiment, "running", 0) or 0) == 1
    ):
        flash(
            _(
                "The updated feed assignment has been saved. Running clients will use the new feeds after they are restarted."
            ),
            "info",
        )
    if registry.resolve(experiment).news_page_feeds:
        flash(
            _(
                "News feeds updated. Clients created from now on get a news page for each feed."
            ),
            "success",
        )
        return redirect(url_for("experiments.experiment_details", uid=uid))
    flash(_("Feed assignments updated successfully."), "success")
    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/api/parse_rss_feed", methods=["POST"])
@login_required
def parse_rss_feed():
    """Parse an RSS URL and return basic feed metadata."""
    check_privileges(current_user.username)

    payload = request.get_json(silent=True) or {}
    feed_url = str(payload.get("feed_url", "")).strip()
    if not feed_url:
        return jsonify({"error": _("No URL provided")}), 400

    if "://" not in feed_url:
        feed_url = f"https://{feed_url}"

    try:
        feed_content = _read_feed_with_headers(feed_url)
        parsed_feed = _parse_admin_feed_metadata(feed_url, feed_content)
        if parsed_feed is None:
            return jsonify({"error": _("Invalid RSS feed URL")}), 400
        return jsonify(parsed_feed)
    except HTTPError as exc:
        return (
            jsonify({"error": _("Feed source returned HTTP %(code)s.", code=exc.code)}),
            400,
        )
    except URLError:
        return jsonify({"error": _("Feed source could not be reached.")}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


def _parse_admin_feed_metadata(feed_url, feed_content):
    """Parse a feed source, accepting RSS/Atom and listing JSON."""
    import feedparser

    feed = feedparser.parse(feed_content)
    if not (feed.bozo and not feed.entries):
        parsed_feed_url = getattr(feed, "href", "") or feed_url
        parsed_url = urlparse(parsed_feed_url)
        site_url = str(feed.feed.get("link") or "").strip()
        site_host = urlparse(site_url).netloc or parsed_url.netloc
        return {
            "name": feed.feed.get("title", site_host or parsed_url.netloc or feed_url),
            "feed_url": parsed_feed_url,
            "url_site": site_url or site_host,
            "description": feed.feed.get("description", ""),
            "entries_count": len(feed.entries),
        }

    reddit_listing = reddit_feeds.parse_json_listing(feed_url, feed_content)
    if reddit_listing is not None:
        return reddit_listing

    return None


@experiments.route("/admin/upload_rss_feeds/<int:uid>", methods=["POST"])
@login_required
def upload_rss_feeds(uid):
    """Bulk upload RSS feeds from JSON."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    if "file" not in request.files:
        return jsonify({"error": _("No file provided")}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": _("No file selected")}), 400

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
        return jsonify({"error": _("Invalid JSON format")}), 400
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
        return jsonify({"error": _("No file provided")}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": _("No file selected")}), 400

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


def _embedding_label(experiment) -> str:
    provider = registry.resolve(experiment)
    if provider.embedding_label:
        return provider.embedding_label
    return "HPC" if experiment.simulator_type == "HPC" else str(provider.label)


def _server_config_name(experiment) -> str:
    provider = registry.resolve(experiment)
    if provider.server_config_name:
        return provider.server_config_name
    return (
        "server_config.json"
        if experiment.simulator_type == "HPC"
        else "config_server.json"
    )


@experiments.route("/admin/embedding_settings/<int:uid>", methods=["GET"])
@login_required
def embedding_settings(uid):
    """Display and edit memory embedding backend settings."""
    experiment, experiment_dir, error_response = (
        _load_memory_capable_experiment_context(uid)
    )
    if error_response is not None:
        return error_response

    return render_template(
        "admin/embedding_settings.html",
        experiment=experiment,
        embedding_settings=_read_experiment_embedding_settings(experiment_dir),
        platform_label=_embedding_label(experiment),
        server_label=registry.resolve(experiment).server_label,
    )


@experiments.route("/admin/update_embedding_settings/<int:uid>", methods=["POST"])
@login_required
def update_embedding_settings(uid):
    """Persist memory embedding backend settings to experiment server config."""
    experiment, experiment_dir, error_response = (
        _load_memory_capable_experiment_context(uid)
    )
    if error_response is not None:
        return error_response

    config_path = os.path.join(experiment_dir, _server_config_name(experiment))
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
                _("An Ollama host is required when memory embeddings are enabled."),
                "error",
            )
            return redirect(
                request.referrer or url_for("experiments.embedding_settings", uid=uid)
            )
        if not model:
            flash(
                _("Select an embedding model before saving the configuration."), "error"
            )
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

    flash(_("Embedding settings updated successfully."), "success")
    return redirect(url_for("experiments.experiment_details", uid=uid))
