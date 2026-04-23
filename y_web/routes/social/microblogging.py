"""
Microblogging (Twitter-style) platform routes.

Routes: feeed_logged, feed, get_post_hashtags, get_post_interest,
        get_post_emotion, get_friends, get_thread, api_feed,
        api_hashtag_posts, api_interest_posts, api_emotion_posts,
        api_profile_posts.
"""

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.routes.social._blueprint import main
from y_web.routes.social.helpers import (
    _forum_logged_user,
    _get_discussions,
    build_thread_tree,
    get_adhoc_agent_badge,
    is_admin,
)
from y_web.src.data_access import (
    get_posts_associated_to_emotion,
    get_posts_associated_to_hashtags,
    get_posts_associated_to_interest,
    get_report_count,
    get_safe_profile_pic,
    get_trending_emotions,
    get_trending_hashtags,
    get_trending_topics,
    get_unanswered_mentions,
    get_user_friends,
    get_user_recent_posts,
)
from y_web.src.forum.service import (
    _format_display_time,
    _format_display_time_from_created_at,
)
from y_web.src.models import (
    Admin_users,
    Agent,
    Emotions,
    Exps,
    Hashtags,
    Images,
    Interests,
    Page,
    Post,
    Reactions,
    Rounds,
    User_mgmt,
)
from y_web.src.recsys import get_suggested_posts, get_suggested_users


def _build_friends_view_model(user_id, page, active_tab):
    followers, followees, number_followers, number_followees = get_user_friends(
        user_id, limit=12, page=page
    )

    profile_pic_follower = {}
    for f in followers:
        u = User_mgmt.query.filter_by(id=f["id"]).first()
        if u is None:
            continue
        if u.is_page == 1:
            pg = Page.query.filter_by(name=f["username"]).first()
            if pg is not None:
                profile_pic_follower[f["id"]] = pg.logo
        else:
            ag = Agent.query.filter_by(name=f["username"]).first()
            profile_pic_follower[f["id"]] = (
                ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
            )

    profile_pic_followee = {}
    for f in followees:
        u = User_mgmt.query.filter_by(id=f["id"]).first()
        if u is None:
            continue
        if u.is_page == 1:
            pg = Page.query.filter_by(name=f["username"]).first()
            if pg is not None:
                profile_pic_followee[f["id"]] = pg.logo
        else:
            ag = Agent.query.filter_by(name=f["username"]).first()
            profile_pic_followee[f["id"]] = (
                ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
            )

    active_cards = followers if active_tab == "followers" else followees
    active_total = number_followers if active_tab == "followers" else number_followees
    total_pages = max(1, (active_total + 11) // 12) if active_total else 1
    current_page = min(max(page, 1), total_pages)
    has_prev_page = current_page > 1
    has_next_page = current_page < total_pages
    page_start = ((current_page - 1) * 12) + 1 if active_total else 0
    page_end = min(current_page * 12, active_total) if active_total else 0

    return {
        "followers": followers,
        "followees": followees,
        "profile_pic_follower": profile_pic_follower,
        "profile_pic_followee": profile_pic_followee,
        "active_cards": active_cards,
        "active_total": active_total,
        "number_followers": number_followers,
        "number_followees": number_followees,
        "total_pages": total_pages,
        "page": current_page,
        "has_prev_page": has_prev_page,
        "has_next_page": has_next_page,
        "page_start": page_start,
        "page_end": page_end,
        "active_tab": active_tab,
    }


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
    from y_web.src.experiment.context import get_db_bind_key_for_exp

    bind_key = get_db_bind_key_for_exp(exp.idexp)

    # Query User_mgmt from experiment database
    user_id = current_user.id  # fallback to admin ID
    try:
        # Use the experiment's database bind
        from y_web import db
        from y_web.src.models import User_mgmt

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
        res = _get_discussions(posts, username, page, exp_id, exp_user_id)
    if additional is not None:
        res_additional = _get_discussions(
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
        "microblogging/feed.html",
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
        "microblogging/hashtag.html",
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
        "microblogging/interest.html",
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
        "microblogging/emotions.html",
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
    active_tab = (
        str(request.args.get("tab", "followers") or "followers").strip().lower()
    )
    if active_tab not in {"followers", "followees"}:
        active_tab = "followers"

    view_model = _build_friends_view_model(user_id, page, active_tab)
    mentions = get_unanswered_mentions(current_user.id)

    cu = User_mgmt.query.filter_by(username=current_user.username).first()
    viewed_user = User_mgmt.query.filter_by(id=user_id).first()

    profile_pic = (
        get_safe_profile_pic(cu.username, getattr(cu, "is_page", 0) or 0) if cu else ""
    )

    logged_id = cu.id if cu else current_user.id
    viewed_profile_pic = (
        get_safe_profile_pic(
            viewed_user.username, getattr(viewed_user, "is_page", 0) or 0
        )
        if viewed_user
        else ""
    )
    viewed_username = viewed_user.username if viewed_user else str(user_id)

    return render_template(
        "microblogging/friends.html",
        followers=view_model["followers"],
        profile_pic=profile_pic,
        profile_pic_follower=view_model["profile_pic_follower"],
        followees=view_model["followees"],
        profile_pic_followee=view_model["profile_pic_followee"],
        page=view_model["page"],
        exp_id=exp_id,
        username=cu.username if cu else current_user.username,
        viewed_username=viewed_username,
        viewed_profile_pic=viewed_profile_pic,
        enumerate=enumerate,
        len=len,
        logged_username=cu.username if cu else current_user.username,
        logged_id=logged_id,
        user_id=user_id,
        active_tab=view_model["active_tab"],
        active_cards=view_model["active_cards"],
        active_total=view_model["active_total"],
        total_pages=view_model["total_pages"],
        has_prev_page=view_model["has_prev_page"],
        has_next_page=view_model["has_next_page"],
        page_start=view_model["page_start"],
        page_end=view_model["page_end"],
        number_followers=view_model["number_followers"],
        number_followees=view_model["number_followees"],
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


@main.get("/<int:exp_id>/api/friends/<user_id>/<int:page>")
@login_required
def api_friends(exp_id, user_id, page=1):
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        pass

    active_tab = (
        str(request.args.get("tab", "followers") or "followers").strip().lower()
    )
    if active_tab not in {"followers", "followees"}:
        active_tab = "followers"

    view_model = _build_friends_view_model(user_id, page, active_tab)
    html = render_template(
        "microblogging/components/friends_panel.html",
        exp_id=exp_id,
        user_id=user_id,
        active_tab=view_model["active_tab"],
        active_cards=view_model["active_cards"],
        active_total=view_model["active_total"],
        page=view_model["page"],
        total_pages=view_model["total_pages"],
        has_prev_page=view_model["has_prev_page"],
        has_next_page=view_model["has_next_page"],
        page_start=view_model["page_start"],
        page_end=view_model["page_end"],
        number_followers=view_model["number_followers"],
        number_followees=view_model["number_followees"],
        profile_pic_follower=view_model["profile_pic_follower"],
        profile_pic_followee=view_model["profile_pic_followee"],
    )
    return jsonify(
        {
            "html": html,
            "page": view_model["page"],
            "total_pages": view_model["total_pages"],
            "active_tab": view_model["active_tab"],
        }
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

    requested_post = Post.query.filter_by(id=post_id).first()
    if not requested_post:
        flash("Post not found", "error")
        return redirect(url_for("main.index"))

    thread_root_id = getattr(requested_post, "thread_id", None) or requested_post.id
    root_post = Post.query.filter_by(id=thread_root_id).first() or requested_post
    thread_root_id = root_post.id

    # Get all comments with this thread_id
    comment_posts = (
        Post.query.filter(Post.thread_id == thread_root_id, Post.id != thread_root_id)
        .order_by(Post.created_at.asc(), Post.id.asc())
        .all()
    )

    root = root_post.id

    c = Rounds.query.filter_by(id=root_post.round).first()
    if c is None:
        day = "None"
        hour = "00"
    else:
        day = c.day
        hour = c.hour

    root_display_time = _format_display_time_from_created_at(
        getattr(root_post, "created_at", None)
    ) or _format_display_time(
        str(day),
        f"{int(hour):02d}" if str(hour).isdigit() else str(hour),
    )

    image = Images.query.filter_by(id=root_post.image_id).first()

    user = User_mgmt.query.filter_by(id=root_post.user_id).first()
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
    if root_post.shared_from in (-1, "-1", None, ""):
        shared_from_info = -1
    else:
        shared_user = (
            db.session.query(User_mgmt)
            .join(Post, User_mgmt.id == Post.user_id)
            .filter(Post.id == root_post.shared_from)
            .first()
        )
        shared_from_info = (
            (root_post.shared_from, shared_user.username)
            if shared_user
            else (root_post.shared_from, "Unknown")
        )

    from y_web.src.data_access import augment_text, get_elicited_emotions, get_topics

    discussion_tree = {
        "post": augment_text(root_post.tweet, exp_id),
        "profile_pic": profile_pic,
        "image": image,
        "shared_from": shared_from_info,
        "post_id": root_post.id,
        "author": user.username,
        "author_id": root_post.user_id,
        "day": day,
        "hour": hour,
        "display_time": root_display_time,
        "children": [],
        "likes": len(
            list(Reactions.query.filter_by(post_id=root_post.id, type="like").all())
        ),
        "dislikes": len(
            list(Reactions.query.filter_by(post_id=root_post.id, type="dislike").all())
        ),
        "is_liked": Reactions.query.filter_by(
            post_id=root_post.id, user_id=exp_user_id, type="like"
        ).first()
        is None,
        "is_disliked": Reactions.query.filter_by(
            post_id=root_post.id, user_id=exp_user_id, type="dislike"
        ).first()
        is None,
        "is_shared": len(Post.query.filter_by(shared_from=root_post.id).all()),
        "report_count": get_report_count(root_post.id),
        "emotions": get_elicited_emotions(root_post.id),
        "topics": get_topics(root_post.id, root_post.user_id),
        "adhoc_agent_badge": get_adhoc_agent_badge(user),
        "is_moderation_comment": int(
            getattr(root_post, "is_moderation_comment", 0) or 0
        ),
    }

    parent_lookup = {root_post.id: None}
    post_to_data = {root_post.id: discussion_tree}

    for post in comment_posts:
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
            "display_time": display_time,
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
            "report_count": get_report_count(post.id),
            "emotions": get_elicited_emotions(post.id),
            "topics": get_topics(post.id, post.user_id),
            "adhoc_agent_badge": get_adhoc_agent_badge(user),
            "is_moderation_comment": int(
                getattr(post, "is_moderation_comment", 0) or 0
            ),
        }

        parent = post.comment_to
        parent_lookup[post.id] = parent
        post_to_data[post.id] = data

    discussion_tree = build_thread_tree(root, post_to_data, parent_lookup)
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
        "microblogging/thread.html",
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
    render_user_id = current_user.id
    posts, additional = None, None

    if user_id == "all":
        posts, additional = get_suggested_posts("all", "", page, max_post_per_page)
    elif user_id != "all":
        user = User_mgmt.query.filter_by(id=user_id).first()
        if not user:
            user = User_mgmt.query.filter_by(username=current_user.username).first()
        if not user:
            return jsonify({"html": "", "has_more": False}), 404
        render_user_id = user.id
        recsys = user.recsys_type
        posts, additional = get_suggested_posts(
            user.id, recsys, page, max_post_per_page
        )
        username = user.username

    res, res_additional = [], []

    # Get experiment user ID for reactions
    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    exp_user_id = exp_user.id if exp_user else current_user.id

    if posts is not None:
        res = _get_discussions(posts, username, page, exp_id, exp_user_id)
    if additional is not None:
        res_additional = _get_discussions(
            additional, username, page, exp_id, exp_user_id
        )

    # combine the posts and additional posts
    if len(res_additional) > 0:
        for add in res_additional:
            res.append(add)

    has_more = bool(
        (posts is not None and getattr(posts, "has_next", False))
        or (additional is not None and getattr(additional, "has_next", False))
    )

    html = render_template(
        "microblogging/components/posts.html",
        items=res,
        enumerate=enumerate,
        user_id=render_user_id,
        str=str,
        bool=bool,
        len=len,
    )
    return jsonify({"html": html, "has_more": has_more})


@main.get("/<int:exp_id>/api/hashtag_posts/<hashtag_id>/<int:page>")
@login_required
def api_hashtag_posts(exp_id, hashtag_id, page=1):
    """
    API endpoint for infinite scrolling in hashtag posts.

    Returns rendered HTML for posts.
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
    html = render_template(
        "microblogging/components/posts.html",
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
    API endpoint for infinite scrolling in interest posts.

    Returns rendered HTML for posts.
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
    html = render_template(
        "microblogging/components/posts.html",
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
    API endpoint for infinite scrolling in emotion posts.

    Returns rendered HTML for posts.
    """
    # Handle both int and UUID emotion_id formats (Standard vs HPC experiments)
    try:
        emotion_id = int(emotion_id)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass
    res = get_posts_associated_to_emotion(
        emotion_id,
        page,
        per_page=10,
        current_user=current_user.id,
        exp_id=exp_id,
    )
    html = render_template(
        "microblogging/components/posts.html",
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
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if getattr(exp, "platform_type", "") == "forum":
        logged_user = _forum_logged_user()
        html = render_template(
            "forum/components/posts.html",
            items=rp,
            enumerate=enumerate,
            user_id=(logged_user.id if logged_user else current_user.id),
            logged_id=(logged_user.id if logged_user else current_user.id),
            is_admin=is_admin(current_user.username),
            profile_delete_inline=True,
            str=str,
            bool=bool,
            len=len,
            exp_id=exp_id,
        )
    else:
        html = render_template(
            "microblogging/components/posts.html",
            items=rp,
            enumerate=enumerate,
            user_id=user_id,
            str=str,
            bool=bool,
            len=len,
        )
    return jsonify({"html": html, "has_more": len(rp) > 0})
