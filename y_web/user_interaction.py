from flask import Blueprint, redirect
from flask_login import login_required, current_user
from . import db
from .models import (
    Follow,
    Rounds,
    Post,
    Hashtags,
    Post_hashtags,
    Emotions,
    Post_emotions,
    Mentions,
    User_mgmt,
    Interests,
    User_interest,
    Post_topics,
    Reactions,
    Admin_users,
    Images,
    Post_Sentiment
)
from flask import request
from .llm_annotations import ContentAnnotator, Annotator
from .utils.text_utils import vader_sentiment

user = Blueprint("user_actions", __name__)


@user.route("/follow/<int:user_id>/<int:follower_id>", methods=["GET", "POST"])
@login_required
def follow(user_id, follower_id):
    # get the last round id from Rounds
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    # check
    followed = (
        Follow.query.filter_by(user_id=user_id, follower_id=int(follower_id))
        .order_by(Follow.id.desc())
        .first()
    )

    if followed:
        if followed.action == "follow":
            new_follow = Follow(
                follower_id=follower_id,
                user_id=user_id,
                action="unfollow",
                round=current_round.id,
            )
            db.session.add(new_follow)
            db.session.commit()
            return redirect(request.referrer)

    # add the user to the Follow table
    new_follow = Follow(
        follower_id=follower_id,
        user_id=user_id,
        action="follow",
        round=current_round.id,
    )
    db.session.add(new_follow)
    db.session.commit()

    return redirect(request.referrer)


@user.route("/share_content")
@login_required
def share_content():
    post_id = request.args.get("post_id")

    # get the post
    original = Post.query.filter_by(id=post_id).first()
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    post = Post(
        tweet=original.tweet,
        round=current_round.id,
        user_id=current_user.id,
        comment_to=-1,
        shared_from=post_id,
        image_id = original.image_id,
        news_id = original.news_id,
        post_img = original.post_img
    )

    db.session.add(post)
    db.session.commit()

    # get topics of the original post
    topics_id = Post_topics.query.filter_by(post_id=post_id).all()
    # add the topics to the shared post
    for t in topics_id:
        ti = Post_topics(post_id=post.id, topic_id=t.topic_id)
        db.session.add(ti)
        db.session.commit()

    return redirect(request.referrer)


@user.route("/react_to_content")
@login_required
def react():
    post_id = request.args.get("post_id")
    action = request.args.get("action")

    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    record = Reactions.query.filter_by(
        post_id=post_id, user_id=current_user.id, round=current_round.id
    ).first()

    if record:
        if record.type == action:
            return {"message": "Reaction added successfully", "status": 200}
        else:
            record.type = action
            record.round = current_round.id
            db.session.commit()

    else:
        reaction = Reactions(
            post_id=post_id,
            user_id=current_user.id,
            type=action,
            round=current_round.id,
        )

        db.session.add(reaction)
        db.session.commit()

    return {"message": "Reaction added successfully", "status": 200}


@user.route("/publish")
@login_required
def publish_post():
    text = request.args.get("post")
    url = request.args.get("url")

    img_id = None
    if url is not None and url != "":

        llm_v = "minicpm-v"
        image_annotator = Annotator(llm_v)
        annotation = image_annotator.annotate(url)

        img = Images.query.filter_by(url=url).first()
        if img is None:
            img = Images(url=url, description=annotation, article_id=-1)
            db.session.add(img)
            db.session.commit()
            img_id = img.id
        else:
            img_id = img.id

    # get the last round id from Rounds
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    # add post to the db
    post = Post(
        tweet=text,
        round=current_round.id,
        user_id=current_user.id,
        comment_to=-1,
        image_id = img_id,
    )

    db.session.add(post)
    db.session.commit()

    post.thread_id = post.id
    db.session.commit()

    sentiment = vader_sentiment(text)
    post_sentiment = Post_Sentiment(
        post_id=post.id,
        user_id=current_user.id,
        pos=sentiment["pos"],
        neg=sentiment["neg"],
        neu=sentiment["neu"],
        compound=sentiment["compound"],
        round=current_round.id
    )
    db.session.add(post_sentiment)
    db.session.commit()

    user = Admin_users.query.filter_by(username=current_user.username).first()
    llm = user.llm if user.llm != "" else "llama3.2:latest"

    annotator = ContentAnnotator(llm=llm)
    emotions = annotator.annotate_emotions(text)
    hashtags = annotator.extract_components(text, c_type="hashtags")
    mentions = annotator.extract_components(text, c_type="mentions")
    topics = annotator.annotate_topics(text)

    for topic in topics:
        res = Interests.query.filter_by(interest=topic).first()
        if res is None:
            interest = Interests(interest=topic)
            db.session.add(interest)
            db.session.commit()
            res = Interests.query.filter_by(interest=topic).first()

        topic_id = res.iid

        ui = User_interest(
            user_id=current_user.id, interest_id=topic_id, round_id=current_round.id
        )
        db.session.add(ui)
        ti = Post_topics(post_id=post.id, topic_id=topic_id)
        db.session.add(ti)
        db.session.commit()

    for emotion in emotions:
        if len(emotion) < 1:
            continue

        em = Emotions.query.filter_by(emotion=emotion).first()
        if em is not None:
            post_emotion = Post_emotions(post_id=post.id, emotion_id=em.id)
            db.session.add(post_emotion)
            db.session.commit()

    for tag in hashtags:
        if len(tag) < 4:
            continue

        ht = Hashtags.query.filter_by(hashtag=tag).first()
        if ht is None:
            ht = Hashtags(hashtag=tag)
            db.session.add(ht)
            db.session.commit()
            ht = Hashtags.query.filter_by(hashtag=tag).first()

        post_tag = Post_hashtags(post_id=post.id, hashtag_id=ht.id)
        db.session.add(post_tag)
        db.session.commit()

    for mention in mentions:
        if len(mention) < 1:
            continue

        us = User_mgmt.query.filter_by(username=mention.strip("@")).first()

        # existing user and not self
        if us is not None and us.id != current_user.id:
            mn = Mentions(user_id=us.id, post_id=post.id, round=current_round.id)
            db.session.add(mn)
            db.session.commit()
        else:
            text = text.replace(mention, "")

            # update post
            post.tweet = text.lstrip().rstrip()
            db.session.commit()

    return {"message": "Published successfully", "status": 200}


@user.route("/publish_comment")
@login_required
def publish_comment():
    text = request.args.get("post")
    pid = request.args.get("parent")

    # get the last round id from Rounds
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    # get the thread if of the post with id pid
    thread_id = Post.query.filter_by(id=pid).first().thread_id

    # add post to the db
    post = Post(
        tweet=text,
        round=current_round.id,
        user_id=current_user.id,
        comment_to=pid,
        thread_id=thread_id,
    )

    db.session.add(post)
    db.session.commit()

    # get sentiment of the post is responding to
    sentiment_root = Post_Sentiment.query.filter_by(post_id=pid).first()
    values = {"pos": sentiment_root.pos, "neg": sentiment_root.neg, "neu": sentiment_root.neu}
    # get the key with the max value
    sentiment_parent = max(values, key=values.get)

    sentiment = vader_sentiment(text)
    post_sentiment = Post_Sentiment(
        post_id=post.id,
        user_id=current_user.id,
        pos=sentiment["pos"],
        neg=sentiment["neg"],
        neu=sentiment["neu"],
        compound=sentiment["compound"],
        sentiment_parent=sentiment_parent,
        round=current_round.id
    )
    db.session.add(post_sentiment)
    db.session.commit()

    # check if the comment is to answer a mention
    mention = Mentions.query.filter_by(post_id=pid, user_id=current_user.id).first()
    if mention:
        mention.answered = 1
        db.session.commit()

    user = Admin_users.query.filter_by(username=current_user.username).first()
    llm = user.llm if user.llm != "" else "llama3.1"

    annotator = ContentAnnotator(llm=llm)
    emotions = annotator.annotate_emotions(text)
    hashtags = annotator.extract_components(text, c_type="hashtags")
    mentions = annotator.extract_components(text, c_type="mentions")

    topics_id = Post_topics.query.filter_by(post_id=thread_id).all()
    topics_id = [t.topic_id for t in topics_id]

    if len(topics_id) > 0:
        for t in topics_id:
            ui = User_interest(
                user_id=current_user.id, interest_id=t, round_id=current_round.id
            )
            db.session.add(ui)
            ti = Post_topics(post_id=post.id, topic_id=t)
            db.session.add(ti)
            db.session.commit()

    for emotion in emotions:
        if len(emotion) < 1:
            continue

        em = Emotions.query.filter_by(emotion=emotion).first()
        if em is not None:
            post_emotion = Post_emotions(post_id=post.id, emotion_id=em.id)
            db.session.add(post_emotion)
            db.session.commit()

    for tag in hashtags:
        if len(tag) < 4:
            continue

        ht = Hashtags.query.filter_by(hashtag=tag).first()
        if ht is None:
            ht = Hashtags(hashtag=tag)
            db.session.add(ht)
            db.session.commit()
            ht = Hashtags.query.filter_by(hashtag=tag).first()

        post_tag = Post_hashtags(post_id=post.id, hashtag_id=ht.id)
        db.session.add(post_tag)
        db.session.commit()

    for mention in mentions:
        if len(mention) < 1:
            continue

        us = User_mgmt.query.filter_by(username=mention.strip("@")).first()

        # existing user and not self
        #@todo: check gosth mentions to the current user...
        if us is not None and us.id != current_user.id:
            mn = Mentions(user_id=us.id, post_id=post.id, round=current_round.id)
            db.session.add(mn)
            db.session.commit()
        else:
            text = text.replace(mention, "")

            # update post
            post.tweet = text.lstrip().rstrip()
            db.session.commit()

    return {"message": "Published successfully", "status": 200}


@user.route("/delete_post")
@login_required
def delete_post():
    post_id = request.args.get("post_id")

    post = Post.query.get(int(post_id))
    db.session.delete(post)
    db.session.commit()

    return {"message": "Reaction added successfully", "status": 200}


@user.route("/cancel_notification")
@login_required
def cancel_notification():
    pid = request.args.get("post_id")

    # check if the comment is to answer a mention
    mention = Mentions.query.filter_by(post_id=pid, user_id=current_user.id).first()
    if mention:
        mention.answered = 1
        db.session.commit()

    return {"message": "Notification cancelled", "status": 200}
