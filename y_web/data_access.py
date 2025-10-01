from .models import (
    Post,
    Post_hashtags,
    Mentions,
    Emotions,
    Post_emotions,
    Reactions,
    Follow,
    Articles,
    Websites,
    Rounds,
    Interests,
    User_interest,
    Post_topics,
    Images,
    Page,
    Agent,
    Post_Sentiment,
)
from sqlalchemy.sql.expression import func
from sqlalchemy import desc
from y_web.utils.text_utils import *
from y_web import db


def get_safe_profile_pic(username, is_page=0):
    """
    Safely get profile picture for a user with fallbacks
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


def get_user_recent_posts(user_id, page, per_page=10, mode="rf", current_user=None):
    """

    :param db:
    :param user_id:
    :param page:
    :param per_page:
    :param mode:
    :param current_user:
    :return:
    """

    if page < 1:
        page = 1

    username = User_mgmt.query.filter_by(id=int(user_id)).first().username
    if mode == "recent":
        posts = (
            Post.query.filter_by(user_id=int(user_id), comment_to=-1).order_by(
                desc(Post.id)
            )
        ).paginate(page=page, per_page=per_page, error_out=False)
    elif mode == "comments":
        posts = (
            Post.query.filter(
                Post.user_id == int(user_id), Post.comment_to != -1
            ).order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)

    elif mode == "liked":
        # get posts liked by the user
        posts = (
            Post.query.join(Reactions, Reactions.post_id == Post.id)
            .filter(Reactions.type == "like", Reactions.user_id == int(user_id))
            .order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)

    elif mode == "disliked":
        posts = (
            Post.query.join(Reactions, Reactions.post_id == Post.id)
            .filter(Reactions.type == "dislike", Reactions.user_id == int(user_id))
            .order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)

    elif mode == "shares":
        # get all posts of user_id having shared_from is not -1
        posts = (
            Post.query.filter(
                Post.user_id == int(user_id), Post.shared_from != -1
            ).order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)

    else:
        # get the user posts with the most reactions
        posts = (
            Post.query.filter_by(user_id=int(user_id), comment_to=-1)
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

            # get elicited emotions names
            emotions = get_elicited_emotions(c.id)

            if username == author:
                text = c.tweet.split(":")[-1].replace(f"@{username}", "")
            else:
                text = c.tweet.split(":")[-1]

            user = User_mgmt.query.filter_by(username=author).first()
            # is the agent a page?
            profile_pic = ""
            if user.is_page == 1:
                page = Page.query.filter_by(name=user.username).first()
                if page is not None:
                    profile_pic = page.logo
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
                    "shared_from": -1
                    if c.shared_from == -1
                    else (
                        c.shared_from,
                        db.session.query(User_mgmt)
                        .join(Post, User_mgmt.id == Post.user_id)
                        .filter(Post.id == c.shared_from)
                        .first()
                        .username,
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
                    ).first()
                    is None,
                    "is_shared": len(Post.query.filter_by(shared_from=c.id).all()),
                    "emotions": emotions,
                    "topics": get_topics(post.thread_id, int(post.user_id)),
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

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        # get elicited emotions names

        emotions = get_elicited_emotions(post.id)
        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        # is the agent a page?
        author = User_mgmt.query.filter_by(id=post.user_id).first()

        profile_pic = ""
        if author.is_page == 1:
            page = Page.query.filter_by(name=author.username).first()
            if page is not None:
                profile_pic = page.logo
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
                "shared_from": -1
                if post.shared_from == -1
                else (
                    post.shared_from,
                    db.session.query(User_mgmt)
                    .join(Post, User_mgmt.id == Post.user_id)
                    .filter(Post.id == post.shared_from)
                    .first()
                    .username,
                ),
                "post_id": post.id,
                "profile_pic": profile_pic,
                "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
                "author_id": int(post.user_id),
                "post": augment_text(post.tweet.split(":")[-1]),
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
                "topics": get_topics(post.id, int(post.user_id)),
            }
        )

    return res


def augment_text(text):
    """
    Augment the text by adding links to the mentions and hashtags.

    :param text: the text to augment
    :return: the augmented text
    """
    # text = text.split("(")[0]

    # Extract the mentions and hashtags
    mentions = extract_components(text, c_type="mentions")
    hashtags = extract_components(text, c_type="hashtags")

    # Define the dictionary to store the mentioned users and used hashtags
    mentioned_users = {}
    used_hastag = {}

    # Get the mentioned user id
    for m in mentions:
        try:
            mentioned_users[m] = User_mgmt.query.filter_by(username=m[1:]).first().id
        except:
            pass

    # Get the used hashtag id
    for h in hashtags:
        try:
            used_hastag[h] = Hashtags.query.filter_by(hashtag=h).first().id
        except:
            pass

    # Replace the mentions and hashtags with the links
    for m, uid in mentioned_users.items():
        text = text.replace(m, f'<a href="/profile/{uid}/recent/1"> {m} </a>')

    for h, hid in used_hastag.items():
        text = text.replace(h, f'<a href="/hashtag_posts/{hid}/1"> {h} </a>')

    # remove first character it is a space
    if len(text) > 0:
        if text[0] == " ":
            text = text[1:]

        # capitalize the first letter of the text
        text = text[0].upper() + text[1:]

    return text


def get_mutual_friends(user_a, user_b, limit=10):
    """
    Get the mutual friends between two users.
    :param user_a:
    :param user_b:
    :param limit:
    :return:
    """
    # Get the friends of the two users
    friends_a = Follow.query.filter_by(user_id=user_a, action="follow").distinct()
    friends_b = Follow.query.filter_by(user_id=user_b, action="follow").distinct()

    # Get the mutual friends
    mutual_friends = []
    for f_a in friends_a:
        for f_b in friends_b:
            if f_a.follower_id == f_b.follower_id:
                mutual_friends.append(f_a.follower_id)

    res = []
    added = {}
    for uid in mutual_friends[:limit]:
        user = User_mgmt.query.filter_by(id=uid).first()
        profile_pic = ""
        if user.is_page == 1:
            page = Page.query.filter_by(name=user.username).first()
            if page is not None:
                profile_pic = page.logo

        else:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=user.username)
                .first()
                .profile_pic
            )

        if user.id not in added:
            res.append(
                {"id": user.id, "username": user.username, "profile_pic": profile_pic}
            )
            added[user.id] = None

    return res


def get_top_user_hashtags(user_id, limit=10):
    ht = (
        Post.query.filter_by(user_id=user_id)
        .join(Post_hashtags, Post.id == Post_hashtags.post_id)
        .join(Hashtags, Post_hashtags.hashtag_id == Hashtags.id)
        .with_entities(Hashtags.id, Hashtags.hashtag, func.count(Post_hashtags.hashtag_id).label("count"))
        .group_by(Hashtags.id, Hashtags.hashtag)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )

    ht = [
        {"id": h[0], "hashtag": h[1], "count": h[2]}
        for h in ht
    ]

    return ht


def get_user_friends(user_id, limit=12, page=1):
    """
    Get the followers and followees of the user with pagination.

    :param user_id: int
    :param limit: int - items per page
    :param page: int - current page number
    :return: (followers_list, followee_list, total_followers, total_followees)
    """
    if page < 1:
        page = 1

    # Conta totale followees (user_id segue follower_id) con conteggio dispari
    number_followees = (
        db.session.query(Follow.follower_id)
        .filter(Follow.user_id == user_id, Follow.follower_id != user_id)
        .group_by(Follow.follower_id)
        .having(func.count(Follow.follower_id) % 2 == 1)
        .count()
    )

    # Conta totale followers (follower_id segue user_id) con conteggio dispari
    number_followers = (
        db.session.query(Follow.user_id)
        .filter(Follow.follower_id == user_id, Follow.user_id != user_id)
        .group_by(Follow.user_id)
        .having(func.count(Follow.user_id) % 2 == 1)
        .count()
    )

    followee_list = []
    followers_list = []

    # Controllo pagine per evitare out of range
    if (number_followers - page * limit < -limit) and (number_followees - page * limit < -limit):
        return get_user_friends(user_id, limit=limit, page=page - 1)

    # Recupera followees con join e group_by corretto
    if page * limit <= number_followees + limit:
        followee_query = (
            db.session.query(Follow.follower_id, User_mgmt.username, User_mgmt.id)
            .filter(Follow.user_id == user_id, Follow.follower_id != user_id)
            .join(User_mgmt, Follow.follower_id == User_mgmt.id)
            .group_by(Follow.follower_id, User_mgmt.username, User_mgmt.id)
            .having(func.count(Follow.follower_id) % 2 == 1)
            .paginate(page=page, per_page=limit, error_out=False)
        )

        for f in followee_query.items:
            uid_f = f.id
            followee_list.append(
                {
                    "id": uid_f,
                    "username": f.username,
                    "number_reactions": Reactions.query.filter_by(user_id=uid_f).count(),
                    "number_followers": (
                        db.session.query(Follow.user_id)
                        .filter(Follow.follower_id == uid_f, Follow.user_id != uid_f)
                        .group_by(Follow.user_id)
                        .having(func.count(Follow.user_id) % 2 == 1)
                        .count()
                    ),
                    "number_followees": (
                        db.session.query(Follow.follower_id)
                        .filter(Follow.user_id == uid_f, Follow.follower_id != uid_f)
                        .group_by(Follow.follower_id)
                        .having(func.count(Follow.follower_id) % 2 == 1)
                        .count()
                    ),
                }
            )

    # Recupera followers con join e group_by corretto
    if page * limit <= number_followers + limit:
        followers_query = (
            db.session.query(Follow.user_id, User_mgmt.username, User_mgmt.id)
            .filter(Follow.follower_id == user_id, Follow.user_id != user_id)
            .join(User_mgmt, Follow.user_id == User_mgmt.id)
            .group_by(Follow.user_id, User_mgmt.username, User_mgmt.id)
            .having(func.count(Follow.user_id) % 2 == 1)
            .paginate(page=page, per_page=limit, error_out=False)
        )

        for f in followers_query.items:
            uid_f = f.id
            followers_list.append(
                {
                    "id": uid_f,
                    "username": f.username,
                    "number_reactions": Reactions.query.filter_by(user_id=uid_f).count(),
                    "number_followers": (
                        db.session.query(Follow.user_id)
                        .filter(Follow.follower_id == uid_f, Follow.user_id != uid_f)
                        .group_by(Follow.user_id)
                        .having(func.count(Follow.user_id) % 2 == 1)
                        .count()
                    ),
                    "number_followees": (
                        db.session.query(Follow.follower_id)
                        .filter(Follow.user_id == uid_f, Follow.follower_id != uid_f)
                        .group_by(Follow.follower_id)
                        .having(func.count(Follow.follower_id) % 2 == 1)
                        .count()
                    ),
                }
            )

    return followers_list, followee_list, number_followers, number_followees


def get_trending_emotions(limit=10, window=120):
    """
    Get the trending emotions.
    :param window:
    :param limit:
    :return:
    """

    # get current round
    last_round_obj = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round = last_round_obj.id if last_round_obj else 0

    # get the trending emotions
    em = (
        db.session.query(
            Emotions.id,
            Emotions.emotion,
            func.count(Post_emotions.emotion_id).label("count")
        )
        .join(Post_emotions, Post_emotions.emotion_id == Emotions.id)
        .join(Post, Post.id == Post_emotions.post_id)
        .filter(Post.round >= last_round - window)
        .group_by(Emotions.id, Emotions.emotion)
        .order_by(desc("count"))
        .limit(limit)
    ).all()

    # format result
    em = [{"emotion": e[1], "count": e[2], "id": e[0]} for e in em]

    return em


def get_trending_hashtags(limit=10, window=120):
    """
    Get the trending hashtags.
    :param limit:
    :return:
    """

    # get current round

    last_round_obj = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round = last_round_obj.id if last_round_obj else 0

    ht = (
        db.session.query(
            Hashtags.id,
            Hashtags.hashtag,
            func.count(Post_hashtags.hashtag_id).label("count")
        )
        .join(Post_hashtags, Post_hashtags.hashtag_id == Hashtags.id)
        .join(Post, Post.id == Post_hashtags.post_id)
        .filter(Post.round >= last_round - window)
        .group_by(Hashtags.id, Hashtags.hashtag)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )

    ht = [
        {
            "hashtag": h[1],
            "count": h[2],
            "id": h[0],
        }
        for h in ht
    ]

    return ht


def get_trending_topics(limit=10, window=120):
    # get current round
    last_round_obj = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round = last_round_obj.id if last_round_obj else 0

    # query trending topics
    tp = (
        db.session.query(
            Interests.iid,
            Interests.interest,
            func.count(Post_topics.topic_id).label("count")
        )
        .join(Post_topics, Post_topics.topic_id == Interests.iid)
        .join(Post, Post.id == Post_topics.post_id)
        .filter(Post.round >= last_round - window)
        .group_by(Interests.iid, Interests.interest)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )

    return [{"id": t[0], "topic": t[1], "count": t[2]} for t in tp]


def get_posts_associated_to_hashtags(hashtag_id, page, per_page=10, current_user=None):
    """
    Get the posts associated to the given hashtag.

    :param hashtag_id:
    :param page:
    :param per_page:
    :return:
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

            # get elicited emotions names

            emotions = get_elicited_emotions(c.id)

            # get author
            user = User_mgmt.query.filter_by(id=c.user_id).first()

            # is the agent a page?
            if user.is_page == 1:
                page = Page.query.filter_by(name=user.username).first()
                if page is not None:
                    profile_pic = page.logo
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
                    "shared_from": -1
                    if c.shared_from == -1
                    else (
                        c.shared_from,
                        db.session.query(User_mgmt)
                        .join(Post, User_mgmt.id == Post.user_id)
                        .filter(Post.id == c.shared_from)
                        .first()
                        .username,
                    ),
                    "author_id": int(c.user_id),
                    "post": augment_text(c.tweet.split(":")[-1]),
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
                "summary": strip_tags(article.summary),
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

        # get elicited emotions names

        emotions = get_elicited_emotions(post.id)

        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        # is the agent a page?
        author = User_mgmt.query.filter_by(id=post.user_id).first()

        if author.is_page == 1:
            page = Page.query.filter_by(name=author.username).first()
            if page is not None:
                profile_pic = page.logo
        else:
            # get agent profile pic
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
                "shared_from": -1
                if post.shared_from == -1
                else (
                    post.shared_from,
                    db.session.query(User_mgmt)
                    .join(Post, User_mgmt.id == Post.user_id)
                    .filter(Post.id == post.shared_from)
                    .first()
                    .username,
                ),
                "post_id": post.id,
                "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
                "author_id": int(post.user_id),
                "post": augment_text(post.tweet.split(":")[-1]),
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
                "topics": get_topics(post.id, int(post.user_id)),
            }
        )

    return res


def get_posts_associated_to_interest(interest_id, page, per_page=10, current_user=None):
    """
    Get the posts associated to the given interest.

    :param interest_id:
    :param page:
    :param per_page:
    :return:
    """

    if page < 1:
        page = 1

    # get posts associated to the topic
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

            # get elicited emotions names
            emotions = get_elicited_emotions(c.id)

            c_user = User_mgmt.query.filter_by(id=c.user_id).first()

            # is the agent a page?
            if c_user.is_page == 1:
                page = Page.query.filter_by(name=c_user.username).first()
                if page is not None:
                    profile_pic = page.logo
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
                    "shared_from": -1
                    if c.shared_from == -1
                    else (
                        c.shared_from,
                        db.session.query(User_mgmt)
                        .join(Post, User_mgmt.id == Post.user_id)
                        .filter(Post.id == c.shared_from)
                        .first()
                        .username,
                    ),
                    "author_id": int(c.user_id),
                    "post": augment_text(c.tweet.split(":")[-1]),
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
                "summary": strip_tags(article.summary),
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

        # is the agent a page?
        author = User_mgmt.query.filter_by(id=post.user_id).first()

        if author.is_page == 1:
            page = Page.query.filter_by(name=author.username).first()
            if page is not None:
                profile_pic = page.logo
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
                "shared_from": -1
                if post.shared_from == -1
                else (
                    post.shared_from,
                    db.session.query(User_mgmt)
                    .join(Post, User_mgmt.id == Post.user_id)
                    .filter(Post.id == post.shared_from)
                    .first()
                    .username,
                ),
                "post_id": post.id,
                "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
                "author_id": int(post.user_id),
                "post": augment_text(post.tweet.split(":")[-1]),
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
                "topics": get_topics(post.id, int(post.user_id)),
            }
        )

    return res


def get_posts_associated_to_emotion(emotion_id, page, per_page=10, current_user=None):
    """
    Get the posts associated to the given emotion.

    :param current_user:
    :param emotion_id:
    :param page:
    :param per_page:
    :return:
    """

    if page < 1:
        page = 1

    # get posts associated to the emotion
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

            # get elicited emotions names
            emotions = get_elicited_emotions(c.id)

            user = User_mgmt.query.filter_by(username=author).first()

            # is the agent a page?
            if user.is_page == 1:
                page = Page.query.filter_by(name=user.username).first()
                if page is not None:
                    profile_pic = page.logo
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
                    "shared_from": -1
                    if c.shared_from == -1
                    else (
                        c.shared_from,
                        db.session.query(User_mgmt)
                        .join(Post, User_mgmt.id == Post.user_id)
                        .filter(Post.id == c.shared_from)
                        .first()
                        .username,
                    ),
                    "author_id": int(c.user_id),
                    "post": augment_text(c.tweet.split(":")[-1]),
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
                "summary": strip_tags(article.summary),
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

        # is the agent a page?
        author = User_mgmt.query.filter_by(id=post.user_id).first()

        if author.is_page == 1:
            page = Page.query.filter_by(name=author.username).first()
            if page is not None:
                profile_pic = page.logo
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
                "shared_from": -1
                if post.shared_from == -1
                else (
                    post.shared_from,
                    db.session.query(User_mgmt)
                    .join(Post, User_mgmt.id == Post.user_id)
                    .filter(Post.id == post.shared_from)
                    .first()
                    .username,
                ),
                "post_id": post.id,
                "profile_pic": profile_pic,
                "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
                "author_id": int(post.user_id),
                "post": augment_text(post.tweet.split(":")[-1]),
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
                "topics": get_topics(post.id, int(post.user_id)),
            }
        )

    return res


def get_user_recent_interests(user_id, limit=5):
    last_round = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round_id = last_round.id if last_round else 0

    interests = (
        db.session.query(
            Interests.interest,
            User_interest.interest_id,
            func.count(User_interest.interest_id).label("count"),
        )
        .join(User_interest, Interests.iid == User_interest.interest_id)
        .filter(
            User_interest.user_id == user_id,
            User_interest.round_id >= last_round_id - 36,
        )
        .group_by(Interests.interest, User_interest.interest_id)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )

    # interests è lista di tuple (interest, interest_id, count)
    res = [(interest, interest_id, count) for interest, interest_id, count in interests]

    return res


def get_elicited_emotions(post_id):
    # get elicited emotions names
    emotions = (
        Post_emotions.query.filter_by(post_id=post_id)
        .join(Emotions, Post_emotions.emotion_id == Emotions.id)
        .add_columns(Emotions.emotion)
        .add_columns(Emotions.icon)
        .add_columns(Emotions.id)
    ).all()

    emotions = set([(e.emotion, e.icon, e.id) for e in emotions])
    return emotions


def get_topics(post_id, user_id):
    # get the topics of the post
    # topics = (
    #    Post.query.filter_by(id=post_id)
    #    .join(Post_topics, Post.id == Post_topics.post_id)
    #    .join(Post_Sentiment, Post.id == Post_Sentiment.post_id)
    #    .join(Interests, Post_topics.topic_id == Interests.iid)
    #    .add_columns(Interests.interest)
    #    .add_columns(Interests.iid)
    #    .add_columns(Post_Sentiment.compound)
    #    .add_columns(Post_Sentiment.is_reaction)
    #    .add_columns(Post_Sentiment.user_id)
    #    .all()
    # )
    post = Post.query.filter_by(id=post_id).first()
    if post.image_id is not None:
        return []

    sentiment = Post_Sentiment.query.filter_by(post_id=post_id, user_id=user_id).all()

    cleaned = {}
    for topic in sentiment:
        if topic.topic_id != -1:
            name = Interests.query.filter_by(iid=topic.topic_id).first().interest
            if topic.topic_id not in cleaned and topic.is_reaction == 0:
                # threshold the sentiment
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


def get_unanswered_mentions(user_id):
    """

    :param user_id:
    :return:
    """

    res = (
        Mentions.query.filter_by(user_id=user_id, answered=0)
        .join(Post, Post.id == Mentions.post_id)
        .join(User_mgmt, User_mgmt.id == Post.user_id)
        .add_columns(User_mgmt.username, Post.user_id, Post.tweet)
        .all()
    )

    return res
