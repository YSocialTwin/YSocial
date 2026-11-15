"""
Shared helper functions for the social routes sub-package.

These are private/helper functions that are *not* decorated with ``@main.``.
They are imported by common.py and by the platforms (through ``y_web.sdk.social``) using
absolute imports to avoid circular dependency with _blueprint.py.

This module must NOT import from y_web.routes.social._blueprint or any other
route module at import-time to prevent circular imports.
"""

import json
import os
from typing import Optional

from flask import request
from flask_login import current_user
from sqlalchemy import or_, select

from y_web import db
from y_web.platforms import registry as platforms
from y_web.src.commons.ids import opaque_id
from y_web.src.commons.ordering import seq_or_id
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


def _root_post_filter(column):
    return or_(column.is_(None), column == -1)


from y_web.i18n import N_, gettext
from y_web.src.system.path_utils import get_writable_path

_ADHOC_AGENT_BADGE_LABELS = {
    "hello_world": N_("Hello World"),
    "moderator": N_("Moderator Agent"),
    "propaganda": N_("Propaganda Agent"),
    "master_of_puppets": N_("Master of Puppets"),
    "mop_puppet": N_("MoP Puppet"),
    "stress_attacker": N_("Stress Attacker"),
    "comic_relief": N_("Comic Relief Agent"),
}


def get_adhoc_agent_badge(user) -> Optional[str]:
    user_type = str(getattr(user, "user_type", "") or "").strip().lower()
    return _ADHOC_AGENT_BADGE_LABELS.get(user_type)


def get_author_type_badge(user) -> str:
    """Return a badge label identifying whether the author is an AI agent or a human."""
    raw = getattr(user, "user_type", None)
    user_type = str(raw if raw is not None else "").strip().lower()
    # Standard agents store the LLM model name in user_type (and some store
    # ""), so anything other than None / "user" is an agent.
    if raw is not None and user_type != "user":
        return N_("AI Agent")  # shown through _(); templates compare the English token
    return N_("Human")


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
            pg = db.session.scalars(select(Page).filter_by(name=username)).first()
            if pg is not None and hasattr(pg, "logo") and pg.logo:
                return pg.logo
        except:
            pass
    else:
        try:
            ag = db.session.scalars(select(Agent).filter_by(name=username)).first()
            if ag is not None and hasattr(ag, "profile_pic") and ag.profile_pic:
                return ag.profile_pic
        except:
            pass

        try:
            admin_user = db.session.scalars(
                select(Admin_users).filter_by(username=username)
            ).first()
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
    user = db.session.scalars(select(Admin_users).filter_by(username=username)).first()
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
    exp = db.session.scalars(select(Exps).filter_by(idexp=int(exp_id))).first()
    provider = platforms.resolve(exp)

    from y_web.src.commons.service import (
        _format_display_time,
        _format_display_time_from_created_at,
    )

    # Get experiment user ID if not provided
    if exp_user_id is None:
        exp_user = db.session.scalars(
            select(User_mgmt).filter_by(username=current_user.username)
        ).first()
        exp_user_id = exp_user.id if exp_user else current_user.id

    from y_web.src.data_access.posts import (
        _hidden_author_ids_for_viewer,
        _hidden_post_ids_in_thread,
    )

    hidden_ids = _hidden_author_ids_for_viewer(exp_id, exp_user_id)

    for post in posts.items:
        try:
            post = post[0]
        except:
            pass

        if hidden_ids and post.user_id in hidden_ids:
            continue

        comments = (
            Post.query.filter(Post.thread_id == post.id, Post.id != post.id)
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username)
            .all()
        )
        if hidden_ids:
            records = [(c.id, c.user_id, c.comment_to) for c, _author in comments]
            dropped_ids = _hidden_post_ids_in_thread(records, hidden_ids)
            comments = [
                (c, author) for c, author in comments if c.id not in dropped_ids
            ]

        cms = []
        for c, author in comments:
            # get elicited emotions names
            emotions = get_elicited_emotions(c.id)

            if username == author:
                text = c.tweet.split(":")[-1].replace(f"@{username}", "")
            else:
                text = c.tweet.split(":")[-1]

            user = db.session.scalars(select(User_mgmt).filter_by(id=c.user_id)).first()
            profile_pic = provider.profile_picture(user)
            if profile_pic is None:
                profile_pic = ""
                if user.is_page == 1:
                    pg = db.session.scalars(
                        select(Page).filter_by(name=user.username)
                    ).first()
                    if page is not None and pg is not None:
                        profile_pic = pg.logo
                else:
                    try:
                        ag = db.session.scalars(
                            select(Agent).filter_by(name=user.username)
                        ).first()
                        profile_pic = (
                            ag.profile_pic
                            if ag is not None and ag.profile_pic is not None
                            else Admin_users.query.filter_by(username=user.username)
                            .first()
                            .profile_pic
                        )
                    except Exception:
                        profile_pic = ""

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
                    "day": db.session.scalars(select(Rounds).filter_by(id=c.round))
                    .first()
                    .day,
                    "hour": db.session.scalars(select(Rounds).filter_by(id=c.round))
                    .first()
                    .hour,
                    "likes": len(
                        db.session.scalars(
                            select(Reactions).filter_by(post_id=c.id, type="like")
                        ).all()
                    ),
                    "dislikes": len(
                        db.session.scalars(
                            select(Reactions).filter_by(post_id=c.id, type="dislike")
                        ).all()
                    ),
                    "is_liked": db.session.scalars(
                        select(Reactions).filter_by(
                            post_id=c.id, user_id=exp_user_id, type="like"
                        )
                    ).first()
                    is None,
                    "is_disliked": db.session.scalars(
                        select(Reactions).filter_by(
                            post_id=c.id, user_id=exp_user_id, type="dislike"
                        )
                    ).first()
                    is None,
                    "is_shared": len(
                        db.session.scalars(
                            select(Post).filter_by(shared_from=c.id)
                        ).all()
                    ),
                    "report_count": get_report_count(c.id),
                    "emotions": emotions,
                    "topics": topics,
                    "adhoc_agent_badge": get_adhoc_agent_badge(user),
                    "author_type_badge": get_author_type_badge(user),
                    "is_moderation_comment": int(
                        getattr(c, "is_moderation_comment", 0) or 0
                    ),
                }
            )

        article = db.session.scalars(
            select(Articles).filter_by(id=post.news_id)
        ).first()
        if article is None:
            art = 0
        else:
            _website = db.session.scalars(
                select(Websites).filter_by(id=article.website_id)
            ).first()
            art = {
                "title": article.title,
                "summary": strip_tags(article.summary),
                "url": article.link,
                "source": _website.name if _website is not None else "",
            }

        image = db.session.scalars(select(Images).filter_by(id=post.image_id)).first()
        if image is None:
            image = ""

        c = db.session.scalars(select(Rounds).filter_by(id=post.round)).first()
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
        aa = db.session.scalars(select(User_mgmt).filter_by(id=post.user_id)).first()

        # Handle case where user doesn't exist
        if aa is None:
            # Skip this post if the author doesn't exist in user_mgmt
            continue

        profile_pic = provider.profile_picture(aa)
        if profile_pic is None:
            profile_pic = ""
            if aa.is_page == 1:
                pg = db.session.scalars(
                    select(Page).filter_by(name=aa.username)
                ).first()
                if pg is not None:
                    profile_pic = pg.logo
            else:
                try:
                    ag = db.session.scalars(
                        select(Agent).filter_by(name=aa.username)
                    ).first()
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
        primary_community = provider.discussion_community(article, topics)

        # Get author username safely
        author_user = db.session.scalars(
            select(User_mgmt).filter_by(id=post.user_id)
        ).first()
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
                    db.session.scalars(
                        select(Reactions).filter_by(post_id=post.id, type="like")
                    ).all()
                ),
                "dislikes": len(
                    db.session.scalars(
                        select(Reactions).filter_by(post_id=post.id, type="dislike")
                    ).all()
                ),
                "is_liked": db.session.scalars(
                    select(Reactions).filter_by(
                        post_id=post.id, user_id=exp_user_id, type="like"
                    )
                ).first()
                is None,
                "is_disliked": db.session.scalars(
                    select(Reactions).filter_by(
                        post_id=post.id, user_id=exp_user_id, type="dislike"
                    )
                ).first()
                is None,
                "is_shared": len(
                    db.session.scalars(
                        select(Post).filter_by(shared_from=post.id)
                    ).all()
                ),
                "report_count": get_report_count(post.id),
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
                "topics": topics,
                "adhoc_agent_badge": get_adhoc_agent_badge(aa),
                "author_type_badge": get_author_type_badge(aa),
                "is_moderation_comment": int(
                    getattr(post, "is_moderation_comment", 0) or 0
                ),
                "primary_community": primary_community,
            }
        )

    return res


#### Participant helpers


def _logged_experiment_user():
    user = db.session.scalars(
        select(User_mgmt).filter_by(username=current_user.username)
    ).first()
    if user is None and str(getattr(current_user, "id", "")).isdigit():
        user = db.session.scalars(
            select(User_mgmt).filter_by(id=opaque_id(current_user.id))
        ).first()
    return user


def _participant_profile_pic(user):
    return resolve_forum_profile_pic(user, get_current_experiment_id())


def _current_profile_pic(exp_id, participant=None):
    if participant is not None:
        return resolve_forum_profile_pic(participant, exp_id)
    return resolve_forum_username_avatar(current_user.username, exp_id)


def _experiment_memory_enabled(exp_id):
    from y_web.src.system.memory_plugin import agent_memory_plugin_installed

    if not agent_memory_plugin_installed():
        return False
    exp = db.session.scalars(select(Exps).filter_by(idexp=int(exp_id))).first()
    if not exp or not platforms.resolve(exp).reads_server_config:
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

    # the client configs of the platforms that read the server config
    exp_dir = os.path.dirname(config_path)
    try:
        for entry in os.listdir(exp_dir):
            is_standard_client = entry.startswith("client_") and entry.endswith(".json")
            is_hpc_client = (
                entry.endswith("_config.json") and entry != "server_config.json"
            )
            if not is_standard_client and not is_hpc_client:
                continue
            client_path = os.path.join(exp_dir, entry)
            try:
                with open(client_path, "r", encoding="utf-8") as client_handle:
                    client_config = json.load(client_handle) or {}
                # Most client configs nest under "agents"
                agents_cfg = client_config.get("agents")
                if isinstance(agents_cfg, dict) and bool(
                    agents_cfg.get("memory_enabled")
                ):
                    return True
                # Others use a flat "memory_enabled" key
                if bool(client_config.get("memory_enabled", False)):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _resolve_feed_back_url(exp_id):
    back_url = (request.args.get("back") or "").strip()
    if back_url.startswith(f"/{exp_id}/rfeed") or back_url.startswith(
        f"/{exp_id}/rsearch"
    ):
        return back_url
    referrer = (request.referrer or "").strip()
    if f"/{exp_id}/rfeed" in referrer or f"/{exp_id}/rsearch" in referrer:
        return referrer
    return f"/{exp_id}/rfeed/all/feed/rf/1?feed_type=new"


# ---------------------------------------------------------------------------
# Frontend UI settings — loaded per experiment for public-facing pages
# ---------------------------------------------------------------------------
from y_web.src.experiment.frontend_defaults import (
    DEFAULT_SETTINGS as _UI_DEFAULTS,
)  # noqa: E402


def _load_ui_settings(exp_id: int) -> dict:
    """Return the frontend settings dict for *exp_id*, merged with defaults.

    Imported lazily to avoid a circular-import cycle at module load time.
    Safe to call both inside and outside an experiment_db_bind context
    (settings live in the *dashboard* DB, not the experiment DB).
    """
    try:
        from y_web.src.experiment.frontend_defaults import (  # noqa: PLC0415
            defaults_for,
        )
        from y_web.src.models import ExpFrontendSettings  # noqa: PLC0415
        from y_web.src.models import Exps  # noqa: PLC0415

        exp = db.session.get(Exps, exp_id)
        defaults = defaults_for(exp.platform_type if exp else None)
        row = db.session.get(ExpFrontendSettings, exp_id)
        if row is None:
            return defaults
        loaded = json.loads(row.settings_json or "{}")
        merged = dict(defaults)
        merged.update(loaded)
        return merged
    except Exception:
        return dict(_UI_DEFAULTS)


# What the explanation says when the platform has none for the mode of the person.
_RECSYS_FALLBACK = N_(
    "This is the algorithm that decides which posts appear in your feed and in what order."
)


def _content_recsys_info(recsys_type, ui=None, recsys=None):
    """``{"name", "label", "description"}`` of a user's content recommender system, or ``None``.

    ``None`` when the experiment's ``show_recsys_info`` setting is off, so templates can test it directly, and when
    no ``recsys`` (the ``HumanRecsysTraits`` of the platform) is given: the platform names and explains its modes.
    """
    if ui is not None and not ui.get("show_recsys_info"):
        return None
    if recsys is None:
        return None
    try:
        from y_web.src.models.config import Content_Recsys  # noqa: PLC0415

        raw = str(recsys_type or "").strip() or "default"
        mode = recsys.normalize(raw)
        label = None
        for row in db.session.scalars(db.select(Content_Recsys)).all():
            if recsys.normalize(row.name) == mode:
                label = row.value
                break
        if label is None:
            label = {"Random": "Random"}.get(mode, mode)
        return {
            "name": mode,
            "label": label,
            "description": gettext(recsys.describe(mode) or _RECSYS_FALLBACK),
        }
    except Exception:
        return None


def _platform_ui_context():
    """Template context for the pages a platform adds variables to (``provider.page_context``).

    The default platform's routes pass ``ui`` explicitly; the other platforms render many templates from many places, so
    they receive the same per-experiment settings (``/admin/frontend_settings``) from here instead: ``ui``, the
    frontend plugin modules (unless the platform has none on its pages) and what the platform adds.
    Never touches pages of other blueprints or of experiments whose platform adds nothing.
    """
    try:
        if request.blueprint != "main":
            return {}
        raw = (request.view_args or {}).get("exp_id")
        if raw is None:
            return {}
        from y_web.src.models import Exps  # noqa: PLC0415

        exp = db.session.get(Exps, int(raw))
        if exp is None:
            return {}
        ui = _load_ui_settings(int(raw))
        extra = platforms.resolve(exp).page_context(exp, ui)
        if extra is None:
            return {}
        extra = dict(extra)
        modules = []
        if extra.pop("frontend_plugins", True):
            try:
                from y_web.src.external_runtime.plugin_loader import (  # noqa: PLC0415
                    active_modules_context,
                )

                modules = active_modules_context(int(raw))
            except Exception:
                modules = []
        return {"frontend_adds_on_modules": modules, "ui": ui, **extra}
    except Exception:
        return {}
