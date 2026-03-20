"""
Forum interaction routes.

Contains publish_post_reddit and publish_comment routes for the forum
(Reddit-style) platform.
"""

import uuid

from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.llm_annotations import Annotator, ContentAnnotator
from y_web.models import (
    Admin_users,
    Articles,
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
    Websites,
)
from y_web.utils.article_extractor import extract_article_info
from y_web.utils.text_utils import toxicity, vader_sentiment

from y_web.routes.interactions._blueprint import user


@user.route("/<int:exp_id>/publish_reddit")
@login_required
def publish_post_reddit(exp_id):
    """
    Publish a new Reddit-style post with title and content.

    Returns:
        Redirect to referrer page after posting
    """
    text = request.args.get("post")
    url = request.args.get("url")

    user = Admin_users.query.filter_by(username=current_user.username).first()
    llm = user.llm if user.llm != "" else "llama3.2:latest"
    llm_url = user.llm_url if user.llm_url != "" else None

    # Get experiment user (not admin user)
    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not exp_user:
        flash("User not found in experiment", "error")
        return redirect(request.referrer)
    exp_user_id = exp_user.id

    # Normalize URL: prepend http:// if missing
    if url and not url.lower().startswith(("http://", "https://")):
        url = "http://" + url

    img_id = None
    if url is not None and url != "":
        # Check if URL is likely an image based on extension
        image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg")
        is_image_url = url.lower().endswith(image_extensions)

        if is_image_url:
            try:
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
                            id=str(uuid.uuid4()),
                            url=url,
                            description=annotation,
                            article_id=-1,
                        )
                        db.session.add(img)
                        db.session.commit()
                        img_id = img.id
                else:
                    img_id = img.id
            except Exception as e:
                db.session.rollback()
                print(f"Error processing image URL {url}: {e}")
                # Continue without image processing
                pass
        else:
            # For non-image URLs, store as article reference without image annotation
            pass

    # get the last round id from Rounds
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    # Handle article URL storage
    news_id = None
    if (
        url is not None
        and url != ""
        and not url.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg")
        )
    ):
        # Check if article already exists
        existing_article = Articles.query.filter_by(link=url).first()
        if existing_article:
            news_id = existing_article.id
        else:
            # Extract article information from URL
            import time

            article_info = extract_article_info(url)

            # Get or create website entry
            website = Websites.query.filter_by(name=article_info["source"]).first()
            if not website:
                try:
                    website = Websites(
                        name=article_info["source"],
                        rss="",
                        leaning="neutral",
                        category="user_shared",
                        last_fetched=int(time.time()),
                        language="en",
                        country="us",
                    )
                    db.session.add(website)
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    website = Websites(
                        id=str(uuid.uuid4()),
                        name=article_info["source"],
                        rss="",
                        leaning="neutral",
                        category="user_shared",
                        last_fetched=int(time.time()),
                        language="en",
                        country="us",
                    )
                    db.session.add(website)
                    db.session.commit()

            # Create article entry with extracted information
            try:
                article = Articles(
                    title=article_info["title"],
                    summary=article_info["summary"],
                    website_id=website.id,
                    link=url,
                    fetched_on=int(time.time()),
                )
                db.session.add(article)
                db.session.commit()
                news_id = article.id
            except Exception as e:
                db.session.rollback()
                article = Articles(
                    id=str(uuid.uuid4()),
                    title=article_info["title"],
                    summary=article_info["summary"],
                    website_id=website.id,
                    link=url,
                    fetched_on=int(time.time()),
                )
                db.session.add(article)
                db.session.commit()
                news_id = article.id

    # add post to the db
    try:
        post = Post(
            tweet=text,
            round=current_round.id,
            user_id=exp_user_id,
            comment_to=-1,
            image_id=img_id,
            news_id=news_id,
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
            news_id=news_id,
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
            ti = Post_topics(post_id=post.id, topic_id=topic_id)
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


@user.route("/<int:exp_id>/publish_comment")
@login_required
def publish_comment(exp_id):
    """
    Publish a comment on a post from form submission.

    Returns:
        Redirect to thread page after commenting
    """
    # Get experiment user (not admin user)
    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not exp_user:
        flash("User not found in experiment", "error")
        return (
            redirect(request.referrer)
            if request.referrer
            else redirect(url_for("main.index"))
        )
    exp_user_id = exp_user.id

    text = request.args.get("post")
    pid = request.args.get("parent")

    # Handle both int and UUID parent ID formats (Standard vs HPC experiments)
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        # Keep as string if it's a UUID
        pass

    # get the last round id from Rounds
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    # get the thread if of the post with id pid
    parent_post = Post.query.filter_by(id=pid).first()
    if not parent_post:
        flash("Parent post not found", "error")
        return (
            redirect(request.referrer)
            if request.referrer
            else redirect(url_for("main.index"))
        )
    thread_id = parent_post.thread_id if parent_post.thread_id else parent_post.id

    # If parent post has no thread_id, update it to use its own ID
    # This ensures queries for thread_id = post.id will find all comments
    if not parent_post.thread_id:
        parent_post.thread_id = parent_post.id
        db.session.commit()

    try:
        # add post to the db
        post = Post(
            tweet=text,
            round=current_round.id,
            user_id=exp_user_id,
            comment_to=pid,
            thread_id=thread_id,
        )

        db.session.add(post)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        uid = str(uuid.uuid4())
        # add post to the db
        post = Post(
            id=uid,
            tweet=text,
            round=current_round.id,
            user_id=exp_user_id,
            comment_to=pid,
            thread_id=thread_id,
        )

        db.session.add(post)
        db.session.commit()

    # get sentiment of the post is responding to
    sentiment_root = Post_Sentiment.query.filter_by(post_id=pid).first()

    if sentiment_root is not None:
        values = {
            "pos": sentiment_root.pos,
            "neg": sentiment_root.neg,
            "neu": sentiment_root.neu,
        }
        # get the key with the max value
    else:
        values = {"neu": 1}

    sentiment_parent = max(values, key=values.get)
    sentiment = vader_sentiment(text)

    toxicity(text, current_user.username, post.id, db)

    # check if the comment is to answer a mention
    mention = Mentions.query.filter_by(post_id=pid, user_id=exp_user_id).first()
    if mention:
        mention.answered = 1
        db.session.commit()

    user = Admin_users.query.filter_by(username=current_user.username).first()
    llm = user.llm if user.llm != "" else "llama3.1"
    llm_url = user.llm_url if user.llm_url != "" else None

    annotator = ContentAnnotator(llm=llm, llm_url=llm_url)
    emotions = annotator.annotate_emotions(text)
    hashtags = annotator.extract_components(text, c_type="hashtags")
    mentions = annotator.extract_components(text, c_type="mentions")

    topics_id = Post_topics.query.filter_by(post_id=thread_id).all()
    topics_id = [t.topic_id for t in topics_id]

    if len(topics_id) > 0:
        for t in topics_id:
            try:
                ui = User_interest(
                    user_id=exp_user_id, interest_id=t, round_id=current_round.id
                )
                db.session.add(ui)
                ti = Post_topics(post_id=post.id, topic_id=t)
                db.session.add(ti)
                db.session.commit()

                post_sentiment = Post_Sentiment(
                    post_id=post.id,
                    user_id=exp_user_id,
                    topic_id=t,
                    pos=sentiment["pos"],
                    neg=sentiment["neg"],
                    neu=sentiment["neu"],
                    compound=sentiment["compound"],
                    sentiment_parent=sentiment_parent,
                    round=current_round.id,
                )
                db.session.add(post_sentiment)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                ui = User_interest(
                    id=str(uuid.uuid4()),
                    user_id=exp_user_id,
                    interest_id=t,
                    round_id=current_round.id,
                )
                db.session.add(ui)
                ti = Post_topics(id=str(uuid.uuid4()), post_id=post.id, topic_id=t)
                db.session.add(ti)
                db.session.commit()

                post_sentiment = Post_Sentiment(
                    id=str(uuid.uuid4()),
                    post_id=post.id,
                    user_id=exp_user_id,
                    topic_id=t,
                    pos=sentiment["pos"],
                    neg=sentiment["neg"],
                    neu=sentiment["neu"],
                    compound=sentiment["compound"],
                    sentiment_parent=sentiment_parent,
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
        # @todo: check ghost mentions to the current user...
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
