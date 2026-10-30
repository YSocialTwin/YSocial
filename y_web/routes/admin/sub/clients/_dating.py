"""Dating client creation: page and route (plan S3, IR-D-06)."""

import json
import os

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.routes.admin.sub.experiments._helpers import (
    _experiment_configuration_update_required,
)
from y_web.src.agents.platform import infer_population_username_type
from y_web.src.dating import client_config as dcc
from y_web.src.dating import is_dating_experiment
from y_web.src.dating import population as dp
from y_web.src.dating import server_settings, settings_ui
from y_web.src.dating.experiment_config import read_switches
from y_web.src.models import Client, Client_Execution, Population, Population_Experiment
from y_web.src.system import prompt_packs
from y_web.src.system.miscellanea import check_privileges
from y_web.src.system.path_utils import get_external_repo_dir, get_writable_path

from ._blueprint import clientsr
from ._crud import _build_client_creation_context, _get_experiment_folder_name


def _experiment_folder(exp) -> str:
    return os.path.join(
        get_writable_path(), "y_web", "experiments", _get_experiment_folder_name(exp)
    )


def _load_server_config(exp_dir):
    try:
        with open(
            os.path.join(exp_dir, "server_config.json"), "r", encoding="utf-8"
        ) as h:
            return json.load(h) or {}
    except (OSError, ValueError):
        return {}


@clientsr.route("/admin/clients_dating/<idexp>")
@login_required
def clients_dating(idexp):
    """Render the dating client creation page."""
    check_privileges(current_user.username)

    context = _build_client_creation_context(idexp, "HPC")
    exp = context["experiment"]
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    if not is_dating_experiment(exp):
        return redirect(url_for("clientsr.clients", idexp=idexp))
    if _experiment_configuration_update_required(exp):
        flash(
            _(
                "Update Experiment Configuration before creating clients for this experiment."
            ),
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    repo = get_external_repo_dir("YDating")
    exp_dir = _experiment_folder(exp)
    server_config = _load_server_config(exp_dir)
    switches = read_switches(server_config)
    fields = dcc.form_fields(repo)
    context.update(
        {
            "switches": switches,
            "sections": settings_ui.layout(
                fields, settings_ui.CLIENT_SECTIONS, switches
            ),
            "adv_values": dcc.values_for_form(repo),
            "slots_per_day": (server_config.get("simulation") or {}).get(
                "num_slots_per_day", 24
            ),
            "run_started": server_settings.run_started(exp_dir),
        }
    )
    return render_template("admin/clients_dating.html", **context)


@clientsr.route("/admin/create_dating_client", methods=["POST"])
@login_required
def create_dating_client_route():
    """Create a dating client from the form (config file, population file, database rows)."""
    check_privileges(current_user.username)
    return create_dating_client()


def create_dating_client():
    from y_web.src.models import Exps

    exp = db.session.scalars(
        select(Exps).filter_by(idexp=request.form.get("id_exp"))
    ).first()
    if exp is None or not is_dating_experiment(exp):
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    back = url_for("clientsr.clients_dating", idexp=exp.idexp)
    name = (request.form.get("name") or "").strip()
    descr = (request.form.get("descr") or "").strip()
    if not name or any(ch in name for ch in '/\\:*?"<>|'):
        flash(_("Invalid client name."), "error")
        return redirect(back)
    population = db.session.scalars(
        select(Population).filter_by(id=request.form.get("population_id", type=int))
    ).first()
    if population is None:
        flash(_("Select a valid population."), "error")
        return redirect(back)
    pop_type = infer_population_username_type(population)
    if pop_type != "dating":
        flash(
            _(
                "Population Username Type '%(pop_type)s' is incompatible with experiment platform 'dating'.",
                pop_type=pop_type,
            ),
            "error",
        )
        return redirect(back)
    pop_data = dp.load_document(population.id)
    if pop_data is None:
        flash(_("The population has no agents."), "error")
        return redirect(back)
    problems = dp.validate_population(pop_data)
    if (
        problems
    ):  # the custom features of the agents were edited into something the runtime would refuse
        flash(
            _(
                "The population is not valid for dating: %(why)s",
                why=" | ".join(problems[:5]),
            ),
            "error",
        )
        return redirect(back)

    repo = get_external_repo_dir("YDating")
    exp_dir = _experiment_folder(exp)
    server_config = _load_server_config(exp_dir)
    switches = read_switches(server_config)
    try:
        days = dcc.parse_days(request.form.get("num_days", "1"))
        language = prompt_packs.resolve(
            request.form.get("prompt_language"), exp.prompt_language
        )
        config = dcc.build_client_config(
            repo,
            name=name,
            population_file=f"{population.name}.json",
            days=days,
            server_config=server_config,
            memory_enabled=switches["memory"],
            language=language,
            form=request.form,
            label_of=_,
        )
    except dcc.DatingClientFormError as exc:
        flash(
            _("Invalid client settings: %(why)s", why=" | ".join(exc.problems[:5])),
            "error",
        )
        return redirect(back)

    os.makedirs(exp_dir, exist_ok=True)
    config_filename = os.path.join(exp_dir, f"client_{name}-{population.name}.json")
    if os.path.exists(config_filename):
        flash(_("A client with this name and population already exists."), "error")
        return redirect(back)
    with open(config_filename, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    with open(
        os.path.join(exp_dir, f"{population.name}.json"), "w", encoding="utf-8"
    ) as handle:
        json.dump(pop_data, handle, indent=2, ensure_ascii=False)
    prompt_packs.record_language(exp_dir, client=name, client_language=language)

    if not db.session.scalars(
        select(Population_Experiment).filter_by(
            id_population=population.id, id_exp=exp.idexp
        )
    ).first():
        db.session.add(
            Population_Experiment(id_population=population.id, id_exp=exp.idexp)
        )
        db.session.commit()
    client = Client(
        name=name,
        prompt_language=language,
        descr=descr,
        id_exp=exp.idexp,
        population_id=population.id,
        days=days,
        llm=(config.get("llm") or {}).get("model"),
        status=0,
    )
    db.session.add(client)
    db.session.commit()
    db.session.add(
        Client_Execution(
            client_id=client.id,
            last_active_hour=-1,
            last_active_day=-1,
            expected_duration_rounds=(
                -1 if days == -1 else days * config["num_slots_per_day"]
            ),
        )
    )
    db.session.commit()
    flash(_("Dating client '%(name)s' created successfully", name=name))
    return redirect(f"/admin/experiment_details/{exp.idexp}")
