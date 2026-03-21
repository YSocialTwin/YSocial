"""
Common interaction routes (follow, share, react, delete, cancel_notification).

These routes are shared across both microblogging and forum platforms.
"""

import uuid

from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.models import (
    Follow,
    Mentions,
    Post,
    Post_topics,
    Reactions,
    Rounds,
    User_mgmt,
)

from y_web.routes.interactions._blueprint import user


@user.route(
    "/<int:exp_id>/follow/<int:user_id>/<int:follower_id>", methods=["GET", "POST"]
)
@login_required
def follow(exp_id, user_id, follower_id):
    """
    Handle follow/unfollow action between users.

    Toggles follow relationship and creates appropriate Follow record.

    Args:
        user_id: ID of user to follow/unfollow
        follower_id: ID of user performing the action

    Returns:
        Redirect to referrer page
    """
    # get the last round id from Rounds
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    # Handle both int and UUID follower_id (Standard vs HPC experiments)
    try:
        follower_id_converted = int(follower_id)
    except (ValueError, TypeError):
        follower_id_converted = follower_id

    # check
    followed = (
        Follow.query.filter_by(user_id=user_id, follower_id=follower_id_converted)
        .order_by(Follow.id.desc())
        .first()
    )

    if followed:
        if followed.action == "follow":
            try:
                new_follow = Follow(
                    follower_id=follower_id,
                    user_id=user_id,
                    action="unfollow",
                    round=current_round.id,
                )
                db.session.add(new_follow)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                new_follow = Follow(
                    id=str(uuid.uuid4()),
                    follower_id=follower_id,
                    user_id=user_id,
                    action="unfollow",
                    round=current_round.id,
                )
                db.session.add(new_follow)
                db.session.commit()
            return redirect(request.referrer)

    # add the user to the Follow table
    try:
        new_follow = Follow(
            follower_id=follower_id,
            user_id=user_id,
            action="follow",
            round=current_round.id,
        )
        db.session.add(new_follow)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        new_follow = Follow(
            id=str(uuid.uuid4()),
            follower_id=follower_id,
            user_id=user_id,
            action="follow",
            round=current_round.id,
        )
        db.session.add(new_follow)
        db.session.commit()

    return redirect(request.referrer)


@user.route("/<int:exp_id>/share_content")
@login_required
def share_content(exp_id):
    """
    Share/retweet an existing post.

    Creates a new post that references the original as a shared post.

    Query params:
        post_id: ID of post to share

    Returns:
        Redirect to referrer page
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

    post_id = request.args.get("post_id")

    # get the post
    original = Post.query.filter_by(id=post_id).first()
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    try:
        post = Post(
            tweet=original.tweet,
            round=current_round.id,
            user_id=exp_user_id,
            comment_to=-1,
            shared_from=post_id,
            image_id=original.image_id,
            news_id=original.news_id,
            post_img=original.post_img,
        )

        db.session.add(post)
        db.session.commit()
    except:
        post = Post(
            id=str(uuid.uuid4()),
            tweet=original.tweet,
            round=current_round.id,
            user_id=exp_user_id,
            comment_to=-1,
            shared_from=post_id,
            image_id=original.image_id,
            news_id=original.news_id,
            post_img=original.post_img,
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


@user.route("/<int:exp_id>/react_to_content")
@login_required
def react(exp_id):
    """Handle react operation."""
    post_id = request.args.get("post_id")
    action = request.args.get("action")

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

    current_round = Rounds.query.order_by(Rounds.id.desc()).first()

    record = Reactions.query.filter_by(
        post_id=post_id, user_id=exp_user_id, round=current_round.id
    ).first()

    if record:
        if record.type == action:
            return {"message": "Reaction added successfully", "status": 200}
        else:
            record.type = action
            record.round = current_round.id
            db.session.commit()

    else:
        try:
            reaction = Reactions(
                post_id=post_id,
                user_id=exp_user_id,
                type=action,
                round=current_round.id,
            )

            db.session.add(reaction)
            db.session.commit()
        except:
            reaction = Reactions(
                id=str(uuid.uuid4()),
                post_id=post_id,
                user_id=exp_user_id,
                type=action,
                round=current_round.id,
            )

            db.session.add(reaction)
            db.session.commit()

    # update the reaction count of the post
    post = Post.query.filter_by(id=post_id).first()
    if post is not None:
        post.reaction_count += 1
        db.session.commit()

    return {"message": "Reaction added successfully", "status": 200}


@user.route("/<int:exp_id>/delete_post")
@login_required
def delete_post(exp_id):
    """Delete post."""
    post_id = request.args.get("post_id")

    # Handle both int and UUID post_id (Standard vs HPC experiments)
    try:
        post_id_converted = int(post_id)
    except (ValueError, TypeError):
        post_id_converted = post_id

    post = Post.query.get(post_id_converted)
    db.session.delete(post)
    db.session.commit()

    return {"message": "Reaction added successfully", "status": 200}


@user.route("/<int:exp_id>/cancel_notification")
@login_required
def cancel_notification(exp_id):
    """Handle cancel notification operation."""
    # Get experiment user (not admin user)
    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not exp_user:
        return {"message": "User not found in experiment", "status": 404}
    exp_user_id = exp_user.id

    pid = request.args.get("post_id")

    # check if the comment is to answer a mention
    mention = Mentions.query.filter_by(post_id=pid, user_id=exp_user_id).first()
    if mention:
        mention.answered = 1
        db.session.commit()

    return {"message": "Notification cancelled", "status": 200}
