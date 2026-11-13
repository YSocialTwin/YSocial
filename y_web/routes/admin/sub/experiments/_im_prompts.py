"""Prompts page of an instant messaging experiment: inspect and edit what the agents' model is told."""

import os

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.im import is_im_experiment
from y_web.src.im import prompts_admin as pa
from y_web.src.models import Exps

from ._blueprint import experiments
from ._helpers import check_privileges


def _folder(experiment) -> str:
    from y_web.src.im.participant import experiment_folder

    return experiment_folder(experiment)


def _experiment_or_redirect(uid):
    check_privileges(current_user.username)
    experiment = db.session.scalars(select(Exps).filter_by(idexp=uid)).first()
    if experiment is None or not is_im_experiment(experiment):
        flash(_("Experiment not found."), "error")
        return None, redirect(url_for("admin.dashboard"))
    return experiment, None


@experiments.route("/admin/prompts_im/<int:uid>")
@login_required
def prompts_im(uid):
    experiment, bounce = _experiment_or_redirect(uid)
    if bounce:
        return bounce
    language = pa.language_of(experiment)
    folder = _folder(experiment)
    base = pa.base_templates(language)
    custom = pa.custom_templates(folder, language)
    return render_template(
        "admin/prompts_im.html",
        experiment=experiment,
        language=language,
        sections=pa.sections(base, custom),
        customised=sum(1 for k, v in custom.items() if k in base and v != base[k]),
        file_name=pa.prompt_file(folder, language).name,
        prefix=pa.PREFIX,
    )


@experiments.route("/admin/update_prompts_im/<int:uid>", methods=["POST"])
@login_required
def update_prompts_im(uid):
    experiment, bounce = _experiment_or_redirect(uid)
    if bounce:
        return bounce
    language = pa.language_of(experiment)
    override, errors = pa.parse_form(request.form, pa.base_templates(language))
    if errors:
        flash(_("Prompts not saved: %(why)s", why="; ".join(errors)), "error")
    else:
        pa.save(_folder(experiment), language, override)
        flash(_("Prompts saved. Clients started from now on use them."), "success")
    return redirect(url_for("experiments.prompts_im", uid=uid))


@experiments.route("/admin/reset_prompts_im/<int:uid>", methods=["POST"])
@login_required
def reset_prompts_im(uid):
    experiment, bounce = _experiment_or_redirect(uid)
    if bounce:
        return bounce
    pa.save(_folder(experiment), pa.language_of(experiment), {})
    flash(_("Prompts restored to the defaults of the package."), "success")
    return redirect(url_for("experiments.prompts_im", uid=uid))
