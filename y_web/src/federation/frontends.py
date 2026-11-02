"""Web interfaces of the member experiments of a World Simulation.

A member can be opened from the web only while its experiment is active (``Exps.status == 1``). Instead of activating
every member by hand, the World Simulation can do it for all of them: when it starts (option
``frontends.activate_on_start``, on by default, read by YWeb only) and on request (the Activate frontends and Deactivate
frontends buttons of the Execution tab). The steps of one experiment are those of the experiments page
(:mod:`y_web.src.experiment.activation`).

Nothing here raises for one member: every member gets its own outcome, so that a failure is reported and the others go on.
Stopping a World Simulation does not deactivate the frontends.
"""

from __future__ import annotations

from typing import Optional

from y_web import db
from y_web.i18n import gettext as _

# Outcomes of one member
ACTIVATED, ALREADY_ACTIVE, DEACTIVATED, ALREADY_INACTIVE, NOT_ALLOWED, FAILED = (
    "activated", "already_active", "deactivated", "already_inactive", "not_allowed", "failed")
PROBLEMS = (NOT_ALLOWED, FAILED)


def activate_on_start(options) -> bool:
    """The option ``frontends.activate_on_start`` of stored options (absent: on)."""
    block = (options or {}).get("frontends")
    value = block.get("activate_on_start", True) if isinstance(block, dict) else True
    return value not in (False, 0, "0", "false", "False")


def owner_user(fed):
    """The ``Admin_users`` row of the owner of a World Simulation (who the frontends are activated for when nobody else is)."""
    from sqlalchemy import select

    from y_web.src.models import Admin_users

    if not getattr(fed, "owner", None):
        return None
    return db.session.scalars(select(Admin_users).filter_by(username=fed.owner)).first()


def _outcome(row, exp, state, message=""):
    return {"member": row.member, "platform": row.platform_type, "experiment": exp.exp_name if exp else "", "state": state, "message": message}


def _apply(fed, admin_user, action):
    from y_web.src.experiment.access import user_can_view_experiment
    from y_web.src.federation import service

    outcomes = []
    for row, exp in service.members_of(fed):
        if exp is None:
            outcomes.append(_outcome(row, exp, FAILED, _("Experiment not found.")))
            continue
        if not user_can_view_experiment(admin_user, exp):
            outcomes.append(_outcome(row, exp, NOT_ALLOWED, _("You are not allowed to access this experiment.")))
            continue
        try:
            result = action(exp)
        except Exception as exc:  # noqa: BLE001 - one member never stops the others
            db.session.rollback()
            outcomes.append(_outcome(row, exp, FAILED, str(exc)))
            continue
        outcomes.append(_outcome(row, exp, result.kind, result.message if not result.ok else ""))
    return outcomes


def activate_frontends(fed, admin_user) -> list:
    """Activate the web interface of every member for ``admin_user``; returns one outcome (dict) per member."""
    from y_web.src.experiment.activation import activate_experiment

    if admin_user is None:
        from y_web.src.federation import service

        return [_outcome(row, exp, FAILED, _("Unable to resolve current user.")) for row, exp in service.members_of(fed)]
    return _apply(fed, admin_user, lambda exp: activate_experiment(exp, admin_user, rollback_on_failure=True))


def deactivate_frontends(fed, admin_user) -> list:
    """Deactivate the web interface of every member; returns one outcome (dict) per member."""
    from y_web.src.experiment.activation import deactivate_experiment

    return _apply(fed, admin_user, deactivate_experiment)


def warnings_of(outcomes) -> list:
    """Texts for the outcomes that are problems (``Member (experiment): reason``)."""
    return [_("%(experiment)s: %(error)s", experiment=o["experiment"] or o["member"], error=o["message"]) for o in outcomes if o["state"] in PROBLEMS]


def summary(outcomes, activating: bool) -> Optional[str]:
    """One line for the person: how many members were switched and how many were already as asked."""
    changed = sum(1 for o in outcomes if o["state"] == (ACTIVATED if activating else DEACTIVATED))
    already = sum(1 for o in outcomes if o["state"] == (ALREADY_ACTIVE if activating else ALREADY_INACTIVE))
    if activating:
        return _("Web interfaces activated: %(n)s (already active: %(m)s).", n=changed, m=already)
    return _("Web interfaces deactivated: %(n)s (already inactive: %(m)s).", n=changed, m=already)


def frontend_rows(fed, admin_user) -> list:
    """What the Execution tab shows per member: ``active`` (status 1), whether the person may act on it and the address to open it."""
    from y_web.src.experiment.access import user_can_view_experiment
    from y_web.src.federation import service

    rows = []
    for row, exp in service.members_of(fed):
        if exp is None:
            continue
        allowed = bool(user_can_view_experiment(admin_user, exp))
        active = exp.status == 1
        rows.append({"member": row.member, "platform": row.platform_type, "experiment": exp.exp_name, "exp_id": exp.idexp,
                     "active": active, "allowed": allowed, "url": f"/admin/join_experiment/{exp.idexp}" if active and allowed else None})
    return rows
