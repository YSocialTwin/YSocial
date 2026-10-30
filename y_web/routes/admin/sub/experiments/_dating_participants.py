"""Participants page of a dating experiment (IR-D-22, IR-D-31): gateway, limits and the people who play."""

from flask import flash, redirect, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.dating import human, is_dating_experiment
from y_web.src.dating.gateway import GatewayClient, GatewayUnavailable
from y_web.src.dating.humans_admin import humans_overview
from y_web.src.models import Exps
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import experiments


@experiments.route("/admin/dating_participants/<int:idexp>")
@login_required
def dating_participants(idexp):
    check_privileges(current_user.username)
    exp = db.session.scalars(select(Exps).filter_by(idexp=idexp)).first()
    if exp is None or not is_dating_experiment(exp):
        flash(_("Experiment not found."), "error")
        return redirect("/admin/experiments")
    return render_template(
        "admin/dating_participants.html", experiment=exp, data=humans_overview(exp)
    )


@experiments.route(
    "/admin/dating_participants/<int:idexp>/reset_credits", methods=["POST"]
)
@login_required
def dating_participants_reset_credits(idexp):
    """Give the likes and super likes of the day back to one person, or to every person (``account=all``)."""
    check_privileges(current_user.username)
    exp = db.session.scalars(select(Exps).filter_by(idexp=idexp)).first()
    if exp is None or not is_dating_experiment(exp):
        flash(_("Experiment not found."), "error")
        return redirect("/admin/experiments")
    back = f"/admin/dating_participants/{idexp}"
    overview = humans_overview(exp)
    if not overview["enabled"]:
        flash(_("Human participation is off for this experiment."), "error")
        return redirect(back)
    wanted = request.form.get("account", "")
    known = [h["account_id"] for h in overview["humans"] if h.get("created")]
    targets = known if wanted == "all" else [a for a in known if a == wanted]
    if not targets:
        flash(
            _("Nobody to reset: the person has not entered the experiment yet."),
            "error",
        )
        return redirect(back)
    client = GatewayClient(human.experiment_folder(exp))
    done = 0
    try:
        for account in targets:
            status, _payload = client.reset_quota(account)
            done += 1 if status == 200 else 0
    except GatewayUnavailable:
        flash(
            _("The server cannot be reached right now: try again in a moment."), "error"
        )
        return redirect(back)
    if done:
        flash(
            _(
                "Credits reset for %(n)s person(s): likes and super likes of the day are back.",
                n=done,
            ),
            "success",
        )
    else:
        flash(_("The credits could not be reset."), "error")
    return redirect(back)
