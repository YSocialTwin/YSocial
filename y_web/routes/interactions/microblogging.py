"""
Microblogging interaction routes.

Contains the publish_post route for the Twitter-style (microblogging) platform.
"""

import uuid

from flask import flash, redirect, request
from flask_login import current_user, login_required

from y_web import db
from y_web.routes.interactions._blueprint import user
from y_web.src.content.text_utils import toxicity, vader_sentiment
from y_web.src.llm import Annotator, ContentAnnotator
from y_web.src.models import (
    Admin_users,
    Emotions,
    Hashtags,
    Images,
    Interests,
    Mentions,
    Post,
    Post_emotions,
    Post_hashtags,
    Post_Sentiment,
    Post_topics,
    Rounds,
    User_interest,
    User_mgmt,
)


@user.route("/<int:exp_id>/publish")
@login_required
def publish_post(exp_id):
    """
    Publish a new post from form submission.

    Returns:
        Redirect to referrer page after posting
    """
    text = request.args.get("post")
    url = request.args.get("url")

    # Get experiment user (not admin user)
    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not exp_user:
        flash("User not found in experiment", "error")
        return redirect(request.referrer)
    exp_user_id = exp_user.id

    user = Admin_users.query.filter_by(username=current_user.username).first()
    llm = user.llm if user.llm != "" else "llama3.2:latest"
    llm_url = user.llm_url if user.llm_url != "" else None

    img_id = None
    if url is not None and url != "":
        llm_v = "minicpm-v"
        image_annotator = Annotator(llm_v, llm_url=llm_url)
        annotation = image_annotator.annotate(url)

        img = Images.query.filter_by(url=url).first()
        if img is None:
            try:
                img = Images(url=url, description=annotation, article_id=-1)
                db.session.add(img)
                db.session.commit()
                img_id = img.id
            except Exception as e:
                db.session.rollback()
                img = Images(
                    id=str(uuid.uuid4()), url=url, description=annotation, article_id=-1
                )
                db.session.add(img)
                db.session.commit()
                img_id = img.id
        else:
            img_id = img.id

    # get the last round id from Rounds
    current_round = Rounds.query.order_by(Rounds.day.desc(), Rounds.hour.desc()).first()

    # add post to the db
    try:
        post = Post(
            tweet=text,
            round=current_round.id,
            user_id=exp_user_id,
            comment_to=-1,
            image_id=img_id,
        )
        db.session.add(post)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        post = Post(
            id=str(uuid.uuid4()),
            tweet=text,
            round=current_round.id,
            user_id=exp_user_id,
            comment_to=-1,
            image_id=img_id,
        )

        db.session.add(post)
        db.session.commit()

    post.thread_id = post.id
    db.session.commit()

    toxicity(text, current_user.username, post.id, db)
    sentiment = vader_sentiment(text)

    annotator = ContentAnnotator(llm=llm, llm_url=llm_url)
    emotions = annotator.annotate_emotions(text)
    hashtags = annotator.extract_components(text, c_type="hashtags")
    mentions = annotator.extract_components(text, c_type="mentions")
    topics = annotator.annotate_topics(text)

    for topic in topics:
        res = Interests.query.filter_by(interest=topic).first()
        if res is None:
            try:
                interest = Interests(interest=topic)
                db.session.add(interest)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                interest = Interests(iid=str(uuid.uuid4()), interest=topic)
                db.session.add(interest)
                db.session.commit()

            res = Interests.query.filter_by(interest=topic).first()

        topic_id = res.iid

        try:
            ui = User_interest(
                user_id=exp_user_id, interest_id=topic_id, round_id=current_round.id
            )
            db.session.add(ui)
            ti = Post_topics(post_id=post.id, topic_id=topic_id)
            db.session.add(ti)
            db.session.commit()

            post_sentiment = Post_Sentiment(
                post_id=post.id,
                user_id=exp_user_id,
                topic_id=topic_id,
                pos=sentiment["pos"],
                neg=sentiment["neg"],
                neu=sentiment["neu"],
                compound=sentiment["compound"],
                round=current_round.id,
            )
            db.session.add(post_sentiment)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            ui = User_interest(
                id=str(uuid.uuid4()),
                user_id=exp_user_id,
                interest_id=topic_id,
                round_id=current_round.id,
            )
            db.session.add(ui)
            ti = Post_topics(id=str(uuid.uuid4()), post_id=post.id, topic_id=topic_id)
            db.session.add(ti)
            db.session.commit()

            post_sentiment = Post_Sentiment(
                id=str(uuid.uuid4()),
                post_id=post.id,
                user_id=exp_user_id,
                topic_id=topic_id,
                pos=sentiment["pos"],
                neg=sentiment["neg"],
                neu=sentiment["neu"],
                compound=sentiment["compound"],
                round=current_round.id,
            )
            db.session.add(post_sentiment)
            db.session.commit()

    for emotion in emotions:
        if len(emotion) < 1:
            continue

        em = Emotions.query.filter_by(emotion=emotion).first()
        if em is not None:
            try:
                post_emotion = Post_emotions(post_id=post.id, emotion_id=em.id)
                db.session.add(post_emotion)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                post_emotion = Post_emotions(
                    id=str(uuid.uuid4()), post_id=post.id, emotion_id=em.id
                )
                db.session.add(post_emotion)
                db.session.commit()

    for tag in hashtags:
        if len(tag) < 4:
            continue

        ht = Hashtags.query.filter_by(hashtag=tag).first()
        if ht is None:
            try:
                ht = Hashtags(hashtag=tag)
                db.session.add(ht)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                ht = Hashtags(id=str(uuid.uuid4()), hashtag=tag)
                db.session.add(ht)
                db.session.commit()
            ht = Hashtags.query.filter_by(hashtag=tag).first()

        try:
            post_tag = Post_hashtags(post_id=post.id, hashtag_id=ht.id)
            db.session.add(post_tag)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            post_tag = Post_hashtags(
                id=str(uuid.uuid4()), post_id=post.id, hashtag_id=ht.id
            )
            db.session.add(post_tag)
            db.session.commit()

    for mention in mentions:
        if len(mention) < 1:
            continue

        us = User_mgmt.query.filter_by(username=mention.strip("@")).first()

        # existing user and not self
        if us is not None and us.id != exp_user_id:
            try:
                mn = Mentions(user_id=us.id, post_id=post.id, round=current_round.id)
                db.session.add(mn)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                mn = Mentions(
                    id=str(uuid.uuid4()),
                    user_id=us.id,
                    post_id=post.id,
                    round=current_round.id,
                )
                db.session.add(mn)
                db.session.commit()
        else:
            text = text.replace(mention, "")

            # update post
            post.tweet = text.lstrip().rstrip()
            db.session.commit()

    return {"message": "Published successfully", "status": 200}
