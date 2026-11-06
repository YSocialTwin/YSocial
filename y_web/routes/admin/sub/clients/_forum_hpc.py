"""Forum client creation on YForum (HPC): page and route (plan F12, strada B).

The form offers only what YForum reads. The experiment switches (annotations, opinions, stress/reward, memory) are the
experiment's, never the form's; the configuration is validated with YForum's strict schema before anything is written.
"""

import json
import os
import uuid

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.routes.admin.sub.experiments._helpers import (
    _experiment_configuration_update_required,
)
from y_web.src.agents.custom_features import summarize_agent_custom_features_bulk
from y_web.src.forum import is_forum_hpc_experiment
from y_web.src.forum import network as forum_network
from y_web.src.forum.client_config import (
    FORUM_CONTENT_RECSYS,
    FORUM_FOLLOW_RECSYS,
    ForumClientFormError,
    build_client_config,
    parse_client_form,
)
from y_web.src.forum.experiment_config import read_switches
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
    Topic_List,
)
from y_web.src.system import prompt_packs
from y_web.src.system.miscellanea import check_privileges
from y_web.src.system.path_utils import get_external_repo_dir, get_writable_path

from ._blueprint import clientsr
from ._crud import (
    _build_client_creation_context,
    _apply_structured_features_to_agent_payload,
    _collect_population_agent_attributes,
    _client_config_path_for_platform,
    _get_experiment_folder_name,
)
from ._helpers import allocate_topics_by_percentage


def _experiment_folder(exp) -> str:
    return os.path.join(
        get_writable_path(), "y_web", "experiments", _get_experiment_folder_name(exp)
    )


def load_server_config(exp_dir: str) -> dict:
    """The experiment's server configuration ({} when it is not there yet)."""
    for name in ("server_config.json", "config_server.json"):
        path = os.path.join(exp_dir, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
    return {}


def _forum_context(idexp):
    """The creation context of the standard forum page, restricted to the recommenders YForum implements."""
    context = _build_client_creation_context(idexp, ("Standard", "Forum"))
    context["crecsys"] = [
        r for r in context["crecsys"] if r.name in FORUM_CONTENT_RECSYS
    ]
    context["frecsys"] = [
        r for r in context["frecsys"] if r.name in FORUM_FOLLOW_RECSYS
    ]
    return context


def _recsys_names(rows):
    return [r.name for r in rows]


def _validate(config):
    """Problems YForum's schema finds in a client configuration (empty: valid)."""
    import sys

    root = get_external_repo_dir("YForum")
    if not root or not os.path.isdir(root):
        return (
            []
        )  # nothing to check against: the start-time validator is the safety net
    sys.path.insert(0, str(root))
    try:
        from YForum.config_validation import validate
    except ImportError:
        return []
    finally:
        sys.path.remove(str(root))
    try:
        validate(config, "config/client_config")
    except Exception as exc:  # noqa: BLE001 - the schema error is the message
        return [str(exc)]
    return []


@clientsr.route("/admin/clients_forum_hpc/<idexp>")
@login_required
def clients_forum_hpc(idexp):
    """Render the forum (YForum) client creation page."""
    check_privileges(current_user.username)

    context = _forum_context(idexp)
    exp = context["experiment"]
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    if not is_forum_hpc_experiment(exp):
        return redirect(url_for("clientsr.clients", idexp=idexp))
    if _experiment_configuration_update_required(exp):
        flash(
            _(
                "Update Experiment Configuration before creating clients for this experiment."
            ),
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    switches = read_switches(load_server_config(_experiment_folder(exp)))
    context["switches"] = switches
    context["memory_configuration_supported"] = bool(context.get("llm_agents_enabled"))
    return render_template("admin/clients_forum_hpc.html", **context)


def _write_network(exp_dir, client_name, population_id, form, upload, config):
    """Write the initial follow network (model or uploaded file) and name it in the client configuration.

    Returns the network type recorded on the client (None: no network), or raises ``ForumClientFormError``.
    """
    model = (form.get("network_model") or "").strip()
    has_file = bool(upload and getattr(upload, "filename", ""))
    if not model and not has_file:
        return None
    names = [
        a.name
        for a in (
            db.session.scalars(select(Agent).filter_by(id=link.agent_id)).first()
            for link in db.session.scalars(
                select(Agent_Population).filter_by(population_id=population_id)
            ).all()
        )
        if a is not None
    ] + [
        p.name
        for p in (
            db.session.scalars(select(Page).filter_by(id=link.page_id)).first()
            for link in db.session.scalars(
                select(Page_Population).filter_by(population_id=population_id)
            ).all()
        )
        if p is not None
    ]
    try:
        if has_file:
            text = upload.read().decode("utf-8", errors="replace")
            edges, skipped = forum_network.filter_uploaded(text, names)
            if not edges:
                raise ForumClientFormError(
                    "the network file has no pair of agents of the population "
                    "(two columns with agent names, no header)"
                )
            if skipped:
                flash(
                    _(
                        "%(n)s lines of the network file were ignored (names not in the population).",
                        n=len(skipped),
                    ),
                    "warning",
                )
            kind = "Custom Network"
        else:
            edges = forum_network.generate_edges(
                model, names, forum_network.parse_parameters(form)
            )
            kind = model
    except forum_network.NetworkError as exc:
        raise ForumClientFormError(str(exc)) from None
    filename = f"{client_name}_network.csv"
    with open(os.path.join(exp_dir, filename), "w", encoding="utf-8") as handle:
        for follower, followed in edges:
            handle.write(f"{follower},{followed}\n")
    config["population"]["network_file"] = filename
    return kind


def create_forum_hpc_client(exp, name, descr, population_id, form):
    """Create a forum client: configuration, population file, network and database rows."""
    back = url_for("clientsr.clients_forum_hpc", idexp=exp.idexp)
    population = db.session.scalars(
        select(Population).filter_by(id=population_id)
    ).first()
    if population is None:
        flash(_("Select a valid population."), "error")
        return redirect(back)
    name = (name or "").strip()
    if not name or any(ch in name for ch in '/\\:*?"<>|'):
        flash(_("Invalid client name."), "error")
        return redirect(back)
    if db.session.scalars(select(Client).filter_by(name=name)).first():
        flash(_("Client name already exists."), "error")
        return redirect(back)

    context = _forum_context(exp.idexp)
    exp_dir = _experiment_folder(exp)
    server_config = load_server_config(exp_dir)
    switches = read_switches(server_config)
    llm_enabled = bool(context.get("llm_agents_enabled"))
    prompt_language = prompt_packs.resolve(
        form.get("prompt_language"), exp.prompt_language
    )

    try:
        values = parse_client_form(
            form,
            content_recsys=_recsys_names(context["crecsys"]),
            follow_recsys=_recsys_names(context["frecsys"]),
        )
        config = build_client_config(
            values,
            client_name=name,
            population_file=f"{population.name.replace(' ', '')}.json",
            owner=exp.owner,
            llm_agents_enabled=llm_enabled,
            language=prompt_language,
            server_config=server_config,
            switches=switches,
            population_attributes=_collect_population_agent_attributes(population.id),
        )
    except ForumClientFormError as exc:
        flash(_("Invalid client settings: %(why)s", why=str(exc)), "error")
        return redirect(back)

    agents = [
        db.session.scalars(select(Agent).filter_by(id=link.agent_id)).first()
        for link in db.session.scalars(
            select(Agent_Population).filter_by(population_id=population.id)
        ).all()
    ]
    agents = [a for a in agents if a is not None]
    if not agents:
        flash(_("The population is empty."), "error")
        return redirect(back)

    os.makedirs(exp_dir, exist_ok=True)
    config_filename = _client_config_path_for_platform(
        exp_dir, exp, name, population.name
    )
    if os.path.exists(config_filename):
        flash(_("A client with this name and population already exists."), "error")
        return redirect(back)

    # the network is written first: it names its file in the configuration that is validated next
    try:
        network_type = _write_network(
            exp_dir,
            name,
            population.id,
            form,
            request.files.get("network_file"),
            config,
        )
    except ForumClientFormError as exc:
        flash(_("Invalid client settings: %(why)s", why=str(exc)), "error")
        return redirect(back)
    problems = _validate(config)
    if problems:
        network_path = os.path.join(exp_dir, f"{name}_network.csv")
        if os.path.exists(network_path):
            os.remove(network_path)
        flash(
            _("Invalid client settings: %(why)s", why="; ".join(problems[:3])), "error"
        )
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
            percentages[topic.name] = float(
                form.get(f"topic_interest_{topic.id}", "100")
            )
        except (TypeError, ValueError):
            percentages[topic.name] = 100.0
    features = summarize_agent_custom_features_bulk([a.id for a in agents])
    payload = {"agents": []}
    for agent in agents:
        interests = allocate_topics_by_percentage(topics, percentages) or topics[:1]
        profile = (
            db.session.query(ActivityProfile)
            .filter_by(id=agent.activity_profile)
            .first()
        )
        entry = {
            "id": str(uuid.uuid4()),
            "username": agent.name,
            "email": f"{agent.name}@ysocial.it",
            "password": agent.name,
            "age": agent.age,
            "user_type": "agent",
            "leaning": agent.leaning,
            "interests": [interests, len(interests)],
            "oe": agent.oe,
            "co": agent.co,
            "ex": agent.ex,
            "ag": agent.ag,
            "ne": agent.ne,
            # "random"/"default": the agent uses the recommenders of the experiment
            "recsys_type": values["content_recsys"] or "random",
            "frecsys_type": values["follow_recsys"] or "default",
            "language": agent.language,
            "owner": exp.owner,
            "education_level": agent.education_level,
            "round_actions": int(agent.round_actions),
            "gender": agent.gender,
            "nationality": agent.nationality,
            "toxicity": agent.toxicity,
            "is_page": 0,
            "daily_activity_level": agent.daily_activity_level,
            "profession": agent.profession,
            "activity_profile": profile.name if profile else "Always On",
            "llm": llm_enabled,
        }
        # interests, opinions and custom features: the same helper of the standard forum client (plain values only)
        _apply_structured_features_to_agent_payload(entry, features.get(agent.id) or {})
        payload["agents"].append(entry)

    with open(config_filename, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    with open(
        os.path.join(exp_dir, config["population"]["file"]), "w", encoding="utf-8"
    ) as handle:
        json.dump(payload, handle, indent=2)
    prompt_packs.record_language(exp_dir, client=name, client_language=prompt_language)

    if not db.session.scalars(
        select(Population_Experiment).filter_by(
            id_population=population.id, id_exp=exp.idexp
        )
    ).first():
        db.session.add(
            Population_Experiment(id_population=population.id, id_exp=exp.idexp)
        )
        db.session.commit()
        from y_web.src.federation.dynamic import population_added  # INV-18

        population_added(exp.idexp, population.id)

    sim = config["simulation"]["actions_likelihood"]
    llm = values["llm"]
    client = Client(
        name=name,
        prompt_language=prompt_language,
        descr=descr,
        id_exp=exp.idexp,
        population_id=population.id,
        days=values["days"],
        percentage_new_agents_iteration=values["percentage_new_agents_iteration"],
        percentage_removed_agents_iteration=values[
            "percentage_removed_agents_iteration"
        ],
        max_length_thread_reading=values["max_length_thread_reading"],
        reading_from_follower_ratio=values["reading_from_follower_ratio"],
        probability_of_daily_follow=values["probability_of_daily_follow"],
        probability_of_secondary_follow=values["probability_of_secondary_follow"],
        attention_window=values["attention_window"],
        visibility_rounds=values["visibility_rounds"],
        post=sim["post"],
        comment=sim["comment"],
        read=sim["read"],
        search=sim["search"],
        share_link=sim["share_link"],
        image=sim["image"],
        crecsys=values["content_recsys"],
        frecsys=values["follow_recsys"],
        llm=llm["llm"] if llm_enabled else None,
        llm_api_key=llm["llm_api_key"] if llm_enabled else None,
        llm_max_tokens=llm["llm_max_tokens"] if llm_enabled else None,
        llm_temperature=llm["llm_temperature"] if llm_enabled else None,
        llm_v_agent=llm["llm_v_agent"] if llm_enabled else None,
        llm_v=llm["llm_v"] if llm_enabled else None,
        llm_v_api_key=llm["llm_v_api_key"] if llm_enabled else None,
        llm_v_max_tokens=llm["llm_v_max_tokens"] if llm_enabled else None,
        llm_v_temperature=llm["llm_v_temperature"] if llm_enabled else None,
        network_type=network_type,
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
                -1
                if values["days"] == -1
                else values["days"] * config["num_slots_per_day"]
            ),
        )
    )
    db.session.commit()
    flash(_("Forum client '%(name)s' created successfully", name=name))
    if switches.get("opinion"):
        # as every other platform: the opinions of the agents are set on the dedicated page (YForum reads them from the population)
        return redirect(
            url_for(
                "clientsr.opinion_configuration_hpc",
                idexp=exp.idexp,
                client_id=client.id,
            )
        )
    return redirect(f"/admin/experiment_details/{exp.idexp}")


@clientsr.route("/admin/create_forum_hpc_client", methods=["POST"])
@login_required
def create_forum_hpc_client_route():
    """Create a forum client on YForum."""
    check_privileges(current_user.username)
    exp = db.session.scalars(
        select(Exps).filter_by(idexp=request.form.get("id_exp"))
    ).first()
    if not exp:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    if not is_forum_hpc_experiment(exp):
        flash(_("This experiment is not a forum experiment on YForum."), "error")
        return redirect(url_for("clientsr.clients", idexp=exp.idexp))
    population_id = request.form.get("population_id")
    if not population_id:
        flash(_("Select a valid population."), "error")
        return redirect(url_for("clientsr.clients_forum_hpc", idexp=exp.idexp))
    return create_forum_hpc_client(
        exp,
        request.form.get("name"),
        request.form.get("descr"),
        population_id,
        request.form,
    )
