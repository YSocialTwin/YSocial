"""
Common/profile routes for both microblogging and forum platforms.

Routes: index, profile, profile_logged, edit_profile, update_profile_data,
        update_password.
"""

import json
import math
import os
import uuid as _uuid

from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import and_, desc, func, or_, select, text as _text
from sqlalchemy.sql.expression import func
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.routes.social._blueprint import main
from y_web.routes.social.helpers import (
    _load_ui_settings,
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
    Agent_Opinion,
    Emotions,
    Exp_Topic,
    Exps,
    Follow,
    Hashtags,
    Interests,
    OpinionGroup,
    Page,
    Post,
    Post_emotions,
    Post_hashtags,
    Reactions,
    Rounds,
    StressReward,
    Topic_List,
    User_interest,
    User_mgmt,
)
from y_web.src.recsys import get_suggested_users
from y_web.routes.admin.sub.experiments._frontend_settings import _load_recsys_options
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
    if not exp or getattr(exp, "platform_type", "") not in {
        "forum",
        "microblogging",
        "photo_sharing",
    }:
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
    if not exp or getattr(exp, "platform_type", "") not in {
        "microblogging",
        "forum",
        "photo_sharing",
    }:
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
        user = db.session.scalars(select(User_mgmt).filter_by(id=user_id)).first()
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
    user = db.session.scalars(select(User_mgmt).filter_by(id=user_id)).first()
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
        exps = db.session.scalars(select(Exps).filter(Exps.status != 0)).all()
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
                from y_web.src.models import User_mgmt

                # Temporarily override db_exp bind to query correct database
                original_bind = db.get_app().config["SQLALCHEMY_BINDS"].get("db_exp")
                if bind_key in db.get_app().config["SQLALCHEMY_BINDS"]:
                    db.get_app().config["SQLALCHEMY_BINDS"][
                        "db_exp"
                    ] = db.get_app().config["SQLALCHEMY_BINDS"][bind_key]

                    exp_user = db.session.scalars(
                        select(User_mgmt).filter_by(username=current_user.username)
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
            elif exp.platform_type == "photo_sharing":
                return redirect(f"/{exp.idexp}/photo/feed/all/feed/rf/1")
    return render_template("login/login.html")


@main.get("/profile")
@login_required
def profile():
    """Handle profile operation - legacy route."""
    # Get active experiments
    exps = db.session.scalars(select(Exps).filter(Exps.status != 0)).all()
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
    exp = db.session.scalars(select(Exps).filter_by(idexp=int(exp_id))).first()
    if not exp:
        flash("Experiment not found", "error")
        return redirect(url_for("main.index"))

    # Get experiment user (not admin user) for logged_id
    logged_user = db.session.scalars(
        select(User_mgmt).filter_by(username=current_user.username)
    ).first()
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

    user = db.session.get(User_mgmt, user_id)
    if not user:
        user = db.session.scalars(select(User_mgmt).filter_by(username=user_id)).first()

    # If user still not found, redirect with error message
    if not user:
        flash("User not found in experiment", "error")
        return redirect(url_for("main.index"))

    if getattr(exp, "platform_type", "") == "photo_sharing":
        return redirect(f"/{exp_id}/photo/profile/{user.id}/recent/{page}")

    is_following = (
        _latest_follow_action(follower_id=logged_id, user_id=user.id) == "follow"
    )

    total_posts = Post.query.filter(
        Post.user_id == user_id,
        or_(Post.comment_to.is_(None), Post.comment_to == -1),
    ).count()
    total_comments = Post.query.filter(
        Post.user_id == user_id,
        and_(Post.comment_to.isnot(None), Post.comment_to != -1),
    ).count()
    total_likes = db.session.scalar(
        select(func.count())
        .select_from(Reactions)
        .filter_by(user_id=user_id, type="like")
    )
    total_dislikes = db.session.scalar(
        select(func.count())
        .select_from(Reactions)
        .filter_by(user_id=user_id, type="dislike")
    )
    total_articles = db.session.scalar(
        select(func.count())
        .select_from(Post)
        .filter(Post.user_id == user_id, Post.news_id.isnot(None))
    )

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
            pg = db.session.scalars(select(Page).filter_by(name=user.username)).first()
            if pg:
                profile_pic = pg.logo
        else:
            ag = db.session.scalars(select(Agent).filter_by(name=user.username)).first()
            if ag and ag.profile_pic:
                profile_pic = ag.profile_pic
            else:
                admin = db.session.scalars(
                    select(Admin_users).filter_by(username=user.username)
                ).first()
                profile_pic = admin.profile_pic if admin else ""

    agent_custom_features = {}
    dashboard_agent = db.session.scalars(
        select(Agent).filter_by(name=user.username)
    ).first()
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
        ui=_load_ui_settings(exp_id),
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

    user = db.session.scalars(select(User_mgmt).filter_by(id=user_id)).first()

    profile_pic = ""

    # is the agent a page?
    if user.is_page == 1:
        pg = db.session.scalars(select(Page).filter_by(name=user.username)).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        ag = db.session.scalars(select(Agent).filter_by(name=user.username)).first()
        if ag is not None and ag.profile_pic is not None:
            profile_pic = ag.profile_pic
        else:
            admin_user = db.session.scalars(
                select(Admin_users).filter_by(username=user.username)
            ).first()
            profile_pic = admin_user.profile_pic if admin_user else ""

    # Get experiment user (not admin user)
    logged_user = db.session.scalars(
        select(User_mgmt).filter_by(username=current_user.username)
    ).first()
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

    # ── Topic/opinion data (same logic as onboarding GET) ─────────────────
    def _get_exp_engine_ep():
        try:
            eng = db.engines.get("db_exp")
            if eng:
                return eng
        except Exception:
            pass
        try:
            return db.get_engine(current_app, bind="db_exp")
        except Exception:
            return db.engine

    exp_topic_rows = db.session.scalars(
        select(Exp_Topic).filter_by(exp_id=exp_id)
    ).all()
    topic_ids = [et.topic_id for et in exp_topic_rows]
    topics = []
    if topic_ids:
        topics = db.session.scalars(
            select(Topic_List).filter(Topic_List.id.in_(topic_ids))
        ).all()

    opinion_groups = db.session.scalars(
        select(OpinionGroup).order_by(OpinionGroup.lower_bound)
    ).all()

    saved_interest_idx = {}
    saved_opinions     = {}
    INTEREST_STEPS     = [0.0, 0.33, 0.67, 1.0]

    try:
        user_id_str = str(user_id)
        exp_engine  = _get_exp_engine_ep()

        # Build mapping: sim iid → dashboard topic_id
        sim_to_dash = {}
        for et in exp_topic_rows:
            tl = db.session.scalars(select(Topic_List).filter_by(id=et.topic_id)).first()
            if tl:
                sim_int = db.session.scalars(select(Interests).filter_by(interest=tl.name)).first()
                if sim_int:
                    sim_to_dash[str(sim_int.iid)] = str(et.topic_id)

        with exp_engine.connect() as conn:
            # Interest levels
            rows = conn.execute(
                _text("SELECT topic_id, interest_level FROM user_topic_interest WHERE user_id = :uid"),
                {"uid": user_id_str},
            ).fetchall()
            for row in rows:
                dash_id = sim_to_dash.get(str(row[0]))
                if dash_id:
                    best = min(range(len(INTEREST_STEPS)), key=lambda i: abs(INTEREST_STEPS[i] - float(row[1])))
                    saved_interest_idx[dash_id] = best

            # Opinions
            op_rows = []
            for tid_sentinel in ("'0'", "0"):
                try:
                    op_rows = conn.execute(
                        _text(f"SELECT topic_id, opinion FROM agent_opinion WHERE agent_id = :aid AND tid = {tid_sentinel}"),
                        {"aid": user_id_str},
                    ).fetchall()
                    if op_rows:
                        break
                except Exception:
                    pass

            og_mids = [(og.lower_bound + og.upper_bound) / 2.0 for og in opinion_groups]
            for row in op_rows:
                dash_id = sim_to_dash.get(str(row[0]))
                if dash_id:
                    try:
                        best = min(range(len(og_mids)), key=lambda i: abs(og_mids[i] - float(row[1])))
                        saved_opinions[dash_id] = best
                    except Exception:
                        pass
    except Exception:
        pass

    # Recsys options filtered by simulator_type for this experiment
    _exp = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
    _sim_type = (_exp.simulator_type or "Standard") if _exp else "Standard"
    _recsys_opts = _load_recsys_options(_sim_type)
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
        topics=topics,
        opinion_groups=opinion_groups,
        saved_interest_idx=saved_interest_idx,
        saved_opinions=saved_opinions,
        exp_id=exp_id,
        recsys_options=_recsys_opts,
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

    user = db.session.scalars(select(User_mgmt).filter_by(id=user_id)).first()

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
        page = db.session.scalars(select(Page).filter_by(name=user.username)).first()
        if page is not None:
            page.logo = profile_pic
    else:
        agent = db.session.scalars(select(Agent).filter_by(name=user.username)).first()
        if agent is not None:
            agent.profile_pic = profile_pic

    admin_user = db.session.scalars(
        select(Admin_users).filter_by(username=user.username)
    ).first()
    if admin_user is not None:
        admin_user.profile_pic = profile_pic

    _set_user_cover_image(user.id, cover_image)

    db.session.commit()

    if (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
        or request.is_json
    ):
        return jsonify(
            {
                "ok": True,
                "user_id": str(user.id),
                "username": user.username,
                "email": user.email or "",
                "profile_pic": profile_pic or "",
                "cover_image": cover_image or "",
                "gender": user.gender or "",
                "nationality": user.nationality or "",
                "language": user.language or "",
                "leaning": user.leaning or "",
                "education_level": user.education_level or "",
                "age": user.age or 0,
            }
        )

    return redirect(request.referrer)


@main.route("/<int:exp_id>/update_topic_preferences/<user_id>", methods=["POST"])
@login_required
def update_topic_preferences(exp_id, user_id):
    """Save per-topic interest level and opinion from the edit_profile form."""

    def _get_exp_engine_tp():
        try:
            eng = db.engines.get("db_exp")
            if eng:
                return eng
        except Exception:
            pass
        try:
            return db.get_engine(current_app, bind="db_exp")
        except Exception:
            return db.engine

    def _agent_opinion_needs_explicit_id_tp(engine):
        try:
            with engine.connect() as conn:
                rows = conn.execute(_text("PRAGMA table_info(agent_opinion)")).fetchall()
            for row in rows:
                if row[1] == "id":
                    return "INT" not in (row[2] or "").upper()
        except Exception:
            pass
        return False

    def _ensure_user_topic_interest_table_tp(engine):
        ddl = """CREATE TABLE IF NOT EXISTS user_topic_interest (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT    NOT NULL,
            topic_id       TEXT    NOT NULL,
            interest_level REAL    NOT NULL DEFAULT 0.0,
            UNIQUE(user_id, topic_id)
        )"""
        try:
            with engine.connect() as conn:
                conn.execute(_text(ddl))
                conn.commit()
        except Exception:
            pass

    try:
        user_id_val = int(user_id)
    except (ValueError, TypeError):
        user_id_val = user_id
    user_id_str = str(user_id_val)

    # Resolve opinion group midpoints
    opinion_groups = db.session.scalars(
        select(OpinionGroup).order_by(OpinionGroup.lower_bound)
    ).all()
    group_midpoints = {og.id: (og.lower_bound + og.upper_bound) / 2.0 for og in opinion_groups}

    # Build dashboard topic_id → sim iid mapping
    exp_topic_rows = db.session.scalars(select(Exp_Topic).filter_by(exp_id=exp_id)).all()
    topic_map = {}
    for et in exp_topic_rows:
        tl = db.session.scalars(select(Topic_List).filter_by(id=et.topic_id)).first()
        if not tl:
            continue
        sim_interest = db.session.scalars(select(Interests).filter_by(interest=tl.name)).first()
        if sim_interest is None:
            sim_interest = Interests(interest=tl.name)
            db.session.add(sim_interest)
            db.session.flush()
        topic_map[et.topic_id] = sim_interest.iid
    db.session.commit()

    exp_engine = _get_exp_engine_tp()
    uuid_mode  = _agent_opinion_needs_explicit_id_tp(exp_engine)
    _ensure_user_topic_interest_table_tp(exp_engine)

    with exp_engine.connect() as conn:
        try:
            conn.execute(_text("DELETE FROM user_topic_interest WHERE user_id = :uid"), {"uid": user_id_str})
            if uuid_mode:
                conn.execute(_text("DELETE FROM agent_opinion WHERE agent_id = :aid AND tid = '0'"), {"aid": user_id_str})
            else:
                conn.execute(_text("DELETE FROM agent_opinion WHERE agent_id = :aid AND tid = 0 AND id_interacted_with IN (0, -1)"), {"aid": user_id_val})
        except Exception:
            pass

        for topic_id_dash, sim_topic_id in topic_map.items():
            interest_str = request.form.get(f"interest_{topic_id_dash}")
            opinion_str  = request.form.get(f"opinion_{topic_id_dash}")

            if interest_str is not None:
                try:
                    interest_val = max(0.0, min(1.0, float(interest_str)))
                except (ValueError, TypeError):
                    interest_val = 0.0
                conn.execute(
                    _text("INSERT OR REPLACE INTO user_topic_interest (user_id, topic_id, interest_level) VALUES (:uid, :tid, :lvl)"),
                    {"uid": user_id_str, "tid": str(sim_topic_id), "lvl": interest_val},
                )

            if opinion_str is not None:
                try:
                    og_id       = int(opinion_str)
                    opinion_val = group_midpoints.get(og_id, 0.5)
                except (ValueError, TypeError):
                    opinion_val = 0.5
                if uuid_mode:
                    conn.execute(
                        _text("INSERT INTO agent_opinion (id, agent_id, tid, topic_id, id_interacted_with, id_post, opinion, stubborn) VALUES (:id, :aid, '0', :tid, NULL, NULL, :op, 0)"),
                        {"id": str(_uuid.uuid4()), "aid": user_id_str, "tid": str(sim_topic_id), "op": opinion_val},
                    )
                else:
                    conn.execute(
                        _text("INSERT INTO agent_opinion (agent_id, tid, topic_id, id_interacted_with, id_post, opinion, stubborn) VALUES (:aid, 0, :tid, 0, 0, :op, 0)"),
                        {"aid": user_id_val, "tid": sim_topic_id, "op": opinion_val},
                    )
        conn.commit()

    return redirect(url_for("main.edit_profile", exp_id=exp_id, user_id=user_id_val))


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

    user = db.session.scalars(select(User_mgmt).filter_by(id=user_id)).first()

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


# ─────────────────────────────────────────────
#  ONBOARDING ROUTES
# ─────────────────────────────────────────────

@main.get("/<int:exp_id>/onboarding/<user_id>")
@login_required
def onboarding(exp_id, user_id):
    """
    Landing page shown to a regular user immediately after selecting an experiment.

    Displays a combined profile-setup and topic-preference form.  The user can:
      - Customise their profile (all fields from Edit Profile, security excluded).
      - Rate their *interest level* and *opinion* for each active topic using the
        Likert scale stored in dashboard.db → opinion_groups.

    On submission the form POSTs to save_onboarding.
    """
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        pass

    user = db.session.scalars(select(User_mgmt).filter_by(id=user_id)).first()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("auth.login"))

    # ── Skip onboarding if already completed ──────────────────────────────
    def _already_onboarded(uid):
        try:
            eng = None
            try:
                eng = db.engines.get("db_exp")
            except Exception:
                pass
            if eng is None:
                try:
                    eng = db.get_engine(current_app, bind="db_exp")
                except Exception:
                    eng = db.engine
            with eng.connect() as conn:
                row = conn.execute(
                    _text("SELECT 1 FROM user_topic_interest WHERE user_id = :uid LIMIT 1"),
                    {"uid": str(uid)},
                ).fetchone()
                return row is not None
        except Exception:
            return False

    if _already_onboarded(user_id):
        exp_obj = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
        if exp_obj is not None:
            if exp_obj.platform_type == "microblogging":
                return redirect(f"/{exp_id}/feed/{user_id}/feed/rf/1")
            elif exp_obj.platform_type == "forum":
                return redirect(f"/{exp_id}/rfeed/{user_id}/rfeed/rf/1")
            elif exp_obj.platform_type == "photo_sharing":
                return redirect(f"/{exp_id}/photo/feed/all/feed/rf/1")

    # Profile picture
    profile_pic = ""
    if getattr(user, "is_page", 0) == 1:
        pg = db.session.scalars(select(Page).filter_by(name=user.username)).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        ag = db.session.scalars(select(Agent).filter_by(name=user.username)).first()
        if ag is not None and ag.profile_pic:
            profile_pic = ag.profile_pic
        else:
            admin_user = db.session.scalars(
                select(Admin_users).filter_by(username=user.username)
            ).first()
            profile_pic = admin_user.profile_pic if admin_user else ""

    # Available images
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
            f
            for f in os.listdir(users_img_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        )
    except Exception:
        available_profile_pics = []

    available_cover_images = [
        os.path.basename(p) for p in available_cover_image_urls()
    ]

    # Topics assigned to this experiment (dashboard DB)
    exp_topic_rows = db.session.scalars(
        select(Exp_Topic).filter_by(exp_id=exp_id)
    ).all()
    topic_ids = [et.topic_id for et in exp_topic_rows]
    topics = []
    if topic_ids:
        topics = db.session.scalars(
            select(Topic_List).filter(Topic_List.id.in_(topic_ids))
        ).all()

    # Likert scale: opinion groups ordered from most negative to most positive
    opinion_groups = db.session.scalars(
        select(OpinionGroup).order_by(OpinionGroup.lower_bound)
    ).all()

    cover_image = _get_user_cover_image(user.id)

    # ── Pre-populate saved interest / opinion values ───────────────────────
    def _get_exp_engine_get():
        try:
            eng = db.engines.get("db_exp")
            if eng:
                return eng
        except Exception:
            pass
        try:
            return db.get_engine(current_app, bind="db_exp")
        except Exception:
            return db.engine

    user_id_str = str(user_id)
    saved_interests = {}   # dashboard topic_id (str) → float 0-1
    saved_opinions  = {}   # dashboard topic_id (str) → opinion group index (int)

    try:
        exp_engine = _get_exp_engine_get()

        # Build mapping: sim topic_id → dashboard topic_id
        sim_to_dash = {}
        for et in db.session.scalars(select(Exp_Topic).filter_by(exp_id=exp_id)).all():
            tl = db.session.scalars(select(Topic_List).filter_by(id=et.topic_id)).first()
            if tl:
                sim_int = db.session.scalars(select(Interests).filter_by(interest=tl.name)).first()
                if sim_int:
                    sim_to_dash[str(sim_int.iid)] = str(et.topic_id)

        with exp_engine.connect() as conn:
            # Interest levels
            rows = conn.execute(
                _text("SELECT topic_id, interest_level FROM user_topic_interest WHERE user_id = :uid"),
                {"uid": user_id_str},
            ).fetchall()
            for row in rows:
                dash_id = sim_to_dash.get(str(row[0]))
                if dash_id is not None:
                    saved_interests[dash_id] = float(row[1])

            # Opinions — try tid='0' (UUID mode) then tid=0 (integer mode)
            # Columns: topic_id (sim iid), opinion (float)
            op_rows = []
            try:
                op_rows = conn.execute(
                    _text("SELECT topic_id, opinion FROM agent_opinion WHERE agent_id = :aid AND tid = '0'"),
                    {"aid": user_id_str},
                ).fetchall()
            except Exception:
                pass
            if not op_rows:
                try:
                    op_rows = conn.execute(
                        _text("SELECT topic_id, opinion FROM agent_opinion WHERE agent_id = :aid AND tid = 0"),
                        {"aid": user_id_str},
                    ).fetchall()
                except Exception:
                    pass

            # Map opinion float → closest opinion group index
            og_list = opinion_groups  # already ordered by lower_bound
            og_mids = [(og.lower_bound + og.upper_bound) / 2.0 for og in og_list]
            for row in op_rows:
                sim_tid = str(row[0])          # topic_id column = sim iid
                dash_id = sim_to_dash.get(sim_tid)
                if dash_id is None:
                    continue
                try:
                    op_val = float(row[1])     # opinion column
                except Exception:
                    continue
                # find closest index
                best_idx = min(range(len(og_mids)), key=lambda i: abs(og_mids[i] - op_val))
                saved_opinions[dash_id] = best_idx
    except Exception:
        pass

    # Convert interest float → slider step index (0-3)
    # 0.0→0, 0.33→1, 0.67→2, 1.0→3
    INTEREST_STEPS = [0.0, 0.33, 0.67, 1.0]
    saved_interest_idx = {}
    for tid, val in saved_interests.items():
        best = min(range(len(INTEREST_STEPS)), key=lambda i: abs(INTEREST_STEPS[i] - val))
        saved_interest_idx[tid] = best

    return render_template(
        "login/onboarding.html",
        user=user,
        profile_pic=profile_pic,
        available_profile_pics=available_profile_pics,
        cover_image=cover_image,
        available_cover_images=available_cover_images,
        topics=topics,
        opinion_groups=opinion_groups,
        exp_id=exp_id,
        user_id=user_id,
        is_page=getattr(user, "is_page", 0),
        saved_interest_idx=saved_interest_idx,
        saved_opinions=saved_opinions,
        str=str,
        enumerate=enumerate,
        len=len,
        bool=bool,
    )



@main.route("/<int:exp_id>/save_onboarding/<user_id>", methods=["POST"])
@login_required
def save_onboarding(exp_id, user_id):
    """
    Persist onboarding form data and redirect the user to their feed.

    Saves:
      1. Profile fields (gender, age, education_level, profile_pic, cover_image).
      2. Per-topic interest level → user_topic_interest table (created if absent).
      3. Per-topic opinion       → agent_opinion via raw SQL (handles both
         integer-autoincrement and UUID primary key schemas).
    """

    # ── helpers ────────────────────────────────────────────────────────────
    def _get_exp_engine():
        """Return the db_exp SQLAlchemy engine (Flask-SQLAlchemy 2.x / 3.x)."""
        try:
            eng = db.engines.get("db_exp")
            if eng:
                return eng
        except Exception:
            pass
        try:
            return db.get_engine(current_app, bind="db_exp")
        except Exception:
            return db.engine

    def _agent_opinion_needs_explicit_id(engine):
        """True when agent_opinion.id is TEXT/VARCHAR (UUID schema, not autoincrement)."""
        try:
            with engine.connect() as conn:
                rows = conn.execute(_text("PRAGMA table_info(agent_opinion)")).fetchall()
            for row in rows:
                if row[1] == "id":
                    return "INT" not in (row[2] or "").upper()
        except Exception:
            pass
        return False

    def _ensure_user_topic_interest_table(engine):
        ddl = """
        CREATE TABLE IF NOT EXISTS user_topic_interest (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        TEXT    NOT NULL,
            topic_id       TEXT    NOT NULL,
            interest_level REAL    NOT NULL DEFAULT 0.0,
            UNIQUE(user_id, topic_id)
        )"""
        try:
            with engine.connect() as conn:
                conn.execute(_text(ddl))
                conn.commit()
        except Exception:
            pass

    # ── coerce user_id ─────────────────────────────────────────────────────
    try:
        user_id_val = int(user_id)
    except (ValueError, TypeError):
        user_id_val = user_id
    user_id_str = str(user_id_val)

    # ── 0. Load user ───────────────────────────────────────────────────────
    user = db.session.scalars(select(User_mgmt).filter_by(id=user_id_val)).first()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("auth.login"))

    # ── 1. Save profile fields ─────────────────────────────────────────────
    user.gender          = request.form.get("gender")          or user.gender
    user.education_level = request.form.get("education_level") or user.education_level
    try:
        age_val = request.form.get("age")
        if age_val:
            user.age = int(age_val)
    except (ValueError, TypeError):
        pass

    profile_pic  = request.form.get("profile_pic")
    cover_image  = request.form.get("cover_image") or random_cover_image_url()

    if getattr(user, "is_page", 0) == 1:
        page = db.session.scalars(select(Page).filter_by(name=user.username)).first()
        if page is not None:
            page.logo = profile_pic
    else:
        agent = db.session.scalars(select(Agent).filter_by(name=user.username)).first()
        if agent is not None:
            agent.profile_pic = profile_pic

    admin_user = db.session.scalars(
        select(Admin_users).filter_by(username=user.username)
    ).first()
    if admin_user is not None:
        admin_user.profile_pic = profile_pic

    _set_user_cover_image(user.id, cover_image)

    # ── 2. Resolve experiment topics + opinion groups ──────────────────────
    opinion_groups = db.session.scalars(
        select(OpinionGroup).order_by(OpinionGroup.lower_bound)
    ).all()
    group_midpoints = {og.id: (og.lower_bound + og.upper_bound) / 2.0 for og in opinion_groups}

    exp_topic_rows = db.session.scalars(
        select(Exp_Topic).filter_by(exp_id=exp_id)
    ).all()

    # Build mapping: dashboard topic_id → (sim_topic_id / interests.iid)
    topic_map = {}
    for et in exp_topic_rows:
        tl = db.session.scalars(select(Topic_List).filter_by(id=et.topic_id)).first()
        if not tl:
            continue
        sim_interest = db.session.scalars(
            select(Interests).filter_by(interest=tl.name)
        ).first()
        if sim_interest is None:
            sim_interest = Interests(interest=tl.name)
            db.session.add(sim_interest)
            db.session.flush()
        topic_map[et.topic_id] = sim_interest.iid

    # Commit profile updates + any new Interests rows
    db.session.commit()

    # ── 3. Raw SQL: interest levels + opinions ─────────────────────────────
    exp_engine = _get_exp_engine()
    uuid_mode  = _agent_opinion_needs_explicit_id(exp_engine)
    _ensure_user_topic_interest_table(exp_engine)

    with exp_engine.connect() as conn:

        # Remove existing onboarding entries for idempotency
        try:
            conn.execute(
                _text("DELETE FROM user_topic_interest WHERE user_id = :uid"),
                {"uid": user_id_str},
            )
            if uuid_mode:
                conn.execute(
                    _text("DELETE FROM agent_opinion "
                          "WHERE agent_id = :aid AND tid = '0'"),
                    {"aid": user_id_str},
                )
            else:
                conn.execute(
                    _text("DELETE FROM agent_opinion "
                          "WHERE agent_id = :aid AND tid = 0 "
                          "AND id_interacted_with IN (0, -1)"),
                    {"aid": user_id_val},
                )
        except Exception:
            pass

        for topic_id_dash, sim_topic_id in topic_map.items():
            interest_str = request.form.get(f"interest_{topic_id_dash}")
            opinion_str  = request.form.get(f"opinion_{topic_id_dash}")

            # Interest level → user_topic_interest
            if interest_str is not None:
                try:
                    interest_val = max(0.0, min(1.0, float(interest_str)))
                except (ValueError, TypeError):
                    interest_val = 0.0
                conn.execute(
                    _text("INSERT OR REPLACE INTO user_topic_interest "
                          "(user_id, topic_id, interest_level) "
                          "VALUES (:uid, :tid, :lvl)"),
                    {"uid": user_id_str, "tid": str(sim_topic_id), "lvl": interest_val},
                )

            # Opinion → agent_opinion
            if opinion_str is not None:
                try:
                    og_id       = int(opinion_str)
                    opinion_val = group_midpoints.get(og_id, 0.5)
                except (ValueError, TypeError):
                    opinion_val = 0.5

                if uuid_mode:
                    conn.execute(
                        _text("INSERT INTO agent_opinion "
                              "(id, agent_id, tid, topic_id, "
                              " id_interacted_with, id_post, opinion, stubborn) "
                              "VALUES (:id, :aid, '0', :tid, NULL, NULL, :op, 0)"),
                        {
                            "id":  str(_uuid.uuid4()),
                            "aid": user_id_str,
                            "tid": str(sim_topic_id),
                            "op":  opinion_val,
                        },
                    )
                else:
                    conn.execute(
                        _text("INSERT INTO agent_opinion "
                              "(agent_id, tid, topic_id, "
                              " id_interacted_with, id_post, opinion, stubborn) "
                              "VALUES (:aid, 0, :tid, 0, 0, :op, 0)"),
                        {
                            "aid": user_id_val,
                            "tid": sim_topic_id,
                            "op":  opinion_val,
                        },
                    )

        conn.commit()

    # ── 4. Redirect to feed ────────────────────────────────────────────────
    exp = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
    if exp is None:
        return redirect("/")

    if exp.platform_type == "microblogging":
        return redirect(f"/{exp.idexp}/feed/{user_id_val}/feed/rf/1")
    elif exp.platform_type == "forum":
        return redirect(f"/{exp.idexp}/rfeed/{user_id_val}/rfeed/rf/1")
    elif exp.platform_type == "photo_sharing":
        return redirect(f"/{exp.idexp}/photo/feed/all/feed/rf/1")
    else:
        return redirect("/")
