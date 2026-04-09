"""
Post-centric data-access helpers.

Provides functions for retrieving, enriching, and filtering posts, including
augmenting post text with HTML links, fetching elicited emotions, topic
sentiment, and unanswered @-mentions.
"""

from sqlalchemy import desc

from y_web import db
from y_web.src.models import (
    Admin_users,
    Agent,
    Articles,
    Emotions,
    Exps,
    Images,
    Interests,
    Mentions,
    Page,
    Post,
    Post_emotions,
    Post_hashtags,
    Post_Sentiment,
    Post_topics,
    Reactions,
    Reported,
    Rounds,
    User_mgmt,
    Websites,
)

from .trends import _compute_last_round  # noqa: F401 — re-used by augment_text


def _get_text_utils():
    """Lazy loader for text_utils to avoid triggering faker at import time.

    y_web/utils/__init__.py re-exports agents.py which requires the optional
    ``faker`` package.  Deferring the import to call time means this module
    can be imported in environments where faker is not installed, matching the
    behaviour of the original y_web/data_access.py.
    """
    from y_web.src.content.text_utils import (  # noqa: PLC0415
        extract_components,
        strip_tags,
    )

    return extract_components, strip_tags


def _strip_tags(html):
    """Thin lazy wrapper around text_utils.strip_tags."""
    _, strip_tags = _get_text_utils()
    return strip_tags(html)


def augment_text(text, exp_id):
    """Augment post text by adding HTML links to @mentions and #hashtags.

    Args:
        text: Raw post text
        exp_id: Experiment ID used to build profile / hashtag URLs

    Returns:
        HTML-augmented text string
    """
    from y_web.src.models import Hashtags  # local import avoids circular-import risk

    extract_components, _ = _get_text_utils()

    text = text.strip('"')

    mentions = extract_components(text, c_type="mentions")
    hashtags = extract_components(text, c_type="hashtags")

    mentioned_users = {}
    used_hastag = {}

    for m in mentions:
        try:
            mentioned_users[m] = User_mgmt.query.filter_by(username=m[1:]).first().id
        except:
            pass

    for h in hashtags:
        try:
            hashtag_obj = Hashtags.query.filter_by(hashtag=h).first()
            if hashtag_obj:
                used_hastag[h] = hashtag_obj.id
            else:
                hashtag_obj = Hashtags.query.filter_by(hashtag=h[1:]).first()
                if hashtag_obj:
                    used_hastag[h] = hashtag_obj.id
        except:
            pass

    for m, uid in mentioned_users.items():
        text = text.replace(m, f'<a href="/{exp_id}/profile/{uid}/recent/1"> {m} </a>')

    for h, hid in used_hastag.items():
        text = text.replace(h, f'<a href="/{exp_id}/hashtag_posts/{hid}/1"> {h} </a>')

    if len(text) > 0:
        if text[0] == " ":
            text = text[1:]
        text = text[0].upper() + text[1:]

    return text


def get_elicited_emotions(post_id):
    """
    Get emotions elicited by a post.

    Args:
        post_id: ID of the post to get emotions for

    Returns:
        List of tuples containing (emotion_name, icon, emotion_id)
    """
    emotions = (
        Post_emotions.query.filter_by(post_id=post_id)
        .join(Emotions, Post_emotions.emotion_id == Emotions.id)
        .add_columns(Emotions.emotion)
        .add_columns(Emotions.icon)
        .add_columns(Emotions.id)
    ).all()

    return list(set([(e.emotion, e.icon, e.id) for e in emotions]))


def get_topics(post_id, user_id):
    """
    Get topics associated with a post and user sentiment.

    Args:
        post_id: ID of the post to get topics for
        user_id: ID of the user viewing the post

    Returns:
        List of topics with sentiment information
    """
    post = Post.query.filter_by(id=post_id).first()
    if post is None:
        return []
    if post.image_id is not None:
        return []

    sentiment = Post_Sentiment.query.filter_by(post_id=post_id, user_id=user_id).all()

    cleaned = {}
    for topic in sentiment:
        if topic.topic_id != -1:
            interest = Interests.query.filter_by(iid=topic.topic_id).first()
            if interest is None:
                continue
            name = interest.interest
            if topic.topic_id not in cleaned and topic.is_reaction == 0:
                if topic.compound > 0.05:
                    cleaned[topic.topic_id] = (
                        topic.topic_id,
                        name,
                        "positive",
                        topic.round,
                    )
                elif topic.compound < -0.05:
                    cleaned[topic.topic_id] = (
                        topic.topic_id,
                        name,
                        "negative",
                        topic.round,
                    )
                else:
                    cleaned[topic.topic_id] = (
                        topic.topic_id,
                        name,
                        "neutral",
                        topic.round,
                    )

    if not cleaned:
        post_topics = (
            Post_topics.query.filter_by(post_id=post_id)
            .join(Interests, Post_topics.topic_id == Interests.iid)
            .add_columns(Interests.interest)
            .all()
        )
        for topic, interest_name in post_topics:
            if topic.topic_id == -1 or topic.topic_id in cleaned:
                continue
            cleaned[topic.topic_id] = (
                topic.topic_id,
                interest_name,
                "neutral",
                getattr(post, "round", None),
            )

    return list(cleaned.values())


def get_unanswered_mentions(username):
    """
    Get unanswered @-mention notifications for a user.

    Args:
        username: Username to look up

    Returns:
        List of ORM row objects (Mentions joined with Post and User_mgmt)
    """
    user = User_mgmt.query.filter_by(username=username).first()
    if user is None:
        return []
    user_id = user.id

    return (
        Mentions.query.filter_by(user_id=user_id, answered=0)
        .join(Post, Post.id == Mentions.post_id)
        .join(User_mgmt, User_mgmt.id == Post.user_id)
        .add_columns(User_mgmt.username, Post.user_id, Post.tweet)
        .all()
    )


def get_report_count(post_id):
    """Return how many report records exist for a given post or comment."""
    return Reported.query.filter_by(to_post=post_id).count()


def get_user_recent_posts(
    user_id, page, per_page=10, mode="rf", current_user=None, exp_id=None
):
    """
    Retrieve paginated posts for a specific user based on filter mode.

    Args:
        user_id: ID of the user whose posts to retrieve
        page: Page number for pagination (1-indexed)
        per_page: Number of posts per page
        mode: Filter mode - "recent", "comments", "liked", "disliked", "shares", or "rf"
        current_user: Current user viewing the posts (for personalization)
        exp_id: Experiment ID for building augmented text links

    Returns:
        List of post dictionaries with metadata
    """
    from sqlalchemy.sql.expression import func

    if page < 1:
        page = 1

    exp = (
        Exps.query.filter_by(idexp=int(exp_id)).first() if exp_id is not None else None
    )
    is_forum = getattr(exp, "platform_type", "") == "forum"

    if is_forum:
        from y_web.src.content.text_utils import process_reddit_post  # noqa: PLC0415
        from y_web.src.forum.service import (  # noqa: PLC0415
            _format_display_time,
            _format_display_time_from_created_at,
            _resolve_article,
        )
        from y_web.src.forum.service.queries import (  # noqa: PLC0415
            _primary_community_payload,
        )

    user = User_mgmt.query.filter_by(id=user_id).first()
    username = user.username if user else "Unknown"

    if mode == "recent":
        posts = (
            Post.query.filter_by(user_id=user_id, comment_to=-1).order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)
    elif mode == "comments":
        posts = (
            Post.query.filter(Post.user_id == user_id, Post.comment_to != -1).order_by(
                desc(Post.id)
            )
        ).paginate(page=page, per_page=per_page, error_out=False)
    elif mode == "liked":
        posts = (
            Post.query.join(Reactions, Reactions.post_id == Post.id)
            .filter(Reactions.type == "like", Reactions.user_id == user_id)
            .order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)
    elif mode == "disliked":
        posts = (
            Post.query.join(Reactions, Reactions.post_id == Post.id)
            .filter(Reactions.type == "dislike", Reactions.user_id == user_id)
            .order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)
    elif mode == "shares":
        posts = (
            Post.query.filter(Post.user_id == user_id, Post.shared_from != -1).order_by(
                desc(Post.id)
            )
        ).paginate(page=page, per_page=per_page, error_out=False)
    else:
        posts = (
            Post.query.filter_by(user_id=user_id, comment_to=-1)
            .join(Reactions, Post.id == Reactions.post_id)
            .add_columns(func.count(Reactions.id).label("count"))
            .group_by(Post.id)
            .order_by(desc("count"))
        ).paginate(page=page, per_page=per_page, error_out=False)

    res = []

    for post in posts.items:
        if mode not in ["recent", "comments", "liked", "disliked", "shares"]:
            post = post[0]

        comments = (
            Post.query.filter_by(thread_id=post.id)
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username)
            .all()
        )

        cms = []
        idx = 0
        for c, author in comments:
            if idx == 0:
                idx = 1
                continue

            emotions = get_elicited_emotions(c.id)

            if username == author:
                text = c.tweet.split(":")[-1].replace(f"@{username}", "")
            else:
                text = c.tweet.split(":")[-1]

            user = User_mgmt.query.filter_by(username=author).first()
            profile_pic = ""
            if user.is_page == 1:
                pg = Page.query.filter_by(name=user.username).first()
                if pg is not None:
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

            comment_round = Rounds.query.filter_by(id=c.round).first()
            comment_day = comment_round.day if comment_round is not None else "None"
            comment_hour = comment_round.hour if comment_round is not None else "00"
            comment_display_time = (
                _format_display_time_from_created_at(getattr(c, "created_at", None))
                if is_forum
                else None
            ) or (
                _format_display_time(
                    str(comment_day),
                    (
                        f"{int(comment_hour):02d}"
                        if str(comment_hour).isdigit()
                        else str(comment_hour)
                    ),
                )
                if is_forum
                else None
            )
            comment_topics = get_topics(c.id, c.user_id)
            if len(comment_topics) == 0:
                comment_topics = []
            comment_title, comment_body = (
                process_reddit_post(c.tweet) if is_forum else ("", text)
            )
            processed_comment = (
                augment_text(comment_body, exp_id)
                if comment_body
                else augment_text(text, exp_id)
            )

            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
                    "profile_pic": profile_pic,
                    "shared_from": (
                        lambda: (
                            -1
                            if c.shared_from == -1
                            else (
                                lambda u: (
                                    (c.shared_from, u.username)
                                    if u
                                    else (c.shared_from, "Unknown")
                                )
                            )(
                                db.session.query(User_mgmt)
                                .join(Post, User_mgmt.id == Post.user_id)
                                .filter(Post.id == c.shared_from)
                                .first()
                            )
                        )
                    )(),
                    "author_id": c.user_id,
                    "title": comment_title if is_forum else "",
                    "post": processed_comment,
                    "round": c.round,
                    "day": comment_day,
                    "hour": comment_hour,
                    "display_time": comment_display_time if is_forum else None,
                    "likes": len(
                        list(Reactions.query.filter_by(post_id=c.id, type="like"))
                    ),
                    "dislikes": len(
                        list(Reactions.query.filter_by(post_id=c.id, type="dislike"))
                    ),
                    "is_liked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
                    ).first()
                    is None,
                    "is_shared": len(Post.query.filter_by(shared_from=c.id).all()),
                    "report_count": get_report_count(c.id),
                    "emotions": emotions,
                    "topics": comment_topics,
                    "is_moderation_comment": int(
                        getattr(c, "is_moderation_comment", 0) or 0
                    ),
                }
            )

        article = Articles.query.filter_by(id=post.news_id).first()
        if article is None:
            art = 0
            article_preview = None
        else:
            art = {
                "title": article.title,
                "summary": _strip_tags(article.summary),
                "url": article.link,
                "source": Websites.query.filter_by(id=article.website_id).first().name,
            }
            article_preview = _resolve_article(article) if is_forum else None

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour
        display_time = (
            _format_display_time_from_created_at(getattr(post, "created_at", None))
            if is_forum
            else None
        ) or (
            _format_display_time(
                str(day),
                f"{int(hour):02d}" if str(hour).isdigit() else str(hour),
            )
            if is_forum
            else None
        )

        emotions = get_elicited_emotions(post.id)
        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        author = User_mgmt.query.filter_by(id=post.user_id).first()

        profile_pic = ""
        if author.is_page == 1:
            pg = Page.query.filter_by(name=author.username).first()
            if pg is not None:
                profile_pic = pg.logo
        else:
            ag = Agent.query.filter_by(name=author.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=author.username)
                .first()
                .profile_pic
            )
        topics = get_topics(post.id, post.user_id)
        if len(topics) == 0:
            topics = []
        primary_community = (
            _primary_community_payload(article_preview, topics) if is_forum else None
        )
        title, post_body = (
            process_reddit_post(post.tweet)
            if is_forum
            else ("", post.tweet.split(":")[-1])
        )
        processed_post = augment_text(post_body, exp_id) if post_body else ""

        res.append(
            {
                "article": art,
                "image": image,
                "thread_id": post.thread_id,
                "shared_from": (
                    lambda: (
                        -1
                        if post.shared_from == -1
                        else (
                            lambda u: (
                                (post.shared_from, u.username)
                                if u
                                else (post.shared_from, "Unknown")
                            )
                        )(
                            db.session.query(User_mgmt)
                            .join(Post, User_mgmt.id == Post.user_id)
                            .filter(Post.id == post.shared_from)
                            .first()
                        )
                    )
                )(),
                "post_id": post.id,
                "profile_pic": profile_pic,
                "author": (lambda u: u.username if u else "Unknown")(
                    User_mgmt.query.filter_by(id=post.user_id).first()
                ),
                "author_id": post.user_id,
                "title": title if is_forum else "",
                "post": processed_post,
                "round": post.round,
                "day": day,
                "hour": hour,
                "display_time": display_time if is_forum else None,
                "created_at": (
                    getattr(post, "created_at", None).isoformat()
                    if getattr(post, "created_at", None)
                    else None
                ),
                "likes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="like").all())
                ),
                "dislikes": len(
                    list(
                        Reactions.query.filter_by(post_id=post.id, type="dislike").all()
                    )
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="dislike"
                ).first()
                is None,
                "is_shared": len(Post.query.filter_by(shared_from=post.id).all()),
                "report_count": get_report_count(post.id),
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
                "topics": topics,
                "is_moderation_comment": int(
                    getattr(post, "is_moderation_comment", 0) or 0
                ),
                "primary_community": primary_community,
            }
        )

    return res


def get_posts_associated_to_hashtags(
    hashtag_id, page, per_page=10, current_user=None, exp_id=None
):
    """Get the posts associated to the given hashtag.

    Args:
        hashtag_id: ID of the hashtag
        page: Page number for pagination (1-indexed)
        per_page: Number of posts per page (default: 10)
        current_user: Current user's ID for personalisation
        exp_id: Experiment ID for building augmented text links

    Returns:
        List of post dictionaries with metadata
    """
    if page < 1:
        page = 1

    posts = (
        Post.query.join(Post_hashtags, Post.id == Post_hashtags.post_id)
        .filter(Post_hashtags.hashtag_id == hashtag_id)
        .order_by(desc(Post.id))
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    res = []
    for post in posts.items:
        comments = (
            Post.query.filter_by(thread_id=post.id)
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username)
            .all()
        )

        cms = []
        idx = 0
        for c, author in comments:
            if idx == 0:
                idx = 1
                continue

            emotions = get_elicited_emotions(c.id)

            user = User_mgmt.query.filter_by(id=c.user_id).first()

            profile_pic = ""
            if user.is_page == 1:
                pg = Page.query.filter_by(name=user.username).first()
                if pg is not None:
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

            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
                    "profile_pic": profile_pic,
                    "shared_from": (
                        lambda: (
                            -1
                            if c.shared_from == -1
                            else (
                                lambda u: (
                                    (c.shared_from, u.username)
                                    if u
                                    else (c.shared_from, "Unknown")
                                )
                            )(
                                db.session.query(User_mgmt)
                                .join(Post, User_mgmt.id == Post.user_id)
                                .filter(Post.id == c.shared_from)
                                .first()
                            )
                        )
                    )(),
                    "author_id": c.user_id,
                    "post": augment_text(c.tweet.split(":")[-1], exp_id),
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
                    ).first()
                    is None,
                    "is_shared": len(Post.query.filter_by(shared_from=c.id).all()),
                    "report_count": get_report_count(c.id),
                    "emotions": emotions,
                    "topics": get_topics(c.id, c.user_id),
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
                "summary": _strip_tags(article.summary),
                "url": article.link,
                "source": Websites.query.filter_by(id=article.website_id).first().name,
            }

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        emotions = get_elicited_emotions(post.id)
        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        author = User_mgmt.query.filter_by(id=post.user_id).first()

        profile_pic = ""
        if author.is_page == 1:
            pg = Page.query.filter_by(name=author.username).first()
            if pg is not None:
                profile_pic = pg.logo
        else:
            ag = Agent.query.filter_by(name=author.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=author.username)
                .first()
                .profile_pic
            )

        res.append(
            {
                "article": art,
                "image": image,
                "profile_pic": profile_pic,
                "thread_id": post.thread_id,
                "shared_from": (
                    lambda: (
                        -1
                        if post.shared_from == -1
                        else (
                            lambda u: (
                                (post.shared_from, u.username)
                                if u
                                else (post.shared_from, "Unknown")
                            )
                        )(
                            db.session.query(User_mgmt)
                            .join(Post, User_mgmt.id == Post.user_id)
                            .filter(Post.id == post.shared_from)
                            .first()
                        )
                    )
                )(),
                "post_id": post.id,
                "author": (lambda u: u.username if u else "Unknown")(
                    User_mgmt.query.filter_by(id=post.user_id).first()
                ),
                "author_id": post.user_id,
                "post": augment_text(post.tweet.split(":")[-1], exp_id),
                "round": post.round,
                "day": day,
                "hour": hour,
                "likes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="like").all())
                ),
                "dislikes": len(
                    list(
                        Reactions.query.filter_by(post_id=post.id, type="dislike").all()
                    )
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="dislike"
                ).first()
                is None,
                "is_shared": len(Post.query.filter_by(shared_from=post.id).all()),
                "report_count": get_report_count(post.id),
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
                "topics": get_topics(post.id, post.user_id),
                "is_moderation_comment": int(
                    getattr(post, "is_moderation_comment", 0) or 0
                ),
            }
        )

    return res


def get_posts_associated_to_interest(
    interest_id, page, per_page=10, current_user=None, exp_id=None
):
    """Get the posts associated to the given interest/topic.

    Args:
        interest_id: ID of the interest/topic
        page: Page number for pagination (1-indexed)
        per_page: Number of posts per page (default: 10)
        current_user: Current user's ID for personalisation
        exp_id: Experiment ID for building augmented text links

    Returns:
        List of post dictionaries with metadata
    """
    if page < 1:
        page = 1

    posts = (
        Post.query.join(Post_topics, Post.id == Post_topics.post_id)
        .filter(Post_topics.topic_id == interest_id)
        .order_by(desc(Post.id))
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    res = []
    for post in posts.items:
        comments = (
            Post.query.filter_by(thread_id=post.id)
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username)
            .all()
        )

        cms = []
        idx = 0
        for c, author in comments:
            if idx == 0:
                idx = 1
                continue

            emotions = get_elicited_emotions(c.id)

            c_user = User_mgmt.query.filter_by(id=c.user_id).first()

            profile_pic = ""
            if c_user.is_page == 1:
                pg = Page.query.filter_by(name=c_user.username).first()
                if pg is not None:
                    profile_pic = pg.logo
            else:
                ag = Agent.query.filter_by(name=c_user.username).first()
                profile_pic = (
                    ag.profile_pic
                    if ag is not None and ag.profile_pic is not None
                    else Admin_users.query.filter_by(username=c_user.username)
                    .first()
                    .profile_pic
                )

            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
                    "profile_pic": profile_pic,
                    "shared_from": (
                        lambda: (
                            -1
                            if c.shared_from == -1
                            else (
                                lambda u: (
                                    (c.shared_from, u.username)
                                    if u
                                    else (c.shared_from, "Unknown")
                                )
                            )(
                                db.session.query(User_mgmt)
                                .join(Post, User_mgmt.id == Post.user_id)
                                .filter(Post.id == c.shared_from)
                                .first()
                            )
                        )
                    )(),
                    "author_id": c.user_id,
                    "post": augment_text(c.tweet.split(":")[-1], exp_id),
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
                    ).first()
                    is None,
                    "is_shared": len(Post.query.filter_by(shared_from=c.id).all()),
                    "report_count": get_report_count(c.id),
                    "emotions": emotions,
                    "topics": get_topics(c.id, c.user_id),
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
                "summary": _strip_tags(article.summary),
                "url": article.link,
                "source": Websites.query.filter_by(id=article.website_id).first().name,
            }

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        emotions = get_elicited_emotions(post.id)
        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        author = User_mgmt.query.filter_by(id=post.user_id).first()

        profile_pic = ""
        if author.is_page == 1:
            pg = Page.query.filter_by(name=author.username).first()
            if pg is not None:
                profile_pic = pg.logo
        else:
            ag = Agent.query.filter_by(name=author.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=author.username)
                .first()
                .profile_pic
            )

        res.append(
            {
                "article": art,
                "image": image,
                "profile_pic": profile_pic,
                "thread_id": post.thread_id,
                "shared_from": (
                    lambda: (
                        -1
                        if post.shared_from == -1
                        else (
                            lambda u: (
                                (post.shared_from, u.username)
                                if u
                                else (post.shared_from, "Unknown")
                            )
                        )(
                            db.session.query(User_mgmt)
                            .join(Post, User_mgmt.id == Post.user_id)
                            .filter(Post.id == post.shared_from)
                            .first()
                        )
                    )
                )(),
                "post_id": post.id,
                "author": (lambda u: u.username if u else "Unknown")(
                    User_mgmt.query.filter_by(id=post.user_id).first()
                ),
                "author_id": post.user_id,
                "post": augment_text(post.tweet.split(":")[-1], exp_id),
                "round": post.round,
                "day": day,
                "hour": hour,
                "likes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="like").all())
                ),
                "dislikes": len(
                    list(
                        Reactions.query.filter_by(post_id=post.id, type="dislike").all()
                    )
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="dislike"
                ).first()
                is None,
                "is_shared": len(Post.query.filter_by(shared_from=post.id).all()),
                "report_count": get_report_count(post.id),
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
                "topics": get_topics(post.id, post.user_id),
                "is_moderation_comment": int(
                    getattr(post, "is_moderation_comment", 0) or 0
                ),
            }
        )

    return res


def get_posts_associated_to_emotion(
    emotion_id, page, per_page=10, current_user=None, exp_id=None
):
    """Get the posts associated to the given emotion.

    Args:
        emotion_id: ID of the emotion
        page: Page number for pagination (1-indexed)
        per_page: Number of posts per page (default: 10)
        current_user: Current user's ID for personalisation
        exp_id: Experiment ID for building augmented text links

    Returns:
        List of post dictionaries with metadata
    """
    if page < 1:
        page = 1

    posts = (
        Post.query.join(Post_emotions, Post.id == Post_emotions.post_id)
        .filter(Post_emotions.emotion_id == emotion_id)
        .order_by(desc(Post.id))
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    res = []
    for post in posts.items:
        comments = (
            Post.query.filter_by(thread_id=post.id)
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username)
            .all()
        )

        cms = []
        idx = 0
        for c, author in comments:
            if idx == 0:
                idx = 1
                continue

            emotions = get_elicited_emotions(c.id)

            user = User_mgmt.query.filter_by(username=author).first()

            profile_pic = ""
            if user.is_page == 1:
                pg = Page.query.filter_by(name=user.username).first()
                if pg is not None:
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

            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
                    "profile_pic": profile_pic,
                    "shared_from": (
                        lambda: (
                            -1
                            if c.shared_from == -1
                            else (
                                lambda u: (
                                    (c.shared_from, u.username)
                                    if u
                                    else (c.shared_from, "Unknown")
                                )
                            )(
                                db.session.query(User_mgmt)
                                .join(Post, User_mgmt.id == Post.user_id)
                                .filter(Post.id == c.shared_from)
                                .first()
                            )
                        )
                    )(),
                    "author_id": c.user_id,
                    "post": augment_text(c.tweet.split(":")[-1], exp_id),
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
                    ).first()
                    is None,
                    "is_shared": len(Post.query.filter_by(shared_from=c.id).all()),
                    "emotions": emotions,
                    "topics": get_topics(c.id, c.user_id),
                    "report_count": get_report_count(c.id),
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
                "summary": _strip_tags(article.summary),
                "url": article.link,
                "source": Websites.query.filter_by(id=article.website_id).first().name,
            }

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        emotions = get_elicited_emotions(post.id)
        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        author = User_mgmt.query.filter_by(id=post.user_id).first()

        profile_pic = ""
        if author.is_page == 1:
            pg = Page.query.filter_by(name=author.username).first()
            if pg is not None:
                profile_pic = pg.logo
        else:
            ag = Agent.query.filter_by(name=author.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=author.username)
                .first()
                .profile_pic
            )

        res.append(
            {
                "article": art,
                "image": image,
                "thread_id": post.thread_id,
                "shared_from": (
                    lambda: (
                        -1
                        if post.shared_from == -1
                        else (
                            lambda u: (
                                (post.shared_from, u.username)
                                if u
                                else (post.shared_from, "Unknown")
                            )
                        )(
                            db.session.query(User_mgmt)
                            .join(Post, User_mgmt.id == Post.user_id)
                            .filter(Post.id == post.shared_from)
                            .first()
                        )
                    )
                )(),
                "post_id": post.id,
                "profile_pic": profile_pic,
                "author": (lambda u: u.username if u else "Unknown")(
                    User_mgmt.query.filter_by(id=post.user_id).first()
                ),
                "author_id": post.user_id,
                "post": augment_text(post.tweet.split(":")[-1], exp_id),
                "round": post.round,
                "day": day,
                "hour": hour,
                "likes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="like").all())
                ),
                "dislikes": len(
                    list(
                        Reactions.query.filter_by(post_id=post.id, type="dislike").all()
                    )
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="dislike"
                ).first()
                is None,
                "is_shared": len(Post.query.filter_by(shared_from=post.id).all()),
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
                "topics": get_topics(post.id, post.user_id),
                "is_moderation_comment": int(
                    getattr(post, "is_moderation_comment", 0) or 0
                ),
            }
        )

    return res
