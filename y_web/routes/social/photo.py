"""
Photo sharing platform routes.

Provides an Instagram-like feed for YPhotoSharing experiments while keeping the
same routing conventions used by the microblogging and forum frontends.
"""

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from y_web.routes.social._blueprint import main
from y_web.routes.social.helpers import (
    _experiment_memory_enabled,
    _get_discussions,
    get_safe_profile_pic,
    is_admin,
)
from y_web.src.data_access import get_unanswered_mentions
from y_web.src.experiment.helpers import ensure_experiment_user
from y_web.src.models import Exps, User_mgmt
from y_web.src.recsys.content_recsys import get_suggested_posts
from y_web.src.recsys.follow_recsys import get_suggested_users


def _photo_logged_user_id():
    logged_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if logged_user is not None:
        return logged_user.id
    return getattr(current_user, "id", 0) or 0


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

    if user_id == "all":
        posts, additional = get_suggested_posts("all", "", page, max_post_per_page)
    else:
        try:
            user = User_mgmt.query.filter_by(id=user_id).first()
            if not user:
                user = User_mgmt.query.filter_by(username=current_user.username).first()
        except Exception:
            user = None
        if not user:
            return redirect(f"/{exp_id}/photo/feed/all/feed/rf/1")
        posts, additional = get_suggested_posts(
            user_id, "ReverseChrono", page, max_post_per_page
        )
        username = user.username

    res = []
    exp_user_id = exp_user.id if exp_user else _photo_logged_user_id()

    if posts is not None:
        res = _get_discussions(posts, username, page, exp_id, exp_user_id)
    if additional is not None:
        res_additional = _get_discussions(
            additional, username, page, exp_id, exp_user_id
        )
        if res_additional:
            res.extend(res_additional)

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
    stories = _build_photo_stories(res, sfollow + spages)

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
        logged_id=logged_user.id,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        sfollow=sfollow,
        spages=spages,
        experiment_memory_enabled=_experiment_memory_enabled(exp_id),
        photo_sidebar_collapsed=True,
    )
