"""
Forum (Reddit-style) platform routes.

Routes: interview, get_thread_reddit, feeed_logged_reddit,
        rnotifications_logged, rnotifications, rfeed_redirect,
        feed_reddit, search_reddit, api_feed_reddit.
"""

from urllib.parse import urlencode

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc
from sqlalchemy.sql.expression import func

from y_web import db
from y_web.src.data_access import (
    augment_text,
    get_elicited_emotions,
    get_topics,
    get_trending_hashtags,
    get_unanswered_mentions,
)
from y_web.src.models import (
    Admin_users,
    Agent,
    Articles,
    Exps,
    Images,
    Page,
    Post,
    Reactions,
    ReplyInboxState,
    Rounds,
    User_mgmt,
    Websites,
)
from y_web.src.recsys import get_suggested_users
from y_web.src.forum.service import (
    _format_display_time,
    _format_display_time_from_created_at,
    fetch_feed_page,
)
from y_web.routes.social._blueprint import main
from y_web.routes.social.helpers import (
    _expand_tree,
    _experiment_memory_enabled,
    _forum_current_profile_pic,
    _forum_logged_user,
    _forum_memory_enabled,
    _forum_profile_pic,
    _forum_resolve_back_url,
    _get_discussions,
    is_admin,
)
from y_web.src.content.text_utils import process_reddit_post, strip_tags


@main.get("/<int:exp_id>/interview")
@login_required
def interview(exp_id):
    admin_user = Admin_users.query.filter_by(username=current_user.username).first()
    if not admin_user or admin_user.role not in {"admin", "researcher"}:
        abort(403)

    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp:
        abort(404)
    platform_type = str(getattr(exp, "platform_type", "") or "")
    if platform_type not in {"forum", "microblogging"}:
        abort(404)
    if not _experiment_memory_enabled(exp_id):
        flash(
            "Interview is unavailable because memory is disabled for this experiment."
        )
        if platform_type == "forum":
            return redirect(f"/{exp_id}/rfeed/all/feed/rf/1?feed_type=new")
        exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
        feed_user_id = exp_user.id if exp_user else "all"
        return redirect(f"/{exp_id}/feed/{feed_user_id}/feed/rf/1")

    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    logged_id = (
        int(exp_user.id) if exp_user else int(getattr(current_user, "id", 0) or 0)
    )

    mentions = []
    try:
        mentions = get_unanswered_mentions(logged_id)
    except Exception:
        mentions = []

    if platform_type == "forum":
        return render_template(
            "forum/interview.html",
            logged_username=current_user.username,
            logged_id=logged_id,
            profile_pic=_forum_current_profile_pic(exp_id, _forum_logged_user()),
            mentions=mentions,
            is_admin=is_admin(current_user.username),
            exp_id=exp_id,
            forum_memory_enabled=True,
        )

    profile_pic = ""
    try:
        ag = Agent.query.filter_by(name=current_user.username).first()
        if ag is not None and ag.profile_pic is not None:
            profile_pic = ag.profile_pic
        else:
            admin = Admin_users.query.filter_by(username=current_user.username).first()
            profile_pic = admin.profile_pic if admin else ""
    except Exception:
        profile_pic = ""

    return render_template(
        "microblogging/interview.html",
        logged_username=current_user.username,
        logged_id=logged_id,
        profile_pic=profile_pic,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        exp_id=exp_id,
        experiment_memory_enabled=True,
        len=len,
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
    root_display_time = _format_display_time_from_created_at(
        getattr(posts[0], "created_at", None)
    ) or _format_display_time(
        str(day),
        f"{int(hour):02d}" if str(hour).isdigit() else str(hour),
    )

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
        "display_time": root_display_time,
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
        display_time = _format_display_time_from_created_at(
            getattr(post, "created_at", None)
        ) or _format_display_time(
            str(day),
            f"{int(hour):02d}" if str(hour).isdigit() else str(hour),
        )

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
            "display_time": display_time,
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

    tree = _expand_tree(post_to_child, post_to_data)
    discussion_tree = tree[root]
    trending_ht = get_trending_hashtags()
    logged_user = _forum_logged_user()
    mention_user_id = logged_user.id if logged_user is not None else None
    mentions = get_unanswered_mentions(mention_user_id) if mention_user_id else []

    return render_template(
        "forum/thread.html",
        thread=discussion_tree,
        profile_pic=_forum_current_profile_pic(exp_id, logged_user),
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
        forum_memory_enabled=_forum_memory_enabled(exp_id),
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
            "forum/notifications.html",
            items=[],
            page=page,
            has_more=False,
            unread_before_open=0,
            profile_pic=_forum_current_profile_pic(exp_id, logged_user),
            logged_username=current_user.username,
            logged_id=current_user.id,
            mentions=[],
            is_admin=is_admin(current_user.username),
            exp_id=exp_id,
            forum_memory_enabled=_forum_memory_enabled(exp_id),
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
        "forum/notifications.html",
        items=items,
        page=page,
        has_more=has_more,
        unread_before_open=unread_before_open,
        profile_pic=_forum_current_profile_pic(exp_id, logged_user),
        logged_username=current_user.username,
        logged_id=exp_user_id,
        mentions=get_unanswered_mentions(exp_user_id),
        is_admin=is_admin(current_user.username),
        exp_id=exp_id,
        forum_memory_enabled=_forum_memory_enabled(exp_id),
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

    profile_pic = _forum_current_profile_pic(exp_id, logged_user)
    profile_pic_feed = _forum_current_profile_pic(exp_id, logged_user)

    return render_template(
        "forum/feed.html",
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
        forum_memory_enabled=_forum_memory_enabled(exp_id),
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
        "forum/feed.html",
        items=res,
        page=current_page,
        profile_pic=_forum_current_profile_pic(exp_id, logged_user),
        profile_pic_feed=_forum_current_profile_pic(exp_id, logged_user),
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
        forum_memory_enabled=_forum_memory_enabled(exp_id),
    )


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
        res = _get_discussions(posts, username, page, exp_id, exp_user_id)
    if additional is not None:
        res_additional = _get_discussions(
            additional, username, page, exp_id, exp_user_id
        )

    # combine the posts and additional posts
    if len(res_additional) > 0:
        for add in res_additional:
            res.append(add)

    html = render_template(
        "forum/components/posts.html",
        items=res,
        enumerate=enumerate,
        user_id=user_id if user_id != "all" else current_user.id,
        str=str,
        bool=bool,
        len=len,
    )
    return jsonify({"html": html, "has_more": len(res) > 0})
