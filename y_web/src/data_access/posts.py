"""
Post-centric data-access helpers.

Provides functions for retrieving, enriching, and filtering posts, including
augmenting post text with HTML links, fetching elicited emotions, topic
sentiment, and unanswered @-mentions.
"""

from sqlalchemy import desc

from y_web import db
from y_web.models import (
    Admin_users,
    Agent,
    Articles,
    Emotions,
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
    from y_web.utils.text_utils import extract_components, strip_tags  # noqa: PLC0415

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
    from y_web.models import Hashtags  # local import avoids circular-import risk

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
            name = Interests.query.filter_by(iid=topic.topic_id).first().interest
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
                    ).first()
                    is None,
                    "is_shared": len(Post.query.filter_by(shared_from=c.id).all()),
                    "emotions": emotions,
                    "topics": get_topics(post.thread_id, post.user_id),
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
                        Reactions.query.filter_by(
                            post_id=post.id, type="dislike"
                        ).all()
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
                    "emotions": emotions,
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
                        Reactions.query.filter_by(
                            post_id=post.id, type="dislike"
                        ).all()
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
                    "emotions": emotions,
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
                        Reactions.query.filter_by(
                            post_id=post.id, type="dislike"
                        ).all()
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
                        Reactions.query.filter_by(
                            post_id=post.id, type="dislike"
                        ).all()
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
            }
        )

    return res
