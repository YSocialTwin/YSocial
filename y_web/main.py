"""
Main application routes and views.

Handles the primary user-facing routes including the home feed, user profiles,
hashtag pages, post details, and search functionality for the social media platform.
"""

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.recsys_support import get_suggested_posts, get_suggested_users

from .data_access import *
from .models import Admin_users, Exps, Images, Page

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


@main.app_errorhandler(404)
def page_not_found(e):
    """
    Handle 404 errors with custom error page.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 404 template, 404 status code)
    """
    return render_template("404.html"), 404


@main.route("/")
def index():
    """
    Home page route - redirects authenticated users to feed, others to login.

    Returns:
        Redirect to appropriate page based on authentication status
    """
    if current_user.is_authenticated:
        # get active experiment if exists
        exp = Exps.query.filter(Exps.status != 0).first()
        if exp is not None:
            if exp.platform_type == "microblogging":
                return redirect(f"/feed/{current_user.id}/feed/rf/1")
            elif exp.platform_type == "forum":
                return redirect(f"/rfeed/{current_user.id}/rfeed/rf/1")
    return render_template("login.html")


@main.get("/profile")
@login_required
def profile():
    """Handle profile operation."""
    user_id = current_user.id
    return redirect(f"/profile/{user_id}/rf/1")


@main.get("/profile/<int:user_id>/<string:mode>/<int:page>")
@login_required
def profile_logged(user_id, page=1, mode="recent"):
    """Handle profile logged operation."""
    user_id = int(user_id)
    user = User_mgmt.query.get(user_id)

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
    rp = get_user_recent_posts(user_id, page, 10, mode, current_user.id)
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
        logged_id=current_user.id,
        is_following=is_following,
        interests=interests,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


@main.get("/edit_profile/<int:user_id>")
@login_required
def edit_profile(user_id):
    """Handle edit profile operation."""
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

    return render_template(
        "edit_profile.html",
        user=user,
        profile_pic=profile_pic,
        is_page=user.is_page,
        enumerate=enumerate,
        username=user.username,
        len=len,
        user_id=int(user_id),
        logged_username=current_user.username,
        str=str,
        logged_id=current_user.id,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.route("/update_profile_data/<int:user_id>", methods=["POST"])
@login_required
def update_profile_data(user_id):
    """Update profile data."""
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


@main.route("/update_password/<int:user_id>", methods=["POST"])
@login_required
def update_password(user_id):
    """Update password."""
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

    Returns:
        Redirect to feed with user ID and default parameters
    """
    user_id = current_user.id
    return redirect(f"/feed/{user_id}/feed/rf/1")


@main.get("/feed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>")
@login_required
def feed(user_id="all", timeline="timeline", mode="rf", page=1):
    """Handle feed operation."""
    if page < 1:
        page = 1

    max_post_per_page = 10
    username = ""
    posts, additional = None, None

    if user_id == "all":
        posts, additional = get_suggested_posts("all", "", page, max_post_per_page)

    elif user_id != "all":
        user = User_mgmt.query.filter_by(id=int(user_id)).first()
        recsys = user.recsys_type

        posts, additional = get_suggested_posts(
            user_id, recsys, page, max_post_per_page
        )
        username = user.username

    res, res_additional = [], []

    if posts is not None:
        res = __get_discussions(posts, username, page)
    if additional is not None:
        res_additional = __get_discussions(additional, username, page)

    # combine the posts and additional posts
    if len(res_additional) > 0:
        for add in res_additional:
            res.append(add)

    # not enough posts to display
    if len(res) == 0 and page > 1:
        return redirect(f"/feed/{user_id}/{timeline}/{mode}/{page - 1}")

    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.id)
    sfollow = get_suggested_users(user_id, pages=False)
    spages = get_suggested_users(user_id, pages=True)

    # get user profile pic
    if user_id != "all":
        user = User_mgmt.query.filter_by(id=user_id).first()
    else:
        user = User_mgmt.query.filter_by(id=current_user.id).first()

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
        logged_id=current_user.id,
        trending_ht=trending_ht,
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        sfollow=sfollow,
        spages=spages,
    )


@main.get("/hashtag_posts/<int:hashtag_id>/<int:page>")
@login_required
def get_post_hashtags(hashtag_id, page=1):
    """
    Display posts containing a specific hashtag.

    Args:
        hashtag_id: ID of hashtag to filter posts by
        page: Page number for pagination (default: 1)

    Returns:
        Rendered template with hashtag posts
    """
    res = get_posts_associated_to_hashtags(
        hashtag_id, page, per_page=10, current_user=current_user.id
    )

    if len(res) == 0:
        return redirect(f"/hashtag_posts/{hashtag_id}/{page - 1}")

    # get hashtag name
    hashtag = Hashtags.query.filter_by(id=hashtag_id).first().hashtag

    trending_ht = get_trending_hashtags()

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
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

    return render_template(
        "hashtag.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=int(current_user.id),
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_ht,
        logged_id=int(current_user.id),
        hashtag_id=hashtag_id,
        current_hashtag=hashtag,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/interest/<int:interest_id>/<int:page>")
@login_required
def get_post_interest(interest_id, page=1):
    """
    Display posts associated with a specific interest/topic.

    Args:
        interest_id: ID of interest/topic to filter posts by
        page: Page number for pagination (default: 1)

    Returns:
        Rendered template with interest-related posts
    """
    res = get_posts_associated_to_interest(
        interest_id, page, per_page=10, current_user=current_user.id
    )

    if len(res) == 0:
        return redirect(f"/interest/{interest_id}/{page - 1}")

    # get topic name
    interest = Interests.query.filter_by(iid=interest_id).first().interest

    trending_tp = get_trending_topics()

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
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

    return render_template(
        "interest.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=int(current_user.id),
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_tp,
        logged_id=int(current_user.id),
        interest_id=interest_id,
        current_interest=interest,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/emotion/<int:emotion_id>/<int:page>")
@login_required
def get_post_emotion(emotion_id, page=1):
    """
    Display posts that elicit a specific emotion.

    Args:
        emotion_id: ID of emotion to filter posts by
        page: Page number for pagination (default: 1)

    Returns:
        Rendered template with emotion-tagged posts
    """
    res = get_posts_associated_to_emotion(
        emotion_id, page, per_page=10, current_user=current_user.id
    )

    if len(res) == 0:
        return redirect(f"/emotion/{emotion_id}/{page - 1}")

    # get emotion name
    emotion = Emotions.query.filter_by(id=emotion_id).first()
    emotion = (emotion_id, emotion.emotion, emotion.icon)

    trending_tp = get_trending_emotions()

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
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

    return render_template(
        "emotions.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=int(current_user.id),
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_tp,
        logged_id=int(current_user.id),
        emotion_id=emotion_id,
        current_emotion=emotion,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/friends/<int:user_id>/<int:page>")
@login_required
def get_friends(user_id, page=1):
    """
    Display user's followers and followees (friends).

    Args:
        user_id: ID of user whose friends to display
        page: Page number for pagination (default: 1)

    Returns:
        Rendered template showing followers and followees
    """
    followers, followees, number_followers, number_followees = get_user_friends(
        user_id, limit=12, page=page
    )
    mentions = get_unanswered_mentions(current_user.id)

    cu = User_mgmt.query.filter_by(id=current_user.id).first()

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
        logged_id=int(cu.id),
        user_id=user_id,
        number_followers=number_followers,
        number_followees=number_followees,
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


@main.get("/thread/<int:post_id>")
@login_required
def get_thread(post_id):
    # get thread_id for post_id
    """Get thread."""
    thread_id = Post.query.filter_by(id=post_id).first().thread_id

    # get all posts with the specified thread id
    posts = Post.query.filter_by(thread_id=thread_id).order_by(Post.id.asc()).all()

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

    discussion_tree = {
        "post": augment_text(posts[0].tweet),
        "profile_pic": profile_pic,
        "image": image,
        "shared_from": (
            -1
            if posts[0].shared_from == -1
            else (
                posts[0].shared_from,
                db.session.query(User_mgmt)
                .join(Post, User_mgmt.id == Post.user_id)
                .filter(Post.id == posts[0].shared_from)
                .first()
                .username,
            )
        ),
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
            post_id=posts[0].id, user_id=current_user.id, type="like"
        ).first()
        is None,
        "is_disliked": Reactions.query.filter_by(
            post_id=posts[0].id, user_id=current_user.id, type="dislike"
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
            "post": augment_text(post.tweet),
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
        reverse_map[post.id] = parent

        if parent != -1:
            if parent in post_to_child:
                post_to_child[parent].append(post.id)
                post_to_child[post.id] = []
                post_to_data[post.id] = data

    tree = __expand_tree(post_to_child, post_to_data)
    discussion_tree = tree[root]
    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.id)

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
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

    return render_template(
        "thread.html",
        thread=discussion_tree,
        profile_pic=profile_pic,
        user_id=current_user.id,
        username=current_user.username,
        logged_username=current_user.username,
        logged_id=int(current_user.id),
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


def __get_discussions(posts, username, page):
    """Handle   get discussions operation."""
    res = []

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

                if ag is None:
                    continue

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

            cms.append(
                {
                    "post_id": c.id,
                    "profile_pic": profile_pic,
                    "author": author,
                    "shared_from": (
                        -1
                        if c.shared_from == -1
                        else (
                            c.shared_from,
                            db.session.query(User_mgmt)
                            .join(Post, User_mgmt.id == Post.user_id)
                            .filter(Post.id == c.shared_from)
                            .first()
                            .username,
                        )
                    ),
                    "author_id": int(c.user_id),
                    "post": augment_text(text),
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
                        post_id=c.id, user_id=current_user.id, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user.id, type="dislike"
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

        res.append(
            {
                "article": art,
                "image": image,
                "profile_pic": profile_pic,
                "thread_id": post.thread_id,
                "shared_from": (
                    -1
                    if post.shared_from == -1
                    else (
                        post.shared_from,
                        db.session.query(User_mgmt)
                        .join(Post, User_mgmt.id == Post.user_id)
                        .filter(Post.id == post.shared_from)
                        .first()
                        .username,
                    )
                ),
                "post_id": post.id,
                "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
                "author_id": int(post.user_id),
                "post": augment_text(post.tweet.split(":")[-1]),
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
                    post_id=post.id, user_id=current_user.id, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user.id, type="dislike"
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


#### Thread


@main.get("/rthread/<int:post_id>")
@login_required
def get_thread_reddit(post_id):
    # get thread_id for post_id
    """Get thread reddit."""
    thread_id = Post.query.filter_by(id=post_id).first().thread_id

    # get all posts with the specified thread id
    posts = Post.query.filter_by(thread_id=thread_id).order_by(Post.id.asc()).all()

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

    # Process post content for Reddit-style display
    title, content = process_reddit_post(posts[0].tweet)
    processed_content = augment_text(content) if content else ""

    # Get article for main post
    article = Articles.query.filter_by(id=posts[0].news_id).first()
    if article is None:
        art = 0
    else:
        art = {
            "title": article.title,
            "summary": strip_tags(article.summary),
            "url": article.link,
            "source": Websites.query.filter_by(id=article.website_id).first().name,
        }

    discussion_tree = {
        "title": title,
        "post": processed_content,
        "profile_pic": profile_pic,
        "image": image,
        "shared_from": (
            -1
            if posts[0].shared_from == -1
            else (
                posts[0].shared_from,
                db.session.query(User_mgmt)
                .join(Post, User_mgmt.id == Post.user_id)
                .filter(Post.id == posts[0].shared_from)
                .first()
                .username,
            )
        ),
        "post_id": posts[0].id,
        "author": user.username,
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

        # Process comment content for Reddit-style display
        comment_title, comment_content = process_reddit_post(post.tweet)
        processed_comment = augment_text(comment_content) if comment_content else ""

        # Get article for comment (if any)
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
        data = {
            "title": comment_title,
            "post": processed_comment,
            "post_id": post.id,
            "author": user.username,
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
        reverse_map[post.id] = parent

        if parent != -1:
            if parent in post_to_child:
                post_to_child[parent].append(post.id)
                post_to_child[post.id] = []
                post_to_data[post.id] = data

    tree = __expand_tree(post_to_child, post_to_data)
    discussion_tree = tree[root]
    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.id)

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
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

    return render_template(
        "reddit/thread.html",
        thread=discussion_tree,
        profile_pic=profile_pic,
        user_id=current_user.id,
        username=current_user.username,
        logged_username=current_user.username,
        logged_id=int(current_user.id),
        str=str,
        bool=bool,
        enumerate=enumerate,
        trending_ht=trending_ht,
        len=len,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


@main.get("/rfeed")
@login_required
def feeed_logged_reddit():
    """
    Display Reddit-style feed for logged-in users.

    Returns:
        Redirect to Reddit feed with default parameters
    """
    user_id = "all"  # Show all posts including user's own posts
    return redirect(f"/feed/{user_id}/feed/rf/1")


@main.get("/rfeed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>")
@login_required
def feed_reddit(user_id="all", timeline="timeline", mode="rf", page=1):
    """Handle feed reddit operation."""
    if page < 1:
        page = 1

    max_post_per_page = 10
    username = ""
    posts, additional = None, None

    feed_type = request.args.get("feed_type", "new")

    print("HERE", feed_type)

    if user_id == "all":
        if feed_type == "top":
            # Top: all time, by upvotes - downvotes
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
            # Fallback to slow subquery version or remove this option for now
            posts = (
                Post.query.filter_by(comment_to=-1)
                .order_by(desc(Post.id))
                .paginate(page=page, per_page=max_post_per_page, error_out=False)
            )
            additional = None
        else:
            # New: enforce reverse chronological order
            posts = (
                Post.query.filter_by(comment_to=-1)
                .order_by(desc(Post.id))
                .paginate(page=page, per_page=max_post_per_page, error_out=False)
            )
            additional = None

    elif user_id != "all":
        user = User_mgmt.query.filter_by(id=int(user_id)).first()
        recsys = user.recsys_type
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

    if posts is not None:
        res = __get_discussions(posts, username, page)
    if additional is not None:
        res_additional = __get_discussions(additional, username, page)

    # combine the posts and additional posts
    if len(res_additional) > 0:
        for add in res_additional:
            res.append(add)

    # not enough posts to display
    if len(res) == 0 and page > 1:
        return redirect(f"/rfeed/{user_id}/{timeline}/{mode}/{page - 1}")

    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.id)
    sfollow = get_suggested_users(user_id, pages=False)
    spages = get_suggested_users(user_id, pages=True)

    # get user profile pic
    if user_id != "all":
        user = User_mgmt.query.filter_by(id=user_id).first()
    else:
        user = User_mgmt.query.filter_by(id=current_user.id).first()

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

    return render_template(
        "reddit/feed.html",
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
        logged_id=current_user.id,
        trending_ht=trending_ht,
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        sfollow=sfollow,
        spages=spages,
        feed_type=feed_type,
    )
