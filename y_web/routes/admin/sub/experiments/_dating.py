"""Dating experiments: advanced server settings and recommender choice (plan S3, IR-D-07, IR-D-10)."""

import copy
import json
import os

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.dating import (
    is_dating_experiment,
    schema_forms,
    server_settings,
    settings_ui,
)
from y_web.src.dating.experiment_config import read_switches
from y_web.src.experiment.access import (
    user_can_manage_experiment,
    user_can_view_experiment,
)
from y_web.src.models import Exps
from y_web.src.system.miscellanea import check_privileges
from y_web.src.system.path_utils import get_external_repo_dir, get_writable_path

from ._blueprint import experiments
from ._helpers import (
    _current_admin_user_or_none,
    _get_database_type,
    _get_experiment_folder,
)


def _dating_experiment(uid):
    exp = db.session.scalars(select(Exps).filter_by(idexp=uid)).first()
    if exp is None or not is_dating_experiment(exp):
        return None
    return exp


def _server_config_path(exp):
    folder = _get_experiment_folder(get_writable_path(), exp, _get_database_type())
    return folder, os.path.join(folder, "server_config.json")


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except (OSError, ValueError):
        return {}


@experiments.route("/admin/dating_settings/<int:uid>")
@login_required
def dating_settings(uid):
    """Advanced server settings and recommender of a dating experiment."""
    check_privileges(current_user.username)
    exp = _dating_experiment(uid)
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    if not user_can_view_experiment(_current_admin_user_or_none(), exp):
        flash(_("You are not allowed to view this experiment."), "error")
        return redirect(url_for("experiments.settings"))
    repo = get_external_repo_dir("YDating")
    folder, path = _server_config_path(exp)
    config = _load(path)
    sch = server_settings.schema(repo)
    base = schema_forms.merge(schema_forms.defaults(sch), config)
    fields = server_settings.form_fields(repo)
    values = {
        f.path: schema_forms.to_form_text(
            schema_forms.get_path(base, f.path, f.default), f
        )
        for f in fields
    }
    values.update(server_settings.recsys_form_text(repo, base))
    models = server_settings.recsys_models(repo)
    sections = settings_ui.layout(
        fields, settings_ui.SERVER_SECTIONS, read_switches(config)
    )
    started = server_settings.run_started(folder)
    for section in sections:  # once data exists these two keep their value
        for block in section["blocks"]:
            for item in block["fields"]:
                item["locked"] = started and (
                    item["f"].path in server_settings.FIXED_AFTER_START
                )
    return render_template(
        "admin/dating_settings.html",
        experiment=exp,
        sections=sections,
        recsys_labels=settings_ui.LABELS,
        values=values,
        models=models,
        common=[
            {"f": f, "label": settings_ui.label_of(f.path)}
            for f in server_settings.common_fields(repo)
        ],
        model_fields={
            m: [
                {"f": f, "label": settings_ui.label_of(f.path)}
                for f in server_settings.recsys_fields(repo, m)
            ]
            for m in models
        },
        default_model=(base.get("matching") or {}).get("default_model"),
        locked=bool(exp.running),
        run_started=started,
        recsys_info=settings_ui.RECSYS_INFO,
        can_manage=user_can_manage_experiment(_current_admin_user_or_none(), exp),
    )


@experiments.route("/admin/update_dating_settings/<int:uid>", methods=["POST"])
@login_required
def update_dating_settings(uid):
    """Validate and save the advanced server settings; refused once the run shapes depend on them."""
    check_privileges(current_user.username)
    exp = _dating_experiment(uid)
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    if not user_can_manage_experiment(_current_admin_user_or_none(), exp):
        flash(_("You do not have permission to update this experiment."), "error")
        return redirect(url_for("experiments.experiment_details", uid=uid))
    back = url_for("experiments.dating_settings", uid=uid)
    repo = get_external_repo_dir("YDating")
    folder, path = _server_config_path(exp)
    config = _load(path)
    previous = copy.deepcopy(config)
    try:
        server_settings.apply_form(repo, config, request.form, label_of=_)
    except server_settings.ServerSettingsError as exc:
        flash(
            _("Invalid dating settings: %(why)s", why=" | ".join(exc.problems[:5])),
            "error",
        )
        return redirect(back)
    allowed, why = server_settings.check_change_allowed(
        folder, config, running=bool(exp.running), old_config=previous
    )
    if not allowed:
        flash(
            _("The settings were not saved: %(why)s.", why=_(why)),
            "error",
        )
        return redirect(back)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=4)
    os.replace(tmp, path)
    server_settings.refresh_lock(folder, config)
    flash(_("Advanced settings updated."), "success")
    return redirect(back)
