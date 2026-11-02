"""Activation of the web interface of an experiment (the "Activate" toggle of the experiments admin).

An experiment whose ``Exps.status`` is 1 can be opened (``/admin/join_experiment/<id>``) by the people who may see it.
The steps behind the toggle live here so that the experiments page and the World Simulation (which activates the
frontends of its members) share one implementation:

* :func:`activate_experiment` sets ``status = 1``, registers the experiment database, gives the administrator a
  ``User_Experiment`` row and a participant of the experiment (Instant messaging and dating own their database: they only
  get the ``User_Experiment`` row);
* :func:`deactivate_experiment` sets ``status = 0``.

Both return an :class:`ActivationResult` with the message the admin page flashes; neither flashes nor redirects. Both are
idempotent: asking for the state an experiment already has changes nothing.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass

from flask import current_app

from y_web import db
from y_web.i18n import gettext as _


@dataclass
class ActivationResult:
    """Outcome of an activation or deactivation.

    ``kind`` is one of ``activated``, ``already_active``, ``deactivated``, ``already_inactive`` or ``failed``;
    ``message`` is the (translated) text for the person; ``changed`` tells whether anything was done."""

    kind: str
    message: str
    ok: bool = True
    changed: bool = True


def get_exp_default_recsys(exp_id: int):
    """Return ``(content_recsys, follow_recsys)`` defaults from ``ExpFrontendSettings`` (``"default"`` when not set)."""
    from y_web.src.models.admin import ExpFrontendSettings

    try:
        row = db.session.get(ExpFrontendSettings, exp_id)
        if row is None:
            return "default", "default"
        settings = json.loads(row.settings_json or "{}")
    except Exception:
        return "default", "default"
    content = settings.get("default_content_recsys") or "default"
    follow = settings.get("default_follow_recsys") or "default"
    return content, follow


def _ensure_user_experiment(admin_id, exp_id):
    from y_web.src.models import User_Experiment

    user_exp = db.session.query(User_Experiment).filter_by(user_id=admin_id, exp_id=exp_id).first()
    if user_exp is None:
        db.session.add(User_Experiment(user_id=admin_id, exp_id=exp_id))
        db.session.commit()


def deactivate_experiment(exp) -> ActivationResult:
    """Close the web interface of an experiment. An experiment that is not active is left as it is."""
    if exp.status != 1:
        return ActivationResult("already_inactive", "", changed=False)
    exp.status = 0
    db.session.commit()
    return ActivationResult("deactivated", _("Experiment '%(exp_name)s' deactivated.", exp_name=exp.exp_name))


def activate_experiment(exp, admin_user, *, rollback_on_failure=False) -> ActivationResult:
    """Open the web interface of an experiment for ``admin_user`` (an ``Admin_users`` row).

    An experiment that is already active is left as it is. When the participant cannot be prepared the result is a
    failure; the status stays 1 as the admin page always did, unless ``rollback_on_failure`` asks to restore 0."""
    from y_web.src.dating import is_dating_experiment
    from y_web.src.experiment.helpers import ensure_experiment_user
    from y_web.src.im import is_im_experiment

    if exp.status == 1:
        return ActivationResult("already_active", "", changed=False)
    exp_id = exp.idexp
    admin_user_id = admin_user.id
    exp.status = 1
    db.session.commit()

    # Register the experiment database dynamically
    from y_web.src.experiment.context import register_experiment_database

    done = ActivationResult("activated", _("Experiment '%(exp_name)s' activated.", exp_name=exp.exp_name))
    if is_im_experiment(exp) or is_dating_experiment(exp):
        # IM and dating own their database and have no YWeb participant row: nothing to bind or provision here
        _ensure_user_experiment(admin_user_id, exp_id)
        return done

    register_experiment_database(current_app, exp_id, exp.db_name)

    if exp.platform_type == "photo_sharing":
        participant_id = admin_user_id
    elif exp.simulator_type == "HPC":
        participant_id = str(uuid.uuid4())
    else:
        participant_id = admin_user_id
    content_recsys, follow_recsys = get_exp_default_recsys(exp_id)
    from y_web.src.content.cover_images import random_cover_image_url

    participant, created = ensure_experiment_user(
        exp,
        user_id=participant_id,
        username=str(admin_user.username),
        email=admin_user.email,
        password=admin_user.password,
        cover_image=random_cover_image_url(),
        recsys_type=content_recsys,
        frecsys_type=follow_recsys,
        joined_on=int(time.time()),
        account_id=admin_user_id,
    )
    if participant is None:
        if rollback_on_failure:
            exp.status = 0
            db.session.commit()
        return ActivationResult("failed", _("Unable to prepare the experiment user."), ok=False)
    if created:
        current_app.logger.info(
            "Created experiment participant %s for experiment %s",
            str(admin_user.username),
            exp_id,
        )

    # Add user to experiment if not present
    _ensure_user_experiment(admin_user_id, exp_id)
    return done
