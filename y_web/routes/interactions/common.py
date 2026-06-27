"""
Common interaction routes (follow, share, react, delete, cancel_notification).

These routes are shared across both microblogging and forum platforms.
"""

import uuid

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.routes.interactions._blueprint import user
from y_web.src.experiment.helpers import open_experiment_session
from y_web.src.models import (
    Follow,
    Mentions,
    Post,
    Post_topics,
    Reactions,
    Reported,
    Rounds,
    User_mgmt,
)


def _resolve_follow_round_id(exp_id):
    """
    Resolve a valid round id for follow/unfollow actions.

    Photo-sharing experiments may be executed with a separate experiment DB, so
    we prefer the latest round from that DB and only fall back to the shared
    bound query if needed.
    """
    try:
        from y_web.src.models import Exps

        exp = Exps.query.filter_by(idexp=int(exp_id)).first()
        if exp is not None:
            session, engine = open_experiment_session(exp)
            if session is not None and engine is not None:
                try:
                    round_row = (
                        session.query(Rounds)
                        .order_by(Rounds.day.desc(), Rounds.hour.desc(), Rounds.id.desc())
                        .first()
                    )
                    if round_row is not None and getattr(round_row, "id", None) is not None:
                        return int(round_row.id)
                finally:
                    session.close()
                    engine.dispose()
    except Exception:
        pass

    current_round = (
        Rounds.query.order_by(Rounds.day.desc(), Rounds.hour.desc(), Rounds.id.desc()).first()
    )
    if current_round is not None and getattr(current_round, "id", None) is not None:
        return int(current_round.id)

    return 0


@user.route("/<int:exp_id>/follow/<user_id>/<follower_id>", methods=["GET", "POST"])
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
    from y_web.src.models import Exps

    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    session = None
    engine = None
    if exp is not None:
        session, engine = open_experiment_session(exp)

    try:
        current_round_id = _resolve_follow_round_id(exp_id)
        acting_username = getattr(current_user, "username", "") or ""
        acting_user = None

        if session is not None and engine is not None:
            acting_user = session.query(User_mgmt).filter_by(username=acting_username).first()
            if acting_user is None and acting_username:
                # Keep the photo experiment consistent with the other platforms:
                # the logged-in participant must exist in the experiment DB
                # before we record social actions for them.
                try:
                    from y_web.src.experiment.helpers import ensure_experiment_user

                    ensure_experiment_user(
                        exp,
                        user_id=getattr(current_user, "id", follower_id) or follower_id,
                        username=acting_username,
                        email=str(getattr(current_user, "email", "") or ""),
                        password=str(getattr(current_user, "password", "") or ""),
                        joined_on=0,
                    )
                    acting_user = session.query(User_mgmt).filter_by(
                        username=acting_username
                    ).first()
                except Exception:
                    acting_user = None
        else:
            acting_user = User_mgmt.query.filter_by(username=acting_username).first()

        if acting_user is not None:
            source_user_id = acting_user.id
        else:
            # Handle both int and UUID follower_id (Standard vs HPC experiments)
            try:
                source_user_id = int(follower_id)
            except (ValueError, TypeError):
                source_user_id = follower_id

        query = session.query(Follow) if session is not None and engine is not None else Follow.query
        latest_follow = (
            query.filter_by(user_id=source_user_id, follower_id=user_id)
            .order_by(Follow.id.desc())
            .first()
        )
        new_action = "unfollow" if str(getattr(latest_follow, "action", "") or "").lower() == "follow" else "follow"

        follow_kwargs = dict(
            follower_id=user_id,
            user_id=source_user_id,
            action=new_action,
            round=current_round_id,
        )
        if getattr(exp, "platform_type", "") == "photo_sharing":
            follow_kwargs["id"] = str(uuid.uuid4())

        new_follow = Follow(**follow_kwargs)
        if session is not None and engine is not None:
            session.add(new_follow)
            session.commit()
        else:
            db.session.add(new_follow)
            db.session.commit()

        target_referrer = request.referrer or ""
        if "/photo/suggestions" in target_referrer:
            return redirect(url_for("main.photo_feed", exp_id=exp_id, user_id="all", timeline="feed", mode="rf", page=1, tab="for_you"))
        return redirect(target_referrer or url_for("main.photo_feed", exp_id=exp_id, user_id="all", timeline="feed", mode="rf", page=1, tab="for_you"))
    finally:
        if session is not None:
            session.close()
        if engine is not None:
            engine.dispose()


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
    current_round = Rounds.query.order_by(Rounds.day.desc(), Rounds.hour.desc()).first()

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

    current_round = Rounds.query.order_by(Rounds.day.desc(), Rounds.hour.desc()).first()

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


@user.route("/<int:exp_id>/report_content")
@login_required
def report_content(exp_id):
    """Report a post or comment using the shared reported table."""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    post_id = request.args.get("post_id")
    report_type = str(request.args.get("type") or "offensive").strip().lower()

    if report_type not in {"offensive", "toxic"}:
        if is_ajax:
            return jsonify({"message": "Unsupported report type.", "status": 400}), 400
        flash("Unsupported report type.", "error")
        return redirect(request.referrer or url_for("main.index"))

    exp_user = User_mgmt.query.filter_by(username=current_user.username).first()
    if not exp_user:
        if is_ajax:
            return (
                jsonify({"message": "User not found in experiment", "status": 404}),
                404,
            )
        flash("User not found in experiment", "error")
        return redirect(request.referrer or url_for("main.index"))

    try:
        post_id_converted = int(post_id)
    except (ValueError, TypeError):
        post_id_converted = post_id

    target_post = Post.query.filter_by(id=post_id_converted).first()
    current_round = Rounds.query.order_by(Rounds.day.desc(), Rounds.hour.desc()).first()
    if target_post is None or current_round is None:
        if is_ajax:
            return jsonify({"message": "Content not found.", "status": 404}), 404
        flash("Content not found.", "error")
        return redirect(request.referrer or url_for("main.index"))

    existing_report = Reported.query.filter_by(
        to_post=target_post.id, from_uid=exp_user.id
    ).first()
    current_count = Reported.query.filter_by(to_post=target_post.id).count()
    if existing_report is not None:
        if is_ajax:
            return jsonify(
                {
                    "message": "Content already reported.",
                    "status": 200,
                    "post_id": target_post.id,
                    "report_count": current_count,
                    "already_reported": True,
                }
            )
        flash("Content already reported.", "info")
        return redirect(request.referrer or url_for("main.index"))

    report_kwargs = {
        "type": report_type,
        "to_uid": target_post.user_id,
        "to_post": target_post.id,
        "from_uid": exp_user.id,
        "tid": current_round.id,
    }
    if isinstance(target_post.id, str):
        report_kwargs["id"] = str(uuid.uuid4())

    report = Reported(**report_kwargs)
    db.session.add(report)
    db.session.commit()
    new_count = Reported.query.filter_by(to_post=target_post.id).count()
    if is_ajax:
        return jsonify(
            {
                "message": "Content reported.",
                "status": 200,
                "post_id": target_post.id,
                "report_count": new_count,
                "already_reported": False,
            }
        )
    flash("Content reported.", "success")
    return redirect(request.referrer or url_for("main.index"))


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
