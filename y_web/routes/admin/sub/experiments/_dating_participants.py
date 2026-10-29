"""Participants page of a dating experiment (IR-D-22, IR-D-31): gateway, limits and the people who play."""

from flask import flash, redirect, render_template
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.dating import is_dating_experiment
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
