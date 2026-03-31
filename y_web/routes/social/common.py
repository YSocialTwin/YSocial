"""
Common/profile routes for both microblogging and forum platforms.

Routes: index, profile, profile_logged, edit_profile, update_profile_data,
        update_password.
"""

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc
from sqlalchemy.sql.expression import func
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.routes.social._blueprint import main
from y_web.routes.social.helpers import (
    _forum_current_profile_pic,
    _forum_logged_user,
    _forum_memory_enabled,
    _forum_profile_pic,
    is_admin,
)
from y_web.src.data_access import (
    get_mutual_friends,
    get_top_user_hashtags,
    get_unanswered_mentions,
    get_user_recent_interests,
    get_user_recent_posts,
)
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
    User_mgmt,
)
from y_web.src.recsys import get_suggested_users


def _latest_follow_action(*, follower_id, user_id):
    follow_event = (
        Follow.query.filter_by(follower_id=follower_id, user_id=user_id)
        .order_by(Follow.id.desc())
        .first()
    )
    return str(getattr(follow_event, "action", "") or "").strip().lower()


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
        Post.user_id == user_id, Post.comment_to != -1
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

    total_followers = Follow.query.filter(
        Follow.user_id == user_id, Follow.follower_id != user_id
    ).count()
    total_followee = Follow.query.filter(
        Follow.follower_id == user_id, Follow.user_id != user_id
    ).count()

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

    # Other functions as before
    rp = get_user_recent_posts(user_id, page, 10, mode, logged_id, exp_id)
    mutual_friends = get_mutual_friends(user_id, current_user.id)
    hashtags_top = get_top_user_hashtags(user_id, 5)
    interests = get_user_recent_interests(user_id, 5)
    mentions = get_unanswered_mentions(current_user.id)

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
        hashtags=hashtags_top,
        str=str,
        logged_id=logged_id,
        is_following=is_following,
        interests=interests,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        exp_id=exp_id,
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
        profile_pic = (
            ag.profile_pic
            if ag is not None and ag.profile_pic is not None
            else Admin_users.query.filter_by(username=user.username).first().profile_pic
        )

    # Get experiment user (not admin user)
    logged_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not logged_user:
        flash("User not found in experiment", "error")
        return redirect(url_for("main.index"))
    logged_id = logged_user.id

    return render_template(
        "microblogging/edit_profile.html",
        user=user,
        profile_pic=profile_pic,
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

    Admin_users.query.filter_by(username=user.username).first().profile_pic = (
        profile_pic
    )

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
