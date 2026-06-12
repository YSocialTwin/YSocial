"""
Common/profile routes for both microblogging and forum platforms.

Routes: index, profile, profile_logged, edit_profile, update_profile_data,
        update_password.
"""

import json
import math
import os

from flask import (
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import and_, desc
from sqlalchemy.sql.expression import func
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.routes.social._blueprint import main
from y_web.routes.social.helpers import (
    _forum_current_profile_pic,
    _forum_logged_user,
    _forum_memory_enabled,
    _forum_profile_pic,
    get_safe_profile_pic,
    is_admin,
)
from y_web.src.agents.custom_features import summarize_agent_custom_features
from y_web.src.content.cover_images import (
    DEFAULT_COVER_IMAGE_PATH,
    available_cover_image_urls,
    normalize_cover_image_url,
    random_cover_image_url,
)
from y_web.src.data_access import (
    count_followees,
    count_followers,
    get_mutual_friends,
    get_top_user_hashtags,
    get_unanswered_mentions,
    get_user_recent_interests,
    get_user_recent_posts,
)
from y_web.src.experiment.helpers import get_experiment_uid_from_db_name
from y_web.src.models import (
    Admin_users,
    Agent,
    Emotions,
    Exps,
    Follow,
    Hashtags,
    Page,
    Post,
    Post_emotions,
    Post_hashtags,
    Reactions,
    Rounds,
    StressReward,
    User_mgmt,
)
from y_web.src.recsys import get_suggested_users
from y_web.src.system.path_utils import get_writable_path


def _latest_follow_action(*, follower_id, user_id):
    follow_event = (
        db.session.query(Follow)
        .outerjoin(Rounds, Follow.round == Rounds.id)
        .filter(Follow.user_id == follower_id, Follow.follower_id == user_id)
        .order_by(Rounds.day.desc(), Rounds.hour.desc(), Follow.id.desc())
        .first()
    )
    return str(getattr(follow_event, "action", "") or "").strip().lower()


def _experiment_server_config(exp):
    if not exp or getattr(exp, "platform_type", "") not in {"forum", "microblogging"}:
        return {}

    uid = get_experiment_uid_from_db_name(
        str(getattr(exp, "db_name", "") or "").replace("\\", "/")
    )
    if not uid:
        return {}

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
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except Exception:
        return {}


def _stress_reward_enabled_for_exp(exp):
    if not exp or getattr(exp, "platform_type", "") not in {"microblogging", "forum"}:
        return False

    config = _experiment_server_config(exp)
    stress_reward_cfg = config.get("stress_reward")
    if isinstance(stress_reward_cfg, dict):
        return bool(
            stress_reward_cfg.get(
                "enabled",
                config.get(
                    "stress_reward_enabled",
                    config.get("stress_reward_annotation", False),
                ),
            )
        )

    return bool(
        config.get(
            "stress_reward_enabled", config.get("stress_reward_annotation", False)
        )
    )


def _stress_reward_scale_level(value):
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        numeric = 0.0
    numeric = max(0.0, min(1.0, numeric))
    if numeric <= 0.0:
        return 0
    return max(1, min(5, int(math.ceil(numeric * 5))))


def _latest_stress_reward_indicator(user_id):
    indicator = {
        "stress": {"value": 0.0, "level": 0},
        "reward": {"value": 0.0, "level": 0},
    }

    for variable in ("stress", "reward"):
        row = (
            StressReward.query.filter_by(
                uid=user_id, variable=variable, type="aggregate"
            )
            .order_by(StressReward.tid.desc())
            .first()
        )
        value = float(getattr(row, "value", 0.0) or 0.0)
        indicator[variable] = {
            "value": value,
            "level": _stress_reward_scale_level(value),
        }

    return indicator


def _default_cover_image_url():
    return DEFAULT_COVER_IMAGE_PATH


def _get_user_cover_image(user_id):
    default_cover = _default_cover_image_url()
    try:
        user = User_mgmt.query.filter_by(id=user_id).first()
    except Exception:
        return default_cover

    cover_image = str(getattr(user, "cover_image", "") or "").strip() if user else ""
    if cover_image:
        return cover_image

    if user is not None:
        user.cover_image = random_cover_image_url()
        try:
            db.session.commit()
            return user.cover_image
        except Exception:
            db.session.rollback()

    return default_cover


def _set_user_cover_image(user_id, cover_image):
    user = User_mgmt.query.filter_by(id=user_id).first()
    if user is not None:
        user.cover_image = normalize_cover_image_url(cover_image)


@main.get("/uploads/<path:relative_path>")
def serve_upload(relative_path: str):
    uploads_root = os.path.join(get_writable_path(), "y_web", "uploads")
    return send_from_directory(uploads_root, relative_path)


@main.route("/")
def index():
    """
    Home page route - redirects authenticated users to feed, others to login.

    Returns:
        Redirect to appropriate page based on authentication status
    """
    if current_user.is_authenticated:
        # get active experiments
        exps = Exps.query.filter(Exps.status != 0).all()
        if exps:
            # If multiple experiments, redirect to join menu
            if len(exps) > 1:
                return redirect("/admin/join_simulation")
            # If single experiment, redirect directly to feed
            exp = exps[0]

            # Get experiment user ID (not admin user ID)
            # Temporarily bind to experiment database to query user
            from y_web.src.experiment.context import get_db_bind_key_for_exp

            bind_key = get_db_bind_key_for_exp(exp.idexp)

            # Query User_mgmt from experiment database
            exp_user_id = current_user.id  # fallback to admin ID
            try:
                # Use the experiment's database bind
                from y_web import db
                from y_web.src.models import User_mgmt

                # Temporarily override db_exp bind to query correct database
                original_bind = db.get_app().config["SQLALCHEMY_BINDS"].get("db_exp")
                if bind_key in db.get_app().config["SQLALCHEMY_BINDS"]:
                    db.get_app().config["SQLALCHEMY_BINDS"][
                        "db_exp"
                    ] = db.get_app().config["SQLALCHEMY_BINDS"][bind_key]

                    exp_user = User_mgmt.query.filter_by(
                        username=current_user.username
                    ).first()
                    if exp_user:
                        exp_user_id = exp_user.id

                    # Restore original bind
                    if original_bind:
                        db.get_app().config["SQLALCHEMY_BINDS"][
                            "db_exp"
                        ] = original_bind
            except Exception:
                pass  # Use fallback admin ID if query fails

            if exp.platform_type == "microblogging":
                return redirect(f"/{exp.idexp}/feed/{exp_user_id}/feed/rf/1")
            elif exp.platform_type == "forum":
                return redirect(f"/{exp.idexp}/rfeed/{exp_user_id}/rfeed/rf/1")
    return render_template("login/login.html")


@main.get("/profile")
@login_required
def profile():
    """Handle profile operation - legacy route."""
    # Get active experiments
    exps = Exps.query.filter(Exps.status != 0).all()
    if not exps:
        flash("No active experiment. Please activate an experiment first.")
        return redirect("/admin/experiments")

    if len(exps) > 1:
        return redirect("/admin/join_simulation")

    exp = exps[0]
    user_id = current_user.id
    return redirect(f"/{exp.idexp}/profile/{user_id}/rf/1")


@main.get("/<int:exp_id>/profile/<user_id>/<string:mode>/<int:page>")
@login_required
def profile_logged(exp_id, user_id, page=1, mode="recent"):
    """Handle profile logged operation."""
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp:
        flash("Experiment not found", "error")
        return redirect(url_for("main.index"))

    # Get experiment user (not admin user) for logged_id
    logged_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not logged_user:
        if getattr(exp, "platform_type", "") == "forum":
            logged_id = current_user.id
        else:
            flash("User not found in experiment", "error")
            return redirect(url_for("main.index"))
    else:
        logged_id = logged_user.id

    # Handle both int and UUID user_id formats (Standard vs HPC experiments)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass

    user = User_mgmt.query.get(user_id)
    if not user:
        user = User_mgmt.query.filter_by(username=user_id).first()

    # If user still not found, redirect with error message
    if not user:
        flash("User not found in experiment", "error")
        return redirect(url_for("main.index"))

    is_following = (
        _latest_follow_action(follower_id=logged_id, user_id=user.id) == "follow"
    )

    total_posts = Post.query.filter_by(user_id=user_id, comment_to=-1).count()
    total_comments = Post.query.filter(
        Post.user_id == user_id, and_(Post.comment_to.isnot(None), Post.comment_to != -1)
    ).count()
    total_likes = Reactions.query.filter_by(user_id=user_id, type="like").count()
    total_dislikes = Reactions.query.filter_by(user_id=user_id, type="dislike").count()
    total_articles = Post.query.filter(
        Post.user_id == user_id, Post.news_id.isnot(None)
    ).count()

    hashtags = (
        db.session.query(
            Hashtags.id,
            Hashtags.hashtag,
            func.count(Post_hashtags.hashtag_id).label("count"),
        )
        .join(Post_hashtags, Post_hashtags.hashtag_id == Hashtags.id)
        .join(Post, Post.id == Post_hashtags.post_id)
        .filter(Post.user_id == user_id)
        .group_by(Hashtags.id, Hashtags.hashtag)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )
    most_used_hashtags = [(h[0], h[1], h[2]) for h in hashtags]

    emotions = (
        db.session.query(
            Emotions.id,
            Emotions.emotion,
            func.count(Post_emotions.emotion_id).label("count"),
        )
        .join(Post_emotions, Post_emotions.emotion_id == Emotions.id)
        .join(Post, Post.id == Post_emotions.post_id)
        .filter(Post.user_id == user_id)
        .group_by(Emotions.id, Emotions.emotion)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )
    most_used_emotions = [(e[0], e[1], e[2]) for e in emotions]

    total_followers = count_followers(user.id)
    total_followee = count_followees(user.id)

    if getattr(exp, "platform_type", "") == "forum":
        profile_pic = _forum_profile_pic(user)
    else:
        profile_pic = ""
        if user.is_page == 1:
            pg = Page.query.filter_by(name=user.username).first()
            if pg:
                profile_pic = pg.logo
        else:
            ag = Agent.query.filter_by(name=user.username).first()
            if ag and ag.profile_pic:
                profile_pic = ag.profile_pic
            else:
                admin = Admin_users.query.filter_by(username=user.username).first()
                profile_pic = admin.profile_pic if admin else ""

    agent_custom_features = {}
    dashboard_agent = Agent.query.filter_by(name=user.username).first()
    if dashboard_agent is not None:
        try:
            agent_custom_features = (
                summarize_agent_custom_features(dashboard_agent.id).get(
                    "custom_features"
                )
                or {}
            )
        except Exception:
            agent_custom_features = {}

    # Other functions as before
    rp = get_user_recent_posts(user_id, page, 10, mode, logged_id, exp_id)
    mutual_friends = get_mutual_friends(user_id, current_user.id)
    hashtags_top = get_top_user_hashtags(user_id, 5)
    interests = get_user_recent_interests(user_id, 5)
    mentions = get_unanswered_mentions(current_user.id)

    stress_reward_active = _stress_reward_enabled_for_exp(exp)
    stress_reward_indicator = (
        _latest_stress_reward_indicator(user.id)
        if stress_reward_active
        else {
            "stress": {"value": 0.0, "level": 0},
            "reward": {"value": 0.0, "level": 0},
        }
    )
    cover_image = _get_user_cover_image(user.id)

    common_context = dict(
        is_page=user.is_page,
        user={
            "user_data": user,
            "total_posts": total_posts,
            "total_comments": total_comments,
            "total_likes": total_likes,
            "total_dislikes": total_dislikes,
            "total_articles": total_articles,
            "most_used_hashtags": most_used_hashtags,
            "most_used_emotions": most_used_emotions,
            "total_followers": total_followers,
            "total_followee": total_followee,
        },
        enumerate=enumerate,
        username=user.username,
        items=rp,
        len=len,
        mutual=mutual_friends,
        page=page,
        mode=mode,
        user_id=user_id,
        logged_username=current_user.username,
        logged_profile_pic=get_safe_profile_pic(
            current_user.username, getattr(current_user, "is_page", 0)
        ),
        hashtags=hashtags_top,
        str=str,
        logged_id=logged_id,
        is_following=is_following,
        interests=interests,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        exp_id=exp_id,
        agent_custom_features=agent_custom_features,
        stress_reward_active=stress_reward_active,
        stress_reward_indicator=stress_reward_indicator,
        cover_image=cover_image,
    )

    if getattr(exp, "platform_type", "") == "forum":
        forum_logged_user = _forum_logged_user()
        mention_user_id = forum_logged_user.id if forum_logged_user else None
        forum_mentions = (
            get_unanswered_mentions(mention_user_id) if mention_user_id else []
        )
        suggested_users = (
            get_suggested_users(forum_logged_user.username, pages=False)
            if forum_logged_user
            else []
        )
        suggested_pages = (
            get_suggested_users(forum_logged_user.username, pages=True)
            if forum_logged_user
            else []
        )
        forum_context = dict(common_context)
        forum_context["mentions"] = forum_mentions
        return render_template(
            "forum/profile.html",
            profile_pic=_forum_current_profile_pic(exp_id, forum_logged_user),
            viewed_profile_pic=profile_pic,
            profile_pic_feed=_forum_current_profile_pic(exp_id, forum_logged_user),
            profile_delete_inline=True,
            feed_user_id=None,
            timeline="profile",
            sfollow=suggested_users,
            spages=suggested_pages,
            forum_memory_enabled=_forum_memory_enabled(exp_id),
            can_follow_profile=int(user.id) != int(logged_id),
            feed_type="new",
            **forum_context,
        )

    return render_template(
        "microblogging/profile.html",
        profile_pic=profile_pic,
        **common_context,
    )


@main.get("/<int:exp_id>/edit_profile/<user_id>")
@login_required
def edit_profile(exp_id, user_id):
    """Handle edit profile operation."""
    # Handle both int and UUID user_id formats (Standard vs HPC experiments)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass

    user = User_mgmt.query.filter_by(id=user_id).first()

    profile_pic = ""

    # is the agent a page?
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        ag = Agent.query.filter_by(name=user.username).first()
        if ag is not None and ag.profile_pic is not None:
            profile_pic = ag.profile_pic
        else:
            admin_user = Admin_users.query.filter_by(username=user.username).first()
            profile_pic = admin_user.profile_pic if admin_user else ""

    # Get experiment user (not admin user)
    logged_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not logged_user:
        flash("User not found in experiment", "error")
        return redirect(url_for("main.index"))
    logged_id = logged_user.id

    available_profile_pics = []
    try:
        users_img_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "static",
            "assets",
            "img",
            "users",
        )
        available_profile_pics = sorted(
            [
                filename
                for filename in os.listdir(users_img_dir)
                if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
        )
    except Exception:
        available_profile_pics = []
    available_cover_images = [
        os.path.basename(path) for path in available_cover_image_urls()
    ]

    return render_template(
        "microblogging/edit_profile.html",
        user=user,
        profile_pic=profile_pic,
        available_profile_pics=available_profile_pics,
        cover_image=_get_user_cover_image(user.id),
        available_cover_images=available_cover_images,
        is_page=user.is_page,
        enumerate=enumerate,
        username=user.username,
        len=len,
        user_id=user_id,
        logged_username=current_user.username,
        str=str,
        logged_id=logged_id,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.route("/<int:exp_id>/update_profile_data/<user_id>", methods=["POST"])
@login_required
def update_profile_data(exp_id, user_id):
    """Update profile data."""
    # Handle both int and UUID user_id formats (Standard vs HPC experiments)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass

    user = User_mgmt.query.filter_by(id=user_id).first()

    user.email = request.form.get("email")
    user.gender = request.form.get("gender")
    user.nationality = request.form.get("nationality")
    user.language = request.form.get("language")
    user.leaning = request.form.get("leaning")
    user.education_level = request.form.get("education_level")
    user.recsys_type = request.form.get("recsys_type")
    user.frecsys_type = request.form.get("frecsys_type")
    user.age = int(request.form.get("age"))
    profile_pic = request.form.get("profile_pic")
    cover_image = request.form.get("cover_image") or random_cover_image_url()

    if user.is_page == 1:
        page = Page.query.filter_by(name=user.username).first()
        if page is not None:
            page.logo = profile_pic
    else:
        agent = Agent.query.filter_by(name=user.username).first()
        if agent is not None:
            agent.profile_pic = profile_pic

    admin_user = Admin_users.query.filter_by(username=user.username).first()
    if admin_user is not None:
        admin_user.profile_pic = profile_pic

    _set_user_cover_image(user.id, cover_image)

    db.session.commit()

    return redirect(request.referrer)


@main.route("/<int:exp_id>/update_password/<user_id>", methods=["POST"])
@login_required
def update_password(exp_id, user_id):
    """Update password."""
    # Handle both int and UUID user_id formats (Standard vs HPC experiments)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass

    user = User_mgmt.query.filter_by(id=user_id).first()

    npassword = request.form.get("new_password")
    npassword2 = request.form.get("new_password2")

    if npassword != npassword2:
        # return an error message
        flash("The provided passwords do not match.")
        return redirect(request.referrer)

    pwd = generate_password_hash(npassword, method="pbkdf2:sha256")
    user.password = pwd
    db.session.commit()

    return redirect(request.referrer)
