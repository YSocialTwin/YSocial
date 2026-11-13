"""Prompts page of a dating experiment: inspect and edit what the agents' model is told (S5, IR-D-13)."""

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.dating import is_dating_experiment
from y_web.src.dating import prompts_admin as pa
from y_web.src.models import Exps
from y_web.src.system.path_utils import get_writable_path

from ._blueprint import experiments
from ._helpers import _get_database_type, _get_experiment_folder, check_privileges


def _experiment_or_redirect(uid):
    check_privileges(current_user.username)
    experiment = db.session.scalars(select(Exps).filter_by(idexp=uid)).first()
    if experiment is None or not is_dating_experiment(experiment):
        flash(_("Experiment not found."), "error")
        return None, redirect(url_for("admin.dashboard"))
    return experiment, None


def _folder(experiment) -> str:
    return _get_experiment_folder(get_writable_path(), experiment, _get_database_type())


@experiments.route("/admin/prompts_dating/<int:uid>")
@login_required
def prompts_dating(uid):
    experiment, bounce = _experiment_or_redirect(uid)
    if bounce:
        return bounce
    language = pa.language_of(experiment, request.args.get("lang"))
    folder = _folder(experiment)
    base = pa.base_templates(language)
    custom = pa.custom_templates(folder, language)
    return render_template(
        "admin/prompts_dating.html",
        experiment=experiment,
        language=language,
        languages=pa.languages(),
        sections=pa.sections(base, custom),
        customised=sum(1 for k, v in custom.items() if k in base and v != base[k]),
        file_name=pa.prompt_file(folder, language).name,
        prefix=pa.PREFIX,
    )


@experiments.route("/admin/update_prompts_dating/<int:uid>", methods=["POST"])
@login_required
def update_prompts_dating(uid):
    experiment, bounce = _experiment_or_redirect(uid)
    if bounce:
        return bounce
    language = pa.language_of(experiment, request.form.get("lang"))
    override, errors = pa.parse_form(request.form, pa.base_templates(language))
    if errors:
        flash(_("Prompts not saved: %(why)s", why="; ".join(errors)), "error")
    else:
        pa.save(_folder(experiment), language, override)
        flash(_("Prompts saved. Clients started from now on use them."), "success")
    return redirect(url_for("experiments.prompts_dating", uid=uid, lang=language))


@experiments.route("/admin/reset_prompts_dating/<int:uid>", methods=["POST"])
@login_required
def reset_prompts_dating(uid):
    experiment, bounce = _experiment_or_redirect(uid)
    if bounce:
        return bounce
    language = pa.language_of(experiment, request.form.get("lang"))
    pa.save(_folder(experiment), language, {})
    flash(_("Prompts restored to the defaults of the package."), "success")
    return redirect(url_for("experiments.prompts_dating", uid=uid, lang=language))
