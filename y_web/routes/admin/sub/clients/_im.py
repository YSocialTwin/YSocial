"""Instant messaging (IM) client creation: page and route (plan, 5.3)."""

import datetime
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
from y_web.src.im import advanced_settings, is_im_experiment, news
from y_web.src.im.experiment_config import (
    TimeParameterError,
    apply_time_parameters,
    load_server_config,
    read_switches,
    run_started,
    save_server_config,
    time_parameters,
)
from y_web.src.im.client_config import (
    IM_SLOTS_PER_DAY,
    ImClientFormError,
    build_agent,
    build_client_config,
    build_page,
    build_topic_catalog,
    check_unique,
    topic_id,
    parse_chat_rows,
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
    exp_dir = _experiment_folder(exp)
    server_config = load_server_config(exp_dir)
    switches = read_switches(server_config)
    other_clients = db.session.query(Client).filter_by(id_exp=exp.idexp).count()
    started = run_started(exp_dir)
    times = time_parameters(server_config)
    if not times["start_date"]:
        times["start_date"] = datetime.date.today().isoformat()
    context.update(
        {
            "switches": switches,
            "news_feed_count": len(news.selected_feeds(exp_dir)),
            "experiment_memory_enabled": switches["memory"],
            "experiment_opinion_dynamics_enabled": switches["opinion"],
            "memory_configuration_supported": bool(context.get("llm_agents_enabled")),
            "times": times,
            # the start date and the round length belong to the experiment once a client or a run exists
            "times_locked": bool(other_clients) or started,
            "run_started": started,
            "adv_groups": advanced_settings.GROUPS,
            "adv_actions": advanced_settings.ACTIONS,
            "adv_action_scale": advanced_settings.ACTION_SCALE,
            "adv_memory": advanced_settings.MEMORY,
            "adv_defaults": advanced_settings.defaults(),
            "adv_name": advanced_settings.field_name,
        }
    )
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


def _hourly_activity(form):
    """``{hour: rate}`` for the hours the researcher filled in, else ``None`` (IM's default of 0.04 for every hour)."""
    rates = {}
    for hour in range(24):
        raw = form.get(f"hourly_{hour}")
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ImClientFormError("hourly activity must be numbers between 0 and 1") from None
        if not 0 <= value <= 1:
            raise ImClientFormError("hourly activity must be numbers between 0 and 1")
        rates[str(hour)] = value
    return rates or None


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

    exp_dir = _experiment_folder(exp)
    server_config = load_server_config(exp_dir)
    switches = read_switches(server_config)
    # the switches are the experiment's (Experiment Configuration), never the form's
    form_data = {key: form_data.get(key) for key in form_data.keys()}
    form_data["experiment_stress_reward_enabled"] = "true" if switches["stress_reward"] else ""
    form_data["experiment_opinion_dynamics_enabled"] = "true" if switches["opinion"] else ""
    form_data["experiment_emotion_annotation"] = "true" if switches["emotion"] else ""
    if not switches["memory"]:
        form_data["memory_enabled"] = ""
    form_data.pop("stress_reward_enabled", None)
    form_data.pop("opinion_enabled", None)
    try:
        settings = parse_client_form(form_data, label_of=_)
        hourly = _hourly_activity(form_data)
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
        chats = parse_chat_rows(form_data, {topic.id: topic.name for _link, topic in topic_rows})
        catalog = build_topic_catalog(
            {t: max(percentages[t], 1.0) / 100.0 for t in topics}, chats=chats
        )
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
    news_mode = news.parse_news_mode(form_data.get("news_mode"))
    if _flag_on(form_data.get("news_pages_from_feeds")):
        accounts += news.feed_pages(
            news.selected_feeds(exp_dir),
            used_urls=[a.get("feed_url") for a in accounts],
            used_usernames=[a["username"] for a in accounts],
            topics=[t for t in topics if percentages.get(t, 100.0) > 0],
            activity_profile=news.DEFAULT_PAGE_PROFILE,
        )
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
        hourly_activity=hourly,
        prompt_language=prompt_language,
    )
    config["telegram"].setdefault("news", {})["mode"] = news_mode
    # chats typed in the editor make the client's own catalog; otherwise the shared one is used
    catalog_file = "topic_catalog.json"
    if catalog.get("chats"):
        catalog_file = f"topic_catalog_{topic_id(name)}.json"
        config["telegram"]["topics"]["catalog_file"] = catalog_file
    schemas = Path(get_external_repo_dir("YInstantMessaging")) / "schemas" / "config"
    schema_file = schemas / "client_config.json"
    problems = schema_errors(config, str(schema_file)) + schema_errors(
        catalog, str(schemas / "topic_catalog.json")
    )
    if problems:
        flash(
            _("Invalid client settings: %(why)s", why="; ".join(problems[:5])), "error"
        )
        return redirect(back)

    os.makedirs(exp_dir, exist_ok=True)
    config_filename = _client_config_path_for_platform(exp_dir, exp, name, population.name)
    if os.path.exists(config_filename):
        flash(_("A client with this name and population already exists."), "error")
        return redirect(back)
    if catalog_file != "topic_catalog.json" and os.path.exists(os.path.join(exp_dir, catalog_file)):
        flash(_("A client with this name and population already exists."), "error")
        return redirect(back)

    # run length, start date and round length: set here, carried into the server configuration
    try:
        apply_time_parameters(
            server_config,
            days=settings["days"],
            start_date=settings["start_date"],
            ticks_per_round=settings["ticks_per_round"],
            other_clients=db.session.query(Client).filter_by(id_exp=exp.idexp).count(),
            run_started=run_started(exp_dir),
        )
    except (TimeParameterError, ValueError) as exc:
        flash(_("Invalid client settings: %(why)s", why=str(exc)), "error")
        return redirect(back)
    save_server_config(exp_dir, server_config)

    with open(config_filename, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    with open(os.path.join(exp_dir, f"{population.name}.json"), "w", encoding="utf-8") as handle:
        json.dump({"agents": accounts}, handle, indent=2)

    _write_news_snapshot(exp_dir, accounts, news_mode)

    shared = {"topics": catalog["topics"]}
    catalog_path = os.path.join(exp_dir, "topic_catalog.json")
    if not os.path.exists(catalog_path):
        with open(catalog_path, "w", encoding="utf-8") as handle:
            json.dump(shared, handle, indent=2)
    else:
        with open(catalog_path, "r", encoding="utf-8") as handle:
            differs = json.load(handle).get("topics") != shared["topics"]
        if differs and catalog_file == "topic_catalog.json":  # a client with its own catalog never reads the shared one
            if not run_started(exp_dir) and not db.session.query(Client).filter_by(id_exp=exp.idexp).count():
                # nothing depends on the old catalog (no run, no other client, e.g. the previous client was deleted)
                with open(catalog_path, "w", encoding="utf-8") as handle:
                    json.dump(shared, handle, indent=2)
            else:
                flash(
                    _(
                        "The experiment already has a topic catalog that differs from the current topics: it was kept, so that existing runs can resume."
                    ),
                    "warning",
                )
    if catalog_file != "topic_catalog.json":
        with open(os.path.join(exp_dir, catalog_file), "w", encoding="utf-8") as handle:
            json.dump(catalog, handle, indent=2)
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
    if opinions_enabled:  # as in the other platforms: the opinion configuration of the new client comes next
        return redirect(url_for("clientsr.opinion_configuration_im", idexp=exp.idexp, client_id=client.id))
    return redirect(f"/admin/experiment_details/{exp.idexp}")


def _flag_on(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "on", "yes")


def _write_news_snapshot(exp_dir, accounts, mode):
    """Snapshot mode needs the articles in a file: write it from the feeds of the news pages (fail-soft)."""
    urls = sorted({a["feed_url"] for a in accounts if a.get("is_page") and a.get("feed_url")})
    if mode != "snapshot" or not urls:
        return
    try:
        result = news.write_snapshot(exp_dir, urls)
    except Exception as exc:  # noqa: BLE001 - a feed problem never blocks the client
        flash(
            _("The news snapshot could not be written (%(error)s): the news pages will share nothing until it exists.", error=str(exc)),
            "warning",
        )
        return
    if result["written"] and not result["articles"]:
        flash(
            _("The feeds returned no articles: the news pages will share nothing. You can retry from the RSS feeds page."),
            "warning",
        )


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
