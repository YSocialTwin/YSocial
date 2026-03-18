"""
Main application routes and views.

Handles the primary user-facing routes including the home feed, user profiles,
hashtag pages, post details, and search functionality for the social media platform.
"""

from urllib.parse import urlencode

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.reddit.service import fetch_feed_page
from y_web.recsys_support import get_suggested_posts, get_suggested_users

from .data_access import *
from .models import Admin_users, Exps, Images, Page, ReplyInboxState

main = Blueprint("main", __name__)


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
            from y_web.experiment_context import get_db_bind_key_for_exp

            bind_key = get_db_bind_key_for_exp(exp.idexp)

            # Query User_mgmt from experiment database
            exp_user_id = current_user.id  # fallback to admin ID
            try:
                # Use the experiment's database bind
                from y_web import db
                from y_web.models import User_mgmt

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
    return render_template("login.html")


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
    # Get experiment user (not admin user) for logged_id
    logged_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not logged_user:
        flash("User not found in experiment", "error")
        return redirect(url_for("main.index"))
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
        Follow.query.filter_by(follower_id=current_user.id, user_id=user_id).count() > 0
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

    # Profile pic logic
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
    rp = get_user_recent_posts(user_id, page, 10, mode, current_user.id, exp_id)
    mutual_friends = get_mutual_friends(user_id, current_user.id)
    hashtags_top = get_top_user_hashtags(user_id, 5)
    interests = get_user_recent_interests(user_id, 5)
    mentions = get_unanswered_mentions(current_user.id)

    return render_template(
        "profile.html",
        profile_pic=profile_pic,
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
        "edit_profile.html",
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


@main.get("/feed")
@login_required
def feeed_logged():
    """
    Display main feed for logged-in users (microblogging platform).
    Legacy route - redirects to experiment selection or first active experiment.

    Returns:
        Redirect to feed with experiment ID and user ID
    """
    # Get active experiments
    exps = Exps.query.filter(Exps.status != 0).all()
    if not exps:
        flash("No active experiment. Please activate an experiment first.")
        return redirect("/admin/experiments")

    if len(exps) > 1:
        return redirect("/admin/join_simulation")

    exp = exps[0]

    # Get experiment user ID (not admin user ID)
    # Temporarily bind to experiment database to query user
    from y_web.experiment_context import get_db_bind_key_for_exp

    bind_key = get_db_bind_key_for_exp(exp.idexp)

    # Query User_mgmt from experiment database
    user_id = current_user.id  # fallback to admin ID
    try:
        # Use the experiment's database bind
        from y_web import db
        from y_web.models import User_mgmt

        # Temporarily override db_exp bind to query correct database
        original_bind = db.get_app().config["SQLALCHEMY_BINDS"].get("db_exp")
        if bind_key in db.get_app().config["SQLALCHEMY_BINDS"]:
            db.get_app().config["SQLALCHEMY_BINDS"]["db_exp"] = db.get_app().config[
                "SQLALCHEMY_BINDS"
            ][bind_key]

            exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
            if exp_user:
                user_id = exp_user.id

            # Restore original bind
            if original_bind:
                db.get_app().config["SQLALCHEMY_BINDS"]["db_exp"] = original_bind
    except Exception:
        pass  # Use fallback admin ID if query fails

    return redirect(f"/{exp.idexp}/feed/{user_id}/feed/rf/1")


@main.get(
    "/<int:exp_id>/feed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>"
)
@login_required
def feed(exp_id, user_id="all", timeline="timeline", mode="rf", page=1):
    """Handle feed operation."""
    if page < 1:
        page = 1

    max_post_per_page = 10
    username = ""
    posts, additional = None, None

    if user_id == "all":
        posts, additional = get_suggested_posts("all", "", page, max_post_per_page)

    elif user_id != "all":
        user = User_mgmt.query.filter_by(id=user_id).first()
        if not user:
            # Try to find user by username instead of ID
            user = User_mgmt.query.filter_by(username=current_user.username).first()
            if not user:
                flash(
                    "User not found in experiment. Please contact administrator.",
                    "error",
                )
                return redirect(f"/admin/experiments")
        recsys = user.recsys_type

        posts, additional = get_suggested_posts(
            user_id, recsys, page, max_post_per_page
        )
        username = user.username

    res, res_additional = [], []

    # Get experiment user ID for reactions
    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    exp_user_id = exp_user.id if exp_user else current_user.id

    if posts is not None:
        res = __get_discussions(posts, username, page, exp_id, exp_user_id)
    if additional is not None:
        res_additional = __get_discussions(
            additional, username, page, exp_id, exp_user_id
        )

    # combine the posts and additional posts
    if len(res_additional) > 0:
        for add in res_additional:
            res.append(add)

    # not enough posts to display
    if len(res) == 0 and page > 1:
        return redirect(f"/feed/{user_id}/{timeline}/{mode}/{page - 1}")

    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.username)
    sfollow = get_suggested_users(current_user.username, pages=False)
    spages = get_suggested_users(current_user.username, pages=True)

    try:
        ag = Agent.query.filter_by(name=current_user.username).first()
        profile_pic = (
            ag.profile_pic
            if ag is not None and ag.profile_pic is not None
            else Admin_users.query.filter_by(username=current_user.username)
            .first()
            .profile_pic
        )
    except:
        profile_pic = ""

    user = User_mgmt.query.filter_by(username=current_user.username).first()
    profile_pic_feed = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic_feed = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic_feed = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=user.username)
                .first()
                .profile_pic
            )
        except:
            profile_pic_feed = ""

    # Get experiment user (not admin user)
    logged_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not logged_user:
        flash("User not found in experiment", "error")
        return redirect(url_for("main.index"))
    logged_id = logged_user.id

    return render_template(
        "feed.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        profile_pic_feed=profile_pic_feed,
        user_id=user_id,
        timeline=timeline,
        username=username,
        mode=mode,
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        logged_id=logged_id,
        trending_ht=trending_ht,
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        sfollow=sfollow,
        spages=spages,
    )


@main.get("/<int:exp_id>/hashtag_posts/<hashtag_id>/<int:page>")
@login_required
def get_post_hashtags(exp_id, hashtag_id, page=1):
    """
    Display posts containing a specific hashtag.

    Args:
        hashtag_id: ID of hashtag to filter posts by
        page: Page number for pagination (default: 1)

    Returns:
        Rendered template with hashtag posts
    """
    # Handle both int and UUID hashtag_id formats (Standard vs HPC experiments)
    try:
        hashtag_id = int(hashtag_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass
    res = get_posts_associated_to_hashtags(
        hashtag_id, page, per_page=10, current_user=current_user.id, exp_id=exp_id
    )

    if len(res) == 0:
        return redirect(f"/{exp_id}/hashtag_posts/{hashtag_id}/{page - 1}")

    # get hashtag name
    hashtag = Hashtags.query.filter_by(id=hashtag_id).first().hashtag

    trending_ht = get_trending_hashtags()

    # get user profile pic
    user = User_mgmt.query.filter_by(username=current_user.username).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=user.username)
                .first()
                .profile_pic
            )
        except:
            profile_pic = ""

    logged_id = user.id

    return render_template(
        "hashtag.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=logged_id,
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_ht,
        logged_id=logged_id,
        hashtag_id=hashtag_id,
        current_hashtag=hashtag,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/<int:exp_id>/interest/<interest_id>/<int:page>")
@login_required
def get_post_interest(exp_id, interest_id, page=1):
    """
    Display posts associated with a specific interest/topic.

    Args:
        interest_id: ID of interest/topic to filter posts by
        page: Page number for pagination (default: 1)

    Returns:
        Rendered template with interest-related posts
    """
    # Handle both int and UUID interest_id formats (Standard vs HPC experiments)
    try:
        interest_id = int(interest_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass
    res = get_posts_associated_to_interest(
        interest_id, page, per_page=10, current_user=current_user.id, exp_id=exp_id
    )

    if len(res) == 0:
        return redirect(f"/{exp_id}/interest/{interest_id}/{page - 1}")

    # get topic name
    interest = Interests.query.filter_by(iid=interest_id).first().interest

    trending_tp = get_trending_topics()

    # get user profile pic
    user = User_mgmt.query.filter_by(username=current_user.username).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=user.username)
                .first()
                .profile_pic
            )
        except:
            profile_pic = ""

    logged_id = user.id

    return render_template(
        "interest.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=logged_id,
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_tp,
        logged_id=logged_id,
        interest_id=interest_id,
        current_interest=interest,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/<int:exp_id>/emotion/<emotion_id>/<int:page>")
@login_required
def get_post_emotion(exp_id, emotion_id, page=1):
    """
    Display posts that elicit a specific emotion.

    Args:
        emotion_id: ID of emotion to filter posts by
        page: Page number for pagination (default: 1)

    Returns:
        Rendered template with emotion-tagged posts
    """
    # Handle both int and UUID emotion_id formats (Standard vs HPC experiments)
    try:
        emotion_id = int(emotion_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass
    res = get_posts_associated_to_emotion(
        emotion_id, page, per_page=10, current_user=current_user.id, exp_id=exp_id
    )

    if len(res) == 0:
        return redirect(f"/{exp_id}/emotion/{emotion_id}/{page - 1}")

    # get emotion name
    emotion = Emotions.query.filter_by(id=emotion_id).first()
    emotion = (emotion_id, emotion.emotion, emotion.icon)

    trending_tp = get_trending_emotions()

    # get user profile pic
    user = User_mgmt.query.filter_by(username=current_user.username).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=user.username)
                .first()
                .profile_pic
            )
        except:
            profile_pic = ""

    logged_id = user.id

    return render_template(
        "emotions.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=logged_id,
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_tp,
        logged_id=logged_id,
        emotion_id=emotion_id,
        current_emotion=emotion,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/<int:exp_id>/friends/<user_id>/<int:page>")
@login_required
def get_friends(exp_id, user_id, page=1):
    """
    Display user's followers and followees (friends).

    Args:
        user_id: ID of user whose friends to display
        page: Page number for pagination (default: 1)

    Returns:
        Rendered template showing followers and followees
    """
    # Handle both int and UUID user_id formats (Standard vs HPC experiments)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass
    followers, followees, number_followers, number_followees = get_user_friends(
        user_id, limit=12, page=page
    )
    mentions = get_unanswered_mentions(current_user.id)

    cu = User_mgmt.query.filter_by(username=current_user.username).first()

    profile_pic_follower = {}

    for f in followers:
        u = User_mgmt.query.filter_by(id=f["id"]).first()

        if u.is_page == 1:
            pg = Page.query.filter_by(name=f["username"]).first()
            if pg is not None:
                profile_pic_follower[f["id"]] = pg.logo
        else:
            try:
                ag = Agent.query.filter_by(name=f["username"]).first()
                profile_pic_follower[f["id"]] = (
                    ag.profile_pic
                    if ag is not None and ag.profile_pic is not None
                    else ""
                )
            except:
                profile_pic_follower[f["id"]] = ""

    profile_pic_followee = {}

    for f in followees:
        u = User_mgmt.query.filter_by(id=f["id"]).first()

        if u.is_page == 1:
            pg = Page.query.filter_by(name=f["username"]).first()
            if pg is not None:
                profile_pic_followee[f["id"]] = pg.logo
        else:
            try:
                ag = Agent.query.filter_by(name=f["username"]).first()
                profile_pic_followee[f["id"]] = (
                    ag.profile_pic
                    if ag is not None and ag.profile_pic is not None
                    else ""
                )
            except:
                profile_pic_followee[f["id"]] = ""

    us = Admin_users.query.filter_by(username=cu.username).first()
    profile_pic = (
        us.profile_pic if us is not None and us.profile_pic is not None else ""
    )

    logged_id = cu.id

    return render_template(
        "friends.html",
        followers=followers,
        profile_pic=profile_pic,
        profile_pic_follower=profile_pic_follower,
        followees=followees,
        profile_pic_followee=profile_pic_followee,
        page=page,
        username=cu.username,
        enumerate=enumerate,
        len=len,
        logged_username=cu.username,
        logged_id=logged_id,
        user_id=user_id,
        number_followers=number_followers,
        number_followees=number_followees,
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


@main.get("/<int:exp_id>/thread/<post_id>")
@login_required
def get_thread(exp_id, post_id):
    # get thread_id for post_id
    """Get thread."""
    # Handle both int and UUID post_id formats (Standard vs HPC experiments)
    try:
        post_id = int(post_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass

    # Get experiment user (not admin user)
    logged_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not logged_user:
        flash("User not found in experiment", "error")
        return redirect(url_for("main.index"))
    exp_user_id = logged_user.id

    # Get the root post first
    root_post = Post.query.filter_by(id=post_id).first()
    if not root_post:
        flash("Post not found", "error")
        return redirect(url_for("main.index"))

    # Get all comments with this thread_id
    comment_posts = (
        Post.query.filter_by(thread_id=post_id).order_by(Post.id.asc()).all()
    )

    # Combine root post and comments
    posts = [root_post] + comment_posts

    print(posts)

    root = posts[0].id

    c = Rounds.query.filter_by(id=posts[0].round).first()
    if c is None:
        day = "None"
        hour = "00"
    else:
        day = c.day
        hour = c.hour

    image = Images.query.filter_by(id=posts[0].image_id).first()

    user = User_mgmt.query.filter_by(id=posts[0].user_id).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=user.username)
                .first()
                .profile_pic
            )
        except:
            profile_pic = ""

    # Get shared post info safely - handle both int and UUID shared_from
    if posts[0].shared_from == -1:
        shared_from_info = -1
    else:
        shared_user = (
            db.session.query(User_mgmt)
            .join(Post, User_mgmt.id == Post.user_id)
            .filter(Post.id == posts[0].shared_from)
            .first()
        )
        shared_from_info = (
            (posts[0].shared_from, shared_user.username)
            if shared_user
            else (posts[0].shared_from, "Unknown")
        )

    discussion_tree = {
        "post": augment_text(posts[0].tweet, exp_id),
        "profile_pic": profile_pic,
        "image": image,
        "shared_from": shared_from_info,
        "post_id": posts[0].id,
        "author": user.username,
        "author_id": posts[0].user_id,
        "day": day,
        "hour": hour,
        posts[0].id: None,
        "children": [],
        "likes": len(
            list(Reactions.query.filter_by(post_id=posts[0].id, type="like").all())
        ),
        "dislikes": len(
            list(Reactions.query.filter_by(post_id=posts[0].id, type="dislike").all())
        ),
        "is_liked": Reactions.query.filter_by(
            post_id=posts[0].id, user_id=exp_user_id, type="like"
        ).first()
        is None,
        "is_disliked": Reactions.query.filter_by(
            post_id=posts[0].id, user_id=exp_user_id, type="dislike"
        ).first()
        is None,
        "is_shared": len(Post.query.filter_by(shared_from=posts[0].id).all()),
        "emotions": get_elicited_emotions(posts[0].id),
        "topics": get_topics(posts[0].id, posts[0].user_id),
    }

    reverse_map = {posts[0].id: None}
    post_to_child = {posts[0].id: []}
    post_to_data = {posts[0].id: discussion_tree}
    parent_id = posts[0].id

    for post in posts[1:]:
        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        user = User_mgmt.query.filter_by(id=post.user_id).first()
        profile_pic = ""
        if user.is_page == 1:
            pg = Page.query.filter_by(name=user.username).first()
            if pg is not None:
                profile_pic = pg.logo
        else:
            try:
                ag = Agent.query.filter_by(name=user.username).first()
                profile_pic = (
                    ag.profile_pic
                    if ag is not None and ag.profile_pic is not None
                    else Admin_users.query.filter_by(username=user.username)
                    .first()
                    .profile_pic
                )
            except:
                profile_pic = ""

        data = {
            "post": augment_text(post.tweet, exp_id),
            "post_id": post.id,
            "author": user.username,
            "author_id": post.user_id,
            "profile_pic": profile_pic,
            "day": day,
            "hour": hour,
            "children": [],
            "likes": len(
                list(Reactions.query.filter_by(post_id=post.id, type="like").all())
            ),
            "dislikes": len(
                list(Reactions.query.filter_by(post_id=post.id, type="dislike").all())
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
            "emotions": get_elicited_emotions(post.id),
            "topics": get_topics(post.id, post.user_id),
        }

        parent = post.comment_to
        reverse_map[post.id] = parent

        if parent != -1:
            if parent in post_to_child:
                post_to_child[parent].append(post.id)
                post_to_child[post.id] = []
                post_to_data[post.id] = data

    tree = __expand_tree(post_to_child, post_to_data)
    discussion_tree = tree[root]
    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(exp_user_id)

    # get user profile pic
    user = User_mgmt.query.filter_by(username=current_user.username).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=user.username)
                .first()
                .profile_pic
            )
        except:
            profile_pic = ""

    logged_id = user.id

    return render_template(
        "thread.html",
        thread=discussion_tree,
        profile_pic=profile_pic,
        user_id=logged_id,
        username=current_user.username,
        logged_username=current_user.username,
        logged_id=logged_id,
        str=str,
        bool=bool,
        enumerate=enumerate,
        trending_ht=trending_ht,
        len=len,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


def __expand_tree(post_to_child, post_to_data):
    """Handle   expand tree operation."""
    for pid, clds in post_to_child.items():
        for cl in clds:
            post_to_data[pid]["children"].append(post_to_data[cl])

    return post_to_data


def recursive_visit(data):
    """Handle recursive visit operation."""
    if len(data["children"]) == 0:
        return data["post"]
    else:
        for c in data["children"]:
            return recursive_visit(c)


def __get_discussions(posts, username, page, exp_id, exp_user_id=None):
    """Handle   get discussions operation."""
    res = []

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

            profile_pic = ""

            user = User_mgmt.query.filter_by(id=c.user_id).first()

            if user.is_page == 1:
                pg = Page.query.filter_by(name=user.username).first()
                if page is not None:
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
                    "emotions": emotions,
                    "topics": topics,
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

        # get elicited emotions names
        emotions = get_elicited_emotions(post.id)
        aa = User_mgmt.query.filter_by(id=post.user_id).first()

        # Handle case where user doesn't exist
        if aa is None:
            # Skip this post if the author doesn't exist in user_mgmt
            continue

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

        # Get author username safely
        author_user = User_mgmt.query.filter_by(id=post.user_id).first()
        author_username = author_user.username if author_user else "Unknown"

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
                "post": augment_text(post.tweet.split(":")[-1], exp_id),
                "round": post.round,
                "day": day,
                "hour": hour,
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
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
                "topics": topics,
            }
        )

    return res


#### Forum


def _forum_logged_user():
    user = User_mgmt.query.filter_by(username=current_user.username).first()
    if user is None and str(getattr(current_user, "id", "")).isdigit():
        user = User_mgmt.query.filter_by(id=int(current_user.id)).first()
    return user


def _forum_profile_pic(user):
    if not user:
        return ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        return pg.logo if pg is not None else ""
    try:
        ag = Agent.query.filter_by(name=user.username).first()
        if ag is not None and ag.profile_pic is not None:
            return ag.profile_pic
        admin = Admin_users.query.filter_by(username=user.username).first()
        return admin.profile_pic if admin is not None else ""
    except Exception:
        return ""


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
            .add_columns(
                Post,
                func.sum(
                    (Reactions.type == "like").cast(db.Integer)
                    - (Reactions.type == "dislike").cast(db.Integer)
                ).label("score"),
            )
            .group_by(Post.id)
            .order_by(desc("score"), desc(Post.id))
        )
    elif normalized_feed == "most_commented":
        query = base_query.order_by(desc(Post.id))
    else:
        query = base_query.order_by(desc(Post.id))

    return normalized_feed, query.paginate(page=page, per_page=per_page, error_out=False)


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


@main.get("/<int:exp_id>/interview")
@login_required
def interview(exp_id):
    admin_user = Admin_users.query.filter_by(username=current_user.username).first()
    if not admin_user or admin_user.role not in {"admin", "researcher"}:
        abort(403)

    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp:
        abort(404)

    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    logged_id = (
        int(exp_user.id) if exp_user else int(getattr(current_user, "id", 0) or 0)
    )

    mentions = []
    try:
        mentions = get_unanswered_mentions(logged_id)
    except Exception:
        mentions = []

    return render_template(
        "reddit/interview.html",
        logged_username=current_user.username,
        logged_id=logged_id,
        profile_pic=get_safe_profile_pic(current_user.username, 0),
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        exp_id=exp_id,
    )


@main.get("/<int:exp_id>/rthread/<post_id>")
@login_required
def get_thread_reddit(exp_id, post_id):
    try:
        post_id = int(post_id)
    except (ValueError, TypeError):
        pass

    root_post = Post.query.filter_by(id=post_id).first()
    if root_post is None:
        flash("Thread not found.")
        return redirect(f"/{exp_id}/rfeed/all/feed/rf/1?feed_type=new")

    thread_id = root_post.thread_id
    posts = Post.query.filter_by(thread_id=thread_id).order_by(Post.id.asc()).all()
    if not posts:
        flash("Thread not found.")
        return redirect(f"/{exp_id}/rfeed/all/feed/rf/1?feed_type=new")

    root = posts[0].id

    c = Rounds.query.filter_by(id=posts[0].round).first()
    day = c.day if c is not None else "None"
    hour = c.hour if c is not None else "00"

    image = Images.query.filter_by(id=posts[0].image_id).first()
    user = User_mgmt.query.filter_by(id=posts[0].user_id).first()
    root_profile_pic = _forum_profile_pic(user)

    title, content = process_reddit_post(posts[0].tweet)
    processed_content = augment_text(content, exp_id) if content else ""

    article = Articles.query.filter_by(id=posts[0].news_id).first()
    if article is None:
        art = 0
    else:
        website = Websites.query.filter_by(id=article.website_id).first()
        art = {
            "title": article.title,
            "summary": strip_tags(article.summary),
            "url": article.link,
            "source": website.name if website is not None else "",
        }

    if posts[0].shared_from == -1:
        shared_from_info = -1
    else:
        shared_user = (
            db.session.query(User_mgmt)
            .join(Post, User_mgmt.id == Post.user_id)
            .filter(Post.id == posts[0].shared_from)
            .first()
        )
        shared_from_info = (
            (posts[0].shared_from, shared_user.username)
            if shared_user
            else (posts[0].shared_from, "Unknown")
        )

    discussion_tree = {
        "title": title,
        "post": processed_content,
        "profile_pic": root_profile_pic,
        "image": image,
        "shared_from": shared_from_info,
        "post_id": posts[0].id,
        "author": user.username if user is not None else "Unknown",
        "author_id": posts[0].user_id,
        "day": day,
        "hour": hour,
        "article": art,
        posts[0].id: None,
        "children": [],
        "likes": len(
            list(Reactions.query.filter_by(post_id=posts[0].id, type="like").all())
        ),
        "dislikes": len(
            list(Reactions.query.filter_by(post_id=posts[0].id, type="dislike").all())
        ),
        "is_liked": Reactions.query.filter_by(
            post_id=posts[0].id, user_id=current_user.id, type="like"
        ).first()
        is not None,
        "is_disliked": Reactions.query.filter_by(
            post_id=posts[0].id, user_id=current_user.id, type="dislike"
        ).first()
        is not None,
        "is_shared": len(Post.query.filter_by(shared_from=posts[0].id).all()),
        "emotions": get_elicited_emotions(posts[0].id),
        "topics": get_topics(posts[0].id, posts[0].user_id),
    }

    post_to_child = {posts[0].id: []}
    post_to_data = {posts[0].id: discussion_tree}

    for post in posts[1:]:
        c = Rounds.query.filter_by(id=post.round).first()
        day = c.day if c is not None else "None"
        hour = c.hour if c is not None else "00"

        user = User_mgmt.query.filter_by(id=post.user_id).first()
        profile_pic = _forum_profile_pic(user)

        comment_title, comment_content = process_reddit_post(post.tweet)
        processed_comment = (
            augment_text(comment_content, exp_id) if comment_content else ""
        )

        article = Articles.query.filter_by(id=post.news_id).first()
        if article is None:
            art = 0
        else:
            website = Websites.query.filter_by(id=article.website_id).first()
            art = {
                "title": article.title,
                "summary": strip_tags(article.summary),
                "url": article.link,
                "source": website.name if website is not None else "",
            }

        data = {
            "title": comment_title,
            "post": processed_comment,
            "post_id": post.id,
            "author": user.username if user is not None else "Unknown",
            "author_id": post.user_id,
            "profile_pic": profile_pic,
            "day": day,
            "hour": hour,
            "article": art,
            "children": [],
            "likes": len(
                list(Reactions.query.filter_by(post_id=post.id, type="like").all())
            ),
            "dislikes": len(
                list(Reactions.query.filter_by(post_id=post.id, type="dislike").all())
            ),
            "is_liked": Reactions.query.filter_by(
                post_id=post.id, user_id=current_user.id, type="like"
            ).first()
            is None,
            "is_disliked": Reactions.query.filter_by(
                post_id=post.id, user_id=current_user.id, type="dislike"
            ).first()
            is None,
            "is_shared": len(Post.query.filter_by(shared_from=post.id).all()),
            "emotions": get_elicited_emotions(post.id),
            "topics": get_topics(post.id, post.user_id),
        }

        parent = post.comment_to
        if parent != -1 and parent in post_to_child:
            post_to_child[parent].append(post.id)
            post_to_child[post.id] = []
            post_to_data[post.id] = data

    tree = __expand_tree(post_to_child, post_to_data)
    discussion_tree = tree[root]
    trending_ht = get_trending_hashtags()
    logged_user = _forum_logged_user()
    mention_user_id = logged_user.id if logged_user is not None else None
    mentions = get_unanswered_mentions(mention_user_id) if mention_user_id else []

    return render_template(
        "reddit/thread.html",
        thread=discussion_tree,
        profile_pic=_forum_profile_pic(logged_user),
        user_id=current_user.id,
        username=current_user.username,
        logged_username=current_user.username,
        logged_id=logged_user.id if logged_user is not None else current_user.id,
        str=str,
        bool=bool,
        enumerate=enumerate,
        trending_ht=trending_ht,
        len=len,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        exp_id=exp_id,
        back_url=_forum_resolve_back_url(exp_id),
    )


@main.get("/rfeed")
@login_required
def feeed_logged_reddit():
    """
    Display Reddit-style feed for logged-in users.
    Legacy route - redirects to experiment selection or first active experiment.

    Returns:
        Redirect to Reddit feed with experiment ID
    """
    # Get active experiments
    exps = Exps.query.filter(Exps.status != 0).all()
    if not exps:
        flash("No active experiment. Please activate an experiment first.")
        return redirect("/admin/experiments")

    if len(exps) > 1:
        return redirect("/admin/join_simulation")

    exp = exps[0]
    return redirect(f"/{exp.idexp}/rfeed/all/feed/rf/1?feed_type=new")


@main.get("/rnotifications")
@login_required
def rnotifications_logged():
    exps = Exps.query.filter(Exps.status != 0).all()
    if not exps:
        flash("No active experiment. Please activate an experiment first.")
        return redirect("/admin/experiments")
    if len(exps) > 1:
        return redirect("/admin/join_simulation")
    return redirect(f"/{exps[0].idexp}/rnotifications")


@main.get("/<int:exp_id>/rnotifications")
@login_required
def rnotifications(exp_id):
    from sqlalchemy import func
    from sqlalchemy.orm import aliased

    exp = Exps.query.filter_by(idexp=exp_id).first()
    if not exp:
        flash("Experiment not found.")
        return redirect("/admin/experiments")
    if exp.platform_type != "forum":
        return redirect(f"/{exp_id}/feed/{current_user.id}/feed/rf/1")

    page = max(request.args.get("page", type=int, default=1), 1)
    per_page = 25
    offset = (page - 1) * per_page

    logged_user = _forum_logged_user()
    exp_user_id = logged_user.id if logged_user is not None else None

    if exp_user_id is None:
        return render_template(
            "reddit/notifications.html",
            items=[],
            page=page,
            has_more=False,
            unread_before_open=0,
            profile_pic=get_safe_profile_pic(current_user.username, 0),
            logged_username=current_user.username,
            logged_id=current_user.id,
            mentions=[],
            is_admin=is_admin(current_user.username),
            exp_id=exp_id,
            len=len,
            str=str,
            bool=bool,
            enumerate=enumerate,
        )

    state = ReplyInboxState.query.filter_by(user_id=exp_user_id).first()
    if not state:
        state = ReplyInboxState(user_id=exp_user_id, last_seen_reply_id=0)
        db.session.add(state)
        db.session.commit()

    cutoff = int(state.last_seen_reply_id or 0)

    Reply = aliased(Post)
    Parent = aliased(Post)
    Author = aliased(User_mgmt)

    base_filters = (
        Parent.user_id == exp_user_id,
        Reply.user_id != exp_user_id,
        Reply.comment_to != -1,
    )

    unread_before_open = (
        db.session.query(func.count(Reply.id))
        .join(Parent, Reply.comment_to == Parent.id)
        .filter(*base_filters, Reply.id > cutoff)
        .scalar()
    )
    unread_before_open = int(unread_before_open or 0)

    rows = (
        db.session.query(Reply, Parent, Author)
        .join(Parent, Reply.comment_to == Parent.id)
        .join(Author, Author.id == Reply.user_id)
        .filter(*base_filters)
        .order_by(Reply.id.desc())
        .limit(per_page + 1)
        .offset(offset)
        .all()
    )
    has_more = len(rows) > per_page
    rows = rows[:per_page]

    def _excerpt(text, max_len=140):
        cleaned = " ".join(str(text or "").strip().split())
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[: max_len - 1].rstrip() + "…"

    items = [
        {
            "reply_id": reply_post.id,
            "thread_url": f"/{exp_id}/rthread/{reply_post.id}",
            "author_id": author.id,
            "author_username": author.username,
            "author_profile_pic": _forum_profile_pic(author),
            "reply_excerpt": _excerpt(getattr(reply_post, "tweet", "")),
            "parent_excerpt": _excerpt(getattr(parent_post, "tweet", "")),
            "parent_is_root": bool(getattr(parent_post, "comment_to", -1) == -1),
            "was_unread": bool(reply_post.id > cutoff),
        }
        for reply_post, parent_post, author in rows
    ]

    max_reply_id = (
        db.session.query(func.max(Reply.id))
        .join(Parent, Reply.comment_to == Parent.id)
        .filter(*base_filters)
        .scalar()
    )
    max_reply_id = int(max_reply_id or 0)
    if max_reply_id > cutoff:
        state.last_seen_reply_id = max_reply_id
        db.session.commit()

    return render_template(
        "reddit/notifications.html",
        items=items,
        page=page,
        has_more=has_more,
        unread_before_open=unread_before_open,
        profile_pic=get_safe_profile_pic(current_user.username, 0),
        logged_username=current_user.username,
        logged_id=exp_user_id,
        mentions=get_unanswered_mentions(exp_user_id),
        is_admin=is_admin(current_user.username),
        exp_id=exp_id,
        len=len,
        str=str,
        bool=bool,
        enumerate=enumerate,
    )


@main.get("/<int:exp_id>/rfeed")
@login_required
def rfeed_redirect(exp_id):
    query_string = request.query_string.decode("utf-8")
    target = f"/{exp_id}/rfeed/all/feed/rf/1"
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target)


@main.get(
    "/<int:exp_id>/rfeed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>"
)
@login_required
def feed_reddit(exp_id, user_id="all", timeline="timeline", mode="rf", page=1):
    if page < 1:
        page = 1

    max_post_per_page = 10
    feed_type = request.args.get("feed_type", "new")
    page_obj = fetch_feed_page(
        viewer_id=current_user.id,
        page=page,
        per_page=max_post_per_page,
        feed_type=feed_type,
        search_query="",
    )
    logged_user = _forum_logged_user()
    exp_user_id = logged_user.id if logged_user else current_user.id
    mentions = get_unanswered_mentions(logged_user.id) if logged_user else []
    res = [post.to_dict() for post in page_obj.posts]
    suggested_users = (
        get_suggested_users(logged_user.username, pages=False) if logged_user else []
    )
    suggested_pages = (
        get_suggested_users(logged_user.username, pages=True) if logged_user else []
    )

    if len(res) == 0 and page > 1:
        return redirect(
            f"/{exp_id}/rfeed/{user_id}/{timeline}/{mode}/{page - 1}?feed_type={feed_type}"
        )

    profile_pic = get_safe_profile_pic(current_user.username, 0)
    profile_pic_feed = _forum_profile_pic(logged_user)

    return render_template(
        "reddit/feed.html",
        items=res,
        page=page_obj.page,
        profile_pic=profile_pic,
        profile_pic_feed=profile_pic_feed,
        user_id=user_id,
        feed_user_id=None,
        timeline=timeline,
        username="",
        mode=mode,
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        logged_id=exp_user_id,
        trending_ht=get_trending_hashtags(),
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        sfollow=suggested_users,
        spages=suggested_pages,
        feed_type=feed_type,
        search_query="",
        view_mode="feed",
        search_total=None,
        per_page=max_post_per_page,
        has_more=(page_obj.page * page_obj.per_page) < page_obj.total,
        exp_id=exp_id,
    )


@main.get("/<int:exp_id>/rsearch")
@login_required
def search_reddit(exp_id):
    page = max(request.args.get("page", type=int, default=1), 1)
    per_page = 10
    search_query = (request.args.get("q") or "").strip()
    feed_type = request.args.get("feed_type", "new")

    logged_user = _forum_logged_user()
    exp_user_id = logged_user.id if logged_user else current_user.id
    mentions = get_unanswered_mentions(logged_user.id) if logged_user else []
    suggested_users = (
        get_suggested_users(logged_user.username, pages=False) if logged_user else []
    )
    suggested_pages = (
        get_suggested_users(logged_user.username, pages=True) if logged_user else []
    )

    if search_query:
        page_obj = fetch_feed_page(
            viewer_id=current_user.id,
            page=page,
            per_page=per_page,
            feed_type=feed_type,
            search_query=search_query,
        )
        res = [post.to_dict() for post in page_obj.posts]
        has_more = (page_obj.page * page_obj.per_page) < page_obj.total
        current_page = page_obj.page
        total_results = page_obj.total
    else:
        res = []
        has_more = False
        current_page = 1
        total_results = 0

    if not res and page > 1:
        query = {"q": search_query, "feed_type": feed_type, "page": page - 1}
        return redirect(f"/{exp_id}/rsearch?{urlencode(query)}")

    return render_template(
        "reddit/feed.html",
        items=res,
        page=current_page,
        profile_pic=get_safe_profile_pic(current_user.username, 0),
        profile_pic_feed=_forum_profile_pic(logged_user),
        user_id="all",
        feed_user_id=None,
        timeline="feed",
        username="",
        mode="rf",
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        logged_id=(logged_user.id if logged_user else current_user.id),
        trending_ht=get_trending_hashtags(),
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        sfollow=suggested_users,
        spages=suggested_pages,
        feed_type=feed_type,
        search_query=search_query,
        view_mode="search",
        search_total=total_results,
        per_page=per_page,
        has_more=has_more,
        exp_id=exp_id,
    )


# API Endpoints for Infinite Scrolling


@main.get(
    "/<int:exp_id>/api/feed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>"
)
@login_required
def api_feed(exp_id, user_id="all", timeline="timeline", mode="rf", page=1):
    """
    API endpoint for infinite scrolling in feed.

    Returns rendered HTML for posts.
    """
    if page < 1:
        page = 1

    max_post_per_page = 10
    username = ""
    posts, additional = None, None

    if user_id == "all":
        posts, additional = get_suggested_posts("all", "", page, max_post_per_page)
    elif user_id != "all":
        user = User_mgmt.query.filter_by(id=user_id).first()
        recsys = user.recsys_type
        posts, additional = get_suggested_posts(
            user_id, recsys, page, max_post_per_page
        )
        username = user.username

    res, res_additional = [], []

    # Get experiment user ID for reactions
    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    exp_user_id = exp_user.id if exp_user else current_user.id

    if posts is not None:
        res = __get_discussions(posts, username, page, exp_id, exp_user_id)
    if additional is not None:
        res_additional = __get_discussions(
            additional, username, page, exp_id, exp_user_id
        )

    # combine the posts and additional posts
    if len(res_additional) > 0:
        for add in res_additional:
            res.append(add)

    html = render_template(
        "components/posts.html",
        items=res,
        enumerate=enumerate,
        user_id=user_id if user_id != "all" else current_user.id,
        str=str,
        bool=bool,
        len=len,
    )
    return jsonify({"html": html, "has_more": len(res) > 0})


@main.get(
    "/<int:exp_id>/api/rfeed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>"
)
@login_required
def api_feed_reddit(exp_id, user_id="all", timeline="timeline", mode="rf", page=1):
    """
    API endpoint for infinite scrolling in Reddit-style feed.

    Returns rendered HTML for posts.
    """
    if page < 1:
        page = 1

    max_post_per_page = 10
    username = ""
    posts, additional = None, None

    feed_type = request.args.get("feed_type", "new")

    if user_id == "all":
        if feed_type == "top":
            posts_query = (
                Post.query.filter_by(comment_to=-1)
                .outerjoin(Reactions, Post.id == Reactions.post_id)
                .add_columns(
                    Post,
                    func.sum(
                        (Reactions.type == "like").cast(db.Integer)
                        - (Reactions.type == "dislike").cast(db.Integer)
                    ).label("score"),
                )
                .group_by(Post.id)
                .order_by(desc("score"), desc(Post.id))
            )
            posts = posts_query.paginate(
                page=page, per_page=max_post_per_page, error_out=False
            )
            additional = None
        elif feed_type == "most_commented":
            posts = (
                Post.query.filter_by(comment_to=-1)
                .order_by(desc(Post.id))
                .paginate(page=page, per_page=max_post_per_page, error_out=False)
            )
            additional = None
        else:
            posts = (
                Post.query.filter_by(comment_to=-1)
                .order_by(desc(Post.id))
                .paginate(page=page, per_page=max_post_per_page, error_out=False)
            )
            additional = None

    elif user_id != "all":
        user = User_mgmt.query.filter_by(id=user_id).first()
        if feed_type == "top":
            posts_query = (
                Post.query.filter(Post.user_id != user_id, Post.comment_to == -1)
                .outerjoin(Reactions, Post.id == Reactions.post_id)
                .add_columns(
                    Post,
                    func.sum(
                        (Reactions.type == "like").cast(db.Integer)
                        - (Reactions.type == "dislike").cast(db.Integer)
                    ).label("score"),
                )
                .group_by(Post.id)
                .order_by(desc("score"), desc(Post.id))
            )
            posts = posts_query.paginate(
                page=page, per_page=max_post_per_page, error_out=False
            )
            additional = None
        elif feed_type == "most_commented":
            posts = (
                Post.query.filter(Post.comment_to == -1)
                .order_by(desc(Post.id))
                .paginate(page=page, per_page=max_post_per_page, error_out=False)
            )
            additional = None
        else:
            posts = (
                Post.query.filter(Post.comment_to == -1)
                .order_by(desc(Post.id))
                .paginate(page=page, per_page=max_post_per_page, error_out=False)
            )
            additional = None
        username = user.username

    res, res_additional = [], []

    # Get experiment user ID for reactions
    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    exp_user_id = exp_user.id if exp_user else current_user.id

    if posts is not None:
        res = __get_discussions(posts, username, page, exp_id, exp_user_id)
    if additional is not None:
        res_additional = __get_discussions(
            additional, username, page, exp_id, exp_user_id
        )

    # combine the posts and additional posts
    if len(res_additional) > 0:
        for add in res_additional:
            res.append(add)

    html = render_template(
        "reddit/components/posts.html",
        items=res,
        enumerate=enumerate,
        user_id=user_id if user_id != "all" else current_user.id,
        str=str,
        bool=bool,
        len=len,
    )
    return jsonify({"html": html, "has_more": len(res) > 0})


@main.get("/<int:exp_id>/api/hashtag_posts/<hashtag_id>/<int:page>")
@login_required
def api_hashtag_posts(exp_id, hashtag_id, page=1):
    """
    # Handle both int and UUID hashtag_id formats (Standard vs HPC experiments)
    try:
        hashtag_id = int(hashtag_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass
    API endpoint for infinite scrolling in hashtag posts.

    Returns rendered HTML for posts.
    """
    res = get_posts_associated_to_hashtags(
        hashtag_id, page, per_page=10, current_user=current_user.id, exp_id=exp_id
    )
    html = render_template(
        "components/posts.html",
        items=res,
        enumerate=enumerate,
        user_id=current_user.id,
        str=str,
        bool=bool,
        len=len,
    )
    return jsonify({"html": html, "has_more": len(res) > 0})


@main.get("/<int:exp_id>/api/interest/<interest_id>/<int:page>")
@login_required
def api_interest_posts(exp_id, interest_id, page=1):
    """
    # Handle both int and UUID interest_id formats (Standard vs HPC experiments)
    try:
        interest_id = int(interest_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass
    API endpoint for infinite scrolling in interest posts.

    Returns rendered HTML for posts.
    """
    res = get_posts_associated_to_interest(
        interest_id, page, per_page=10, current_user=current_user.id, exp_id=exp_id
    )
    html = render_template(
        "components/posts.html",
        items=res,
        enumerate=enumerate,
        user_id=current_user.id,
        str=str,
        bool=bool,
        len=len,
    )
    return jsonify({"html": html, "has_more": len(res) > 0})


@main.get("/<int:exp_id>/api/emotion/<emotion_id>/<int:page>")
@login_required
def api_emotion_posts(exp_id, emotion_id, page=1):
    """
    # Handle both int and UUID emotion_id formats (Standard vs HPC experiments)
    try:
        emotion_id = int(emotion_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass
    API endpoint for infinite scrolling in emotion posts.

    Returns rendered HTML for posts.
    """
    res = get_posts_associated_to_emotion(
        emotion_id,
        page,
        per_page=10,
        current_user=current_user.id,
        exp_id=exp_id,
    )
    html = render_template(
        "components/posts.html",
        items=res,
        enumerate=enumerate,
        user_id=current_user.id,
        str=str,
        bool=bool,
        len=len,
    )
    return jsonify({"html": html, "has_more": len(res) > 0})


@main.get("/<int:exp_id>/api/profile/<user_id>/<string:mode>/<int:page>")
@login_required
def api_profile_posts(exp_id, user_id, page=1, mode="recent"):
    """
    API endpoint for infinite scrolling in profile posts.

    Returns rendered HTML for posts.
    """
    # Handle both int and UUID user_id formats (Standard vs HPC experiments)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass

    rp = get_user_recent_posts(user_id, page, 10, mode, current_user.id, exp_id)
    html = render_template(
        "components/posts.html",
        items=rp,
        enumerate=enumerate,
        user_id=user_id,
        str=str,
        bool=bool,
        len=len,
    )
    return jsonify({"html": html, "has_more": len(rp) > 0})
