"""The experiment a user is working with (kept in the session).

Several experiments can run at the same time, of one platform or of different ones, so an address that names none
(``/feed``) cannot tell which experiment is meant. The session remembers the last experiment the user opened: every
request whose address carries an experiment id (``/<exp_id>/...``, ``/api/.../<exp_id>/...``) records it, and a
platform asks :func:`current_experiment_id` when an address names none.
"""

from __future__ import annotations

from typing import Optional

from flask import has_request_context, session

SESSION_KEY = "current_exp_id"


def remember(exp_id) -> None:
    """Record ``exp_id`` as the experiment the user is working with (a session cookie is written only on change)."""
    if not has_request_context():
        return
    try:
        value = int(exp_id)
    except (TypeError, ValueError):
        return
    if session.get(SESSION_KEY) != value:
        session[SESSION_KEY] = value


def forget() -> None:
    """Drop the remembered experiment (the user left the simulation, or it is gone)."""
    if has_request_context():
        session.pop(SESSION_KEY, None)


def current_experiment_id() -> Optional[int]:
    """The experiment the user last opened, if it still exists; ``None`` otherwise."""
    if not has_request_context():
        return None
    value = session.get(SESSION_KEY)
    if value is None:
        return None
    from y_web import db
    from y_web.src.models import Exps

    exists = db.session.query(Exps.idexp).filter_by(idexp=value).first() is not None
    if not exists:
        forget()
        return None
    return int(value)


def current_experiment():
    """The experiment the user last opened (the row), or ``None``."""
    value = current_experiment_id()
    if value is None:
        return None
    from y_web.src.models import Exps

    return Exps.query.filter_by(idexp=value).first()


def choose_active_experiment(experiments):
    """The experiment a legacy landing address (``/feed`` and the addresses the platforms declare) leads to, among the active ones of a platform.

    The experiment the user last opened when it is among them, else the only one; ``None`` when the choice is the
    user's (none, or several and none of them opened): the caller sends the user to the experiment picker.
    """
    experiments = list(experiments)
    current = current_experiment_id()
    if current is not None:
        for experiment in experiments:
            if experiment.idexp == current:
                return experiment
    return experiments[0] if len(experiments) == 1 else None
