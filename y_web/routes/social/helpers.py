"""
Shared helper functions for the social routes sub-package.

These are private/helper functions that are *not* decorated with ``@main.``.
They are imported by common.py, microblogging.py, and forum.py using
absolute imports to avoid circular dependency with _blueprint.py.

This module must NOT import from y_web.routes.social._blueprint or any other
route module at import-time to prevent circular imports.
"""

import json
import os
from typing import Optional

from flask import request
from flask_login import current_user

from y_web import db
from y_web.src.content.avatars import (
    resolve_forum_profile_pic,
    resolve_forum_username_avatar,
)
from y_web.src.content.text_utils import process_reddit_post, strip_tags
from y_web.src.data_access import (
    augment_text,
    get_elicited_emotions,
    get_report_count,
    get_topics,
)
from y_web.src.experiment.context import get_current_experiment_id
from y_web.src.experiment.helpers import get_experiment_uid_from_db_name
from y_web.src.models import (
    Admin_users,
    Agent,
    Articles,
    Exps,
    Images,
    Page,
    Post,
    Reactions,
    Rounds,
    User_mgmt,
    Websites,
)
from y_web.src.system.path_utils import get_writable_path

_ADHOC_AGENT_BADGE_LABELS = {
    "hello_world": "Hello World",
    "moderator": "Moderator Agent",
    "propaganda": "Propaganda Agent",
    "master_of_puppets": "Master of Puppets",
    "mop_puppet": "MoP Puppet",
    "stress_attacker": "Stress Attacker",
    "comic_relief": "Comic Relief Agent",
}


def get_adhoc_agent_badge(user) -> Optional[str]:
    user_type = str(getattr(user, "user_type", "") or "").strip().lower()
    return _ADHOC_AGENT_BADGE_LABELS.get(user_type)


def get_safe_profile_pic(username, is_page=0):
    """
    Safely retrieve profile picture URL for a user or page.

    Attempts multiple sources with graceful fallback handling.

    Args:
        username: Username to get profile picture for
        is_page: 1 if username refers to a page, 0 for regular user

    Returns:
        Profile picture URL string, or empty string if not found
    """
    if is_page == 1:
        try:
            pg = Page.query.filter_by(name=username).first()
            if pg is not None and hasattr(pg, "logo") and pg.logo:
                return pg.logo
        except:
            pass
    else:
        try:
            ag = Agent.query.filter_by(name=username).first()
            if ag is not None and hasattr(ag, "profile_pic") and ag.profile_pic:
                return ag.profile_pic
        except:
            pass

        try:
            admin_user = Admin_users.query.filter_by(username=username).first()
            if (
                admin_user is not None
                and hasattr(admin_user, "profile_pic")
                and admin_user.profile_pic
            ):
                return admin_user.profile_pic
        except:
            pass

    return ""


def is_admin(username):
    """
    Check if a user has admin role.

    Args:
        username: Username to check

    Returns:
        True if user is admin, False otherwise
    """
    user = Admin_users.query.filter_by(username=username).first()
    if user.role != "admin":
        return False
    return True


def _expand_tree(post_to_child, post_to_data):
    """Handle expand tree operation."""
    for pid, clds in post_to_child.items():
        for cl in clds:
            post_to_data[pid]["children"].append(post_to_data[cl])

    return post_to_data


def build_thread_tree(root_id, post_to_data, parent_lookup):
    """Build a thread tree without depending on row ordering."""
    post_to_child = {pid: [] for pid in post_to_data.keys()}
    post_to_child.setdefault(root_id, [])

    for post_id, parent_id in parent_lookup.items():
        if post_id == root_id:
            continue

        normalized_parent = parent_id
        if normalized_parent in (None, "", -1, "-1"):
            normalized_parent = root_id

        if normalized_parent not in post_to_data:
            normalized_parent = root_id

        post_to_child.setdefault(normalized_parent, []).append(post_id)

    tree = _expand_tree(post_to_child, post_to_data)
    return tree[root_id]


def recursive_visit(data):
    """Handle recursive visit operation."""
    if len(data["children"]) == 0:
        return data["post"]
    else:
        for c in data["children"]:
            return recursive_visit(c)


def _get_discussions(posts, username, page, exp_id, exp_user_id=None):
    """Handle get discussions operation."""
    res = []
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    is_forum = getattr(exp, "platform_type", "") == "forum"

    from y_web.src.forum.service import (
        _format_display_time,
        _format_display_time_from_created_at,
    )
    from y_web.src.forum.service.queries import _primary_community_payload

    # Get experiment user ID if not provided
    if exp_user_id is None:
        exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
        exp_user_id = exp_user.id if exp_user else current_user.id

    for post in posts.items:
        try:
            post = post[0]
        except:
            pass

        comments = (
            Post.query.filter(Post.thread_id == post.id, Post.id != post.id)
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username)
            .all()
        )

        cms = []
        for c, author in comments:
            # get elicited emotions names
            emotions = get_elicited_emotions(c.id)

            if username == author:
                text = c.tweet.split(":")[-1].replace(f"@{username}", "")
            else:
                text = c.tweet.split(":")[-1]

            user = User_mgmt.query.filter_by(id=c.user_id).first()
            if is_forum:
                profile_pic = _forum_profile_pic(user)
            else:
                profile_pic = ""
                if user.is_page == 1:
                    pg = Page.query.filter_by(name=user.username).first()
                    if page is not None and pg is not None:
                        profile_pic = pg.logo
                else:
                    ag = Agent.query.filter_by(name=user.username).first()
                    profile_pic = (
                        ag.profile_pic
                        if ag is not None and ag.profile_pic is not None
                        else Admin_users.query.filter_by(username=user.username)
                        .first()
                        .profile_pic
                    )

            topics = get_topics(c.id, c.user_id)
            if len(topics) == 0:
                topics = []

            # Get shared post info safely - handle both int and UUID shared_from
            if c.shared_from == -1:
                shared_from_info = -1
            else:
                shared_user = (
                    db.session.query(User_mgmt)
                    .join(Post, User_mgmt.id == Post.user_id)
                    .filter(Post.id == c.shared_from)
                    .first()
                )
                shared_from_info = (
                    (c.shared_from, shared_user.username)
                    if shared_user
                    else (c.shared_from, "Unknown")
                )

            cms.append(
                {
                    "post_id": c.id,
                    "profile_pic": profile_pic,
                    "author": author,
                    "shared_from": shared_from_info,
                    "author_id": c.user_id,
                    "post": augment_text(text, exp_id),
                    "round": c.round,
                    "day": Rounds.query.filter_by(id=c.round).first().day,
                    "hour": Rounds.query.filter_by(id=c.round).first().hour,
                    "likes": len(
                        list(Reactions.query.filter_by(post_id=c.id, type="like"))
                    ),
                    "dislikes": len(
                        list(Reactions.query.filter_by(post_id=c.id, type="dislike"))
                    ),
                    "is_liked": Reactions.query.filter_by(
                        post_id=c.id, user_id=exp_user_id, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=exp_user_id, type="dislike"
                    ).first()
                    is None,
                    "is_shared": len(Post.query.filter_by(shared_from=c.id).all()),
                    "report_count": get_report_count(c.id),
                    "emotions": emotions,
                    "topics": topics,
                    "adhoc_agent_badge": get_adhoc_agent_badge(user),
                    "is_moderation_comment": int(
                        getattr(c, "is_moderation_comment", 0) or 0
                    ),
                }
            )

        article = Articles.query.filter_by(id=post.news_id).first()
        if article is None:
            art = 0
        else:
            art = {
                "title": article.title,
                "summary": strip_tags(article.summary),
                "url": article.link,
                "source": Websites.query.filter_by(id=article.website_id).first().name,
            }

        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour
        display_time = _format_display_time_from_created_at(
            getattr(post, "created_at", None)
        ) or _format_display_time(
            str(day),
            f"{int(hour):02d}" if str(hour).isdigit() else str(hour),
        )

        # get elicited emotions names
        emotions = get_elicited_emotions(post.id)
        aa = User_mgmt.query.filter_by(id=post.user_id).first()

        # Handle case where user doesn't exist
        if aa is None:
            # Skip this post if the author doesn't exist in user_mgmt
            continue

        if is_forum:
            profile_pic = _forum_profile_pic(aa)
        else:
            profile_pic = ""
            if aa.is_page == 1:
                pg = Page.query.filter_by(name=aa.username).first()
                if pg is not None:
                    profile_pic = pg.logo
            else:
                try:
                    ag = Agent.query.filter_by(name=aa.username).first()
                    profile_pic = (
                        ag.profile_pic
                        if ag is not None and ag.profile_pic is not None
                        else Admin_users.query.filter_by(username=aa.username)
                        .first()
                        .profile_pic
                    )
                except:
                    profile_pic = ""

        topics = get_topics(post.id, post.user_id)
        if len(topics) == 0:
            topics = []
        primary_community = (
            _primary_community_payload(article, topics) if is_forum else None
        )

        # Get author username safely
        author_user = User_mgmt.query.filter_by(id=post.user_id).first()
        author_username = author_user.username if author_user else "Unknown"
        title, body = process_reddit_post(post.tweet)
        processed_body = augment_text(body, exp_id) if body else ""

        # Get shared post info safely
        if post.shared_from == -1:
            shared_from_info = -1
        else:
            shared_user = (
                db.session.query(User_mgmt)
                .join(Post, User_mgmt.id == Post.user_id)
                .filter(Post.id == post.shared_from)
                .first()
            )
            shared_from_info = (
                (post.shared_from, shared_user.username)
                if shared_user
                else (post.shared_from, "Unknown")
            )

        res.append(
            {
                "article": art,
                "image": image,
                "profile_pic": profile_pic,
                "thread_id": post.thread_id,
                "shared_from": shared_from_info,
                "post_id": post.id,
                "author": author_username,
                "author_id": post.user_id,
                "title": title,
                "post": processed_body,
                "round": post.round,
                "day": day,
                "hour": hour,
                "display_time": display_time,
                "created_at": (
                    getattr(post, "created_at", None).isoformat()
                    if getattr(post, "created_at", None)
                    else None
                ),
                "likes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="like"))
                ),
                "dislikes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="dislike"))
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=exp_user_id, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=exp_user_id, type="dislike"
                ).first()
                is None,
                "is_shared": len(Post.query.filter_by(shared_from=post.id).all()),
                "report_count": get_report_count(post.id),
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
                "topics": topics,
                "adhoc_agent_badge": get_adhoc_agent_badge(aa),
                "is_moderation_comment": int(
                    getattr(post, "is_moderation_comment", 0) or 0
                ),
                "primary_community": primary_community,
            }
        )

    return res


#### Forum helpers


def _forum_logged_user():
    user = User_mgmt.query.filter_by(username=current_user.username).first()
    if user is None and str(getattr(current_user, "id", "")).isdigit():
        user = User_mgmt.query.filter_by(id=int(current_user.id)).first()
    return user


def _forum_profile_pic(user):
    return resolve_forum_profile_pic(user, get_current_experiment_id())


def _forum_current_profile_pic(exp_id, forum_user=None):
    if forum_user is not None:
        return resolve_forum_profile_pic(forum_user, exp_id)
    return resolve_forum_username_avatar(current_user.username, exp_id)


def _experiment_memory_enabled(exp_id):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") not in {"forum", "microblogging"}:
        return False

    uid = get_experiment_uid_from_db_name(
        str(getattr(exp, "db_name", "") or "").replace("\\", "/")
    )
    if not uid:
        return False

    config_path = os.path.join(
        get_writable_path(),
        "y_web",
        "experiments",
        str(uid),
        (
            "server_config.json"
            if getattr(exp, "simulator_type", "Standard") == "HPC"
            else "config_server.json"
        ),
    )
    if not os.path.exists(config_path):
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle) or {}
    except Exception:
        return False

    memory_cfg = config.get("memory")
    if isinstance(memory_cfg, dict) and "enabled" in memory_cfg:
        if bool(memory_cfg.get("enabled")):
            return True

    # Also handle flat format written by client config routes: {"memory_enabled": true, ...}
    if bool(config.get("memory_enabled", False)):
        return True

    platform = getattr(exp, "platform_type", "")
    if platform in {"microblogging", "forum"}:
        exp_dir = os.path.dirname(config_path)
        try:
            for entry in os.listdir(exp_dir):
                is_standard_client = entry.startswith("client_") and entry.endswith(
                    ".json"
                )
                is_hpc_client = (
                    entry.endswith("_config.json") and entry != "server_config.json"
                )
                if not is_standard_client and not is_hpc_client:
                    continue
                client_path = os.path.join(exp_dir, entry)
                try:
                    with open(client_path, "r", encoding="utf-8") as client_handle:
                        client_config = json.load(client_handle) or {}
                    # Microblogging and HPC client configs nest under "agents"
                    agents_cfg = client_config.get("agents")
                    if isinstance(agents_cfg, dict) and bool(
                        agents_cfg.get("memory_enabled")
                    ):
                        return True
                    # Forum client configs use a flat "memory_enabled" key
                    if bool(client_config.get("memory_enabled", False)):
                        return True
                except Exception:
                    continue
        except Exception:
            return False
    return False


def _forum_memory_enabled(exp_id):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp or getattr(exp, "platform_type", "") != "forum":
        return False
    return _experiment_memory_enabled(exp_id)


def _forum_paginate_posts(page, per_page, feed_type, search_query=""):
    from sqlalchemy import desc, func, or_

    normalized_feed = (feed_type or "new").strip().lower()
    if normalized_feed not in {"new", "hot", "top", "most_commented"}:
        normalized_feed = "new"

    base_query = Post.query.filter(Post.comment_to == -1)
    if search_query:
        like = f"%{search_query}%"
        base_query = (
            base_query.outerjoin(User_mgmt, User_mgmt.id == Post.user_id)
            .outerjoin(Articles, Articles.id == Post.news_id)
            .filter(
                or_(
                    Post.tweet.ilike(like),
                    User_mgmt.username.ilike(like),
                    Articles.title.ilike(like),
                    Articles.link.ilike(like),
                )
            )
        )

    if normalized_feed in {"top", "hot"}:
        query = (
            base_query.outerjoin(Reactions, Post.id == Reactions.post_id)
            .outerjoin(Rounds, Post.round == Rounds.id)
            .add_columns(
                Post,
                func.sum(
                    (Reactions.type == "like").cast(db.Integer)
                    - (Reactions.type == "dislike").cast(db.Integer)
                ).label("score"),
            )
            .group_by(Post.id)
            .order_by(
                desc("score"),
                desc(func.coalesce(Rounds.day, -1)),
                desc(func.coalesce(Rounds.hour, -1)),
                desc(Post.id),
            )
        )
    elif normalized_feed == "most_commented":
        query = base_query.outerjoin(Rounds, Post.round == Rounds.id).order_by(
            desc(func.coalesce(Rounds.day, -1)),
            desc(func.coalesce(Rounds.hour, -1)),
            desc(Post.id),
        )
    else:
        query = base_query.outerjoin(Rounds, Post.round == Rounds.id).order_by(
            desc(func.coalesce(Rounds.day, -1)),
            desc(func.coalesce(Rounds.hour, -1)),
            desc(Post.id),
        )

    return normalized_feed, query.paginate(
        page=page, per_page=per_page, error_out=False
    )


def _forum_resolve_back_url(exp_id):
    back_url = (request.args.get("back") or "").strip()
    if back_url.startswith(f"/{exp_id}/rfeed") or back_url.startswith(
        f"/{exp_id}/rsearch"
    ):
        return back_url
    referrer = (request.referrer or "").strip()
    if f"/{exp_id}/rfeed" in referrer or f"/{exp_id}/rsearch" in referrer:
        return referrer
    return f"/{exp_id}/rfeed/all/feed/rf/1?feed_type=new"
