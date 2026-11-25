"""Like / dislike counters, with the optional isolation of the participants' own reactions.

With the experiment setting ``isolate_participant_reactions`` on, a reaction made by a participant (an account of
role ``user`` / ``student``: somebody taking part in a study, typically through a training module) is kept in
``Reactions`` as usual, so it stays in the logs, but it is counted only for the participant who made it:

* the counters shown to everybody else do not include it (:func:`count_reactions`), and
* it does not change ``Post.reaction_count`` (:func:`reaction_is_isolated`), the figure the popularity
  recommenders read.

The viewer is always the logged-in participant, so the counters of their own page show their own reactions on top
of the ones everybody sees. With the setting off (the default) nothing changes.
"""

from flask import g, has_request_context, request
from flask_login import current_user
from sqlalchemy import func, select

from y_web import db
from y_web.src.models import Admin_users, Reactions, User_mgmt

PARTICIPANT_ROLES = ("user", "student")
_CACHE = "_ys_isolated_reactors"


def _setting_on() -> bool:
    if not has_request_context():
        return False
    exp_id = (request.view_args or {}).get("exp_id")
    if exp_id is None:
        return False
    from y_web.routes.social.helpers import _load_ui_settings

    return bool(_load_ui_settings(int(exp_id)).get("isolate_participant_reactions"))


def participant_user_ids() -> set:
    """Ids (in the experiment database) of the users that are participants of a study."""
    names = db.session.scalars(
        select(Admin_users.username).where(Admin_users.role.in_(PARTICIPANT_ROLES))
    ).all()
    if not names:
        return set()
    return set(
        db.session.scalars(select(User_mgmt.id).where(User_mgmt.username.in_(names))).all()
    )


def _viewer_id():
    username = getattr(current_user, "username", None)
    if not username:
        return None
    return db.session.scalar(select(User_mgmt.id).where(User_mgmt.username == username))


def hidden_reactor_ids() -> frozenset:
    """Reactors whose reactions the current viewer does not see (empty when the isolation is off)."""
    if not has_request_context():
        return frozenset()
    if not hasattr(g, _CACHE):
        hidden = frozenset()
        if _setting_on():
            hidden = frozenset(participant_user_ids() - {_viewer_id()})
        setattr(g, _CACHE, hidden)
    return getattr(g, _CACHE)


def reaction_is_isolated(user_id) -> bool:
    """Whether the reactions of ``user_id`` are kept apart (the setting is on and the user is a participant)."""
    return _setting_on() and user_id in participant_user_ids()


def count_reactions(post_id, kind: str) -> int:
    """Number of ``kind`` ("like" / "dislike") reactions of ``post_id`` the current viewer sees."""
    query = (
        select(func.count())
        .select_from(Reactions)
        .where(Reactions.post_id == post_id, Reactions.type == kind)
    )
    hidden = hidden_reactor_ids()
    if hidden:
        query = query.where(Reactions.user_id.notin_(hidden))
    return int(db.session.scalar(query) or 0)
