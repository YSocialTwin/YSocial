"""Instant messaging (IM) client creation: page and route (plan, 5.3)."""

import json
import os
from pathlib import Path

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.routes.admin.sub.experiments._helpers import (
    _experiment_configuration_update_required,
)
from y_web.src.agents.custom_features import summarize_agent_custom_features_bulk
from y_web.src.agents.platform import infer_population_username_type
from y_web.src.im import is_im_experiment
from y_web.src.im.client_config import (
    IM_SLOTS_PER_DAY,
    ImClientFormError,
    build_agent,
    build_client_config,
    build_page,
    build_topic_catalog,
    check_unique,
    parse_client_form,
    schema_errors,
)
from y_web.src.models import (
    ActivityProfile,
    Agent,
    Agent_Population,
    Client,
    Client_Execution,
    Exp_Topic,
    Exps,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    PopulationActivityProfile,
    Topic_List,
)
from y_web.src.system import prompt_packs
from y_web.src.system.miscellanea import check_privileges
from y_web.src.system.path_utils import get_external_repo_dir, get_writable_path

from ._blueprint import clientsr
from ._crud import (
    _build_client_creation_context,
    _client_config_path_for_platform,
    _get_experiment_folder_name,
)
from ._helpers import allocate_topics_by_percentage


def _experiment_folder(exp) -> str:
    return os.path.join(
        get_writable_path(), "y_web", "experiments", _get_experiment_folder_name(exp)
    )


@clientsr.route("/admin/clients_im/<idexp>")
@login_required
def clients_im(idexp):
    """Render the instant messaging client creation page."""
    check_privileges(current_user.username)

    context = _build_client_creation_context(idexp, "HPC")
    exp = context["experiment"]
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    if not is_im_experiment(exp):
        return redirect(url_for("clientsr.clients", idexp=idexp))
    if _experiment_configuration_update_required(exp):
        flash(
            _(
                "Update Experiment Configuration before creating clients for this experiment."
            ),
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    return render_template("admin/clients_im.html", **context)


def _activity_profiles(population_id):
    links = db.session.query(PopulationActivityProfile).filter(
        PopulationActivityProfile.population == population_id
    )
    ids = [link.activity_profile for link in links]
    rows = (
        db.session.query(ActivityProfile).filter(ActivityProfile.id.in_(ids)).all()
        if ids
        else []
    )
    profiles = {row.name: row.hours for row in rows}
    profiles.setdefault("Always On", ",".join(str(h) for h in range(24)))
    return profiles


def _profile_name(profile_id):
    row = (
        db.session.query(ActivityProfile).filter_by(id=profile_id).first()
        if profile_id is not None
        else None
    )
    return row.name if row else "Always On"


def create_im_client(exp, name, descr, population_id, form_data):
    """Create an IM client: config, population and catalog files plus the database rows."""
    back = url_for("clientsr.clients_im", idexp=exp.idexp)
    population = db.session.scalars(select(Population).filter_by(id=population_id)).first()
    if population is None:
        flash(_("Select a valid population."), "error")
        return redirect(back)
    pop_type = infer_population_username_type(population)
    if pop_type not in {None, "instant_messaging"}:
        flash(
            _(
                "Population Username Type '%(pop_type)s' is incompatible with experiment platform 'instant_messaging'.",
                pop_type=pop_type,
            ),
            "error",
        )
        return redirect(back)
    name = (name or "").strip()
    if not name or any(ch in name for ch in '/\\:*?"<>|'):
        flash(_("Invalid client name."), "error")
        return redirect(back)

    try:
        settings = parse_client_form(form_data)
    except ImClientFormError as exc:
        flash(_("Invalid client settings: %(why)s", why=str(exc)), "error")
        return redirect(back)

    topic_rows = (
        db.session.query(Exp_Topic, Topic_List)
        .join(Topic_List, Exp_Topic.topic_id == Topic_List.id)
        .filter(Exp_Topic.exp_id == exp.idexp)
        .all()
    )
    topics, percentages = [], {}
    for _link, topic in topic_rows:
        topics.append(topic.name)
        try:
            percentages[topic.name] = float(form_data.get(f"topic_interest_{topic.id}", "100"))
        except (TypeError, ValueError):
            percentages[topic.name] = 100.0

    try:
        catalog = build_topic_catalog({t: max(percentages[t], 1.0) / 100.0 for t in topics})
    except ImClientFormError as exc:
        flash(_("Invalid client settings: %(why)s", why=str(exc)), "error")
        return redirect(back)

    agents = [
        db.session.scalars(select(Agent).filter_by(id=link.agent_id)).first()
        for link in db.session.scalars(
            select(Agent_Population).filter_by(population_id=population.id)
        ).all()
    ]
    agents = [a for a in agents if a is not None]
    pages = [
        db.session.scalars(select(Page).filter_by(id=link.page_id)).first()
        for link in db.session.scalars(
            select(Page_Population).filter_by(population_id=population.id)
        ).all()
    ]
    pages = [p for p in pages if p is not None]
    if not agents and not pages:
        flash(_("The population is empty."), "error")
        return redirect(back)

    opinions_enabled = bool(settings["opinion_enabled"])
    features = summarize_agent_custom_features_bulk([a.id for a in agents])
    accounts = [
        build_agent(
            agent,
            interests=allocate_topics_by_percentage(topics, percentages) or topics[:1],
            activity_profile=_profile_name(agent.activity_profile),
            structured=features.get(agent.id),
            opinions_enabled=opinions_enabled,
        )
        for agent in agents
    ] + [
        build_page(
            page,
            topics=[t for t in topics if percentages.get(t, 100.0) > 0],
            activity_profile=_profile_name(page.activity_profile),
        )
        for page in pages
    ]
    try:
        check_unique(accounts)
    except ImClientFormError as exc:
        flash(_("Invalid population: %(why)s", why=str(exc)), "error")
        return redirect(back)

    prompt_language = prompt_packs.resolve(
        form_data.get("prompt_language"), exp.prompt_language
    )
    config = build_client_config(
        client_name=name,
        settings=settings,
        topics=topics,
        activity_profiles=_activity_profiles(population.id),
        prompt_language=prompt_language,
    )
    schema_file = Path(get_external_repo_dir("YInstantMessaging")) / "schemas" / "config" / "client_config.json"
    problems = schema_errors(config, str(schema_file))
    if problems:
        flash(
            _("Invalid client settings: %(why)s", why="; ".join(problems[:5])), "error"
        )
        return redirect(back)

    exp_dir = _experiment_folder(exp)
    os.makedirs(exp_dir, exist_ok=True)
    config_filename = _client_config_path_for_platform(exp_dir, exp, name, population.name)
    if os.path.exists(config_filename):
        flash(_("A client with this name and population already exists."), "error")
        return redirect(back)

    with open(config_filename, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    with open(os.path.join(exp_dir, f"{population.name}.json"), "w", encoding="utf-8") as handle:
        json.dump({"agents": accounts}, handle, indent=2)

    catalog_path = os.path.join(exp_dir, "topic_catalog.json")
    if not os.path.exists(catalog_path):
        with open(catalog_path, "w", encoding="utf-8") as handle:
            json.dump(catalog, handle, indent=2)
    else:
        with open(catalog_path, "r", encoding="utf-8") as handle:
            if json.load(handle) != catalog:
                flash(
                    _(
                        "The experiment already has a topic catalog that differs from the current topics: it was kept, so that existing runs can resume."
                    ),
                    "warning",
                )
    prompt_packs.record_language(exp_dir, client=name, client_language=prompt_language)

    if not db.session.scalars(
        select(Population_Experiment).filter_by(id_population=population.id, id_exp=exp.idexp)
    ).first():
        db.session.add(Population_Experiment(id_population=population.id, id_exp=exp.idexp))
        db.session.commit()

    client = Client(
        name=name,
        prompt_language=prompt_language,
        descr=descr,
        id_exp=exp.idexp,
        population_id=population.id,
        days=settings["days"],
        llm=settings["model"],
        status=0,
    )
    db.session.add(client)
    db.session.commit()
    db.session.add(
        Client_Execution(
            client_id=client.id,
            last_active_hour=-1,
            last_active_day=-1,
            expected_duration_rounds=settings["days"] * IM_SLOTS_PER_DAY,
        )
    )
    db.session.commit()

    flash(_("Instant messaging client '%(name)s' created successfully", name=name))
    return redirect(f"/admin/experiment_details/{exp.idexp}")


@clientsr.route("/admin/create_im_client", methods=["POST"])
@login_required
def create_im_client_route():
    """Create an instant messaging client."""
    check_privileges(current_user.username)

    exp = db.session.scalars(
        select(Exps).filter_by(idexp=request.form.get("id_exp"))
    ).first()
    if not exp:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    if not is_im_experiment(exp):
        flash(_("This experiment is not an instant messaging experiment."), "error")
        return redirect(url_for("clientsr.clients", idexp=exp.idexp))
    population_id = request.form.get("population_id")
    if not population_id:
        flash(_("Select a valid population."), "error")
        return redirect(url_for("clientsr.clients_im", idexp=exp.idexp))
    return create_im_client(
        exp,
        request.form.get("name"),
        request.form.get("descr"),
        population_id,
        request.form,
    )
