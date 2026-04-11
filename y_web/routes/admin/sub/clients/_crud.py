"""CRUD routes and helpers for client creation and deletion."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import sys
import traceback
import uuid
from pathlib import Path

import faker
import networkx as nx
import numpy as np
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.routes.admin.sub.experiments._helpers import (
    _experiment_configuration_update_required,
    _experiment_uses_llm_agents,
)
from y_web.src.agents.platform import (
    ensure_population_username_type_column,
    infer_population_username_type,
    population_matches_platform,
)
from y_web.src.external_runtime.registry import EXTERNAL_DIR
from y_web.src.llm.vllm_manager import get_llm_models, is_vllm_installed
from y_web.src.models import (
    ActivityProfile,
    AgeClass,
    Agent,
    Agent_Ext,
    Agent_Population,
    Agent_Profile,
    Client,
    Client_Execution,
    Content_Recsys,
    Exp_Topic,
    Exps,
    Follow_Recsys,
    Leanings,
    OpinionGroup,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    PopulationActivityProfile,
    Topic_List,
    User_mgmt,
)
from y_web.src.simulation.adhoc_client import (
    config_path_for_client,
    delete_adhoc_client,
    initialize_state_for_config,
)
from y_web.src.simulation.adhoc_client import read_json as read_adhoc_json
from y_web.src.simulation.adhoc_client import write_json as write_adhoc_json
from y_web.src.system.miscellanea import check_privileges, get_db_type
from y_web.src.system.path_utils import get_resource_path

from ._blueprint import clientsr
from ._helpers import _forum_effective_link_share, allocate_topics_by_percentage

PLUGIN_REGISTRY_RELATIVE_PATHS = (
    Path("meta") / "registry.json",
    Path("plugins_exposed") / "agent_types.json",
    Path("plugin_exposed") / "agent_types.json",
)


def _custom_agent_slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    tokens = [token for token in cleaned.split() if token and token != "agent"]
    if not tokens:
        return "custom"
    if len(tokens) == 1:
        return tokens[0]
    return tokens[0][0] + "".join(tokens[1:])


def _adhoc_agent_specs() -> list[dict]:
    specs = []
    if not EXTERNAL_DIR.exists():
        return specs

    for repo_dir in sorted(EXTERNAL_DIR.iterdir()):
        if not repo_dir.is_dir():
            continue
        manifest_path = None
        for relative_path in PLUGIN_REGISTRY_RELATIVE_PATHS:
            candidate = repo_dir / relative_path
            if candidate.exists():
                manifest_path = candidate
                break
        if manifest_path is None:
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        for entry in payload.get("agent_types", []):
            agent_type = str(entry.get("agent_type") or "").strip()
            if not agent_type:
                continue
            display_name = str(entry.get("display_name") or agent_type).strip()
            slug = _custom_agent_slug(display_name)
            accepted_slugs = {slug, agent_type}
            if slug == "hworld":
                accepted_slugs.add("hword")
            specs.append(
                {
                    "slug": slug,
                    "accepted_slugs": sorted(accepted_slugs),
                    "agent_type": agent_type,
                    "display_name": display_name,
                    "description": str(entry.get("description") or "").strip(),
                    "requires_llm": bool(
                        entry.get("requires_llm", entry.get("llm_required", False))
                    ),
                    "requires_opinion_dynamics": bool(
                        entry.get("requires_opinion_dynamics", False)
                    ),
                    "client_parameter_sections": list(
                        entry.get("client_parameter_sections") or []
                    ),
                    "client_parameters": list(entry.get("client_parameters") or []),
                    "repo_name": repo_dir.name,
                }
            )
    return specs


def _adhoc_population_choices(idexp: str, specs: list[dict]) -> dict[str, list[dict]]:
    pop_exp_associations = Population_Experiment.query.filter_by(id_exp=idexp).all()
    population_ids = [pe.id_population for pe in pop_exp_associations]
    pops = (
        Population.query.filter(~Population.id.in_(population_ids)).all()
        if population_ids
        else Population.query.all()
    )
    custom_pops = [pop for pop in pops if pop.pop_type not in (None, "")]

    choices = {}
    for spec in specs:
        matching = []
        for pop in custom_pops:
            if pop.pop_type in spec["accepted_slugs"]:
                matching.append(
                    {
                        "id": pop.id,
                        "name": pop.name,
                        "descr": pop.descr or "",
                    }
                )
        choices[spec["slug"]] = matching
    return choices


def _find_adhoc_agent_spec(agent_slug: str | None) -> dict | None:
    if not agent_slug:
        return None
    for spec in _adhoc_agent_specs():
        if agent_slug in spec["accepted_slugs"] or agent_slug == spec["slug"]:
            return spec
    return None


def _coerce_adhoc_client_setting(
    parameter: dict,
    raw_value,
    *,
    experiment_topic_ids: set[int],
    experiment_topics_by_id: dict[int, str],
    opinion_groups_by_name: dict[str, dict[str, float | str]],
    age_classes_by_name: dict[str, dict[str, int | str]],
    leaning_names: set[str],
):
    param_type = str(parameter.get("type") or "string").strip().lower()
    if param_type == "mop_targets":
        if raw_value in (None, ""):
            return []
        if isinstance(raw_value, str):
            payload = json.loads(raw_value)
        else:
            payload = raw_value
        if not isinstance(payload, list):
            raise ValueError("MoP targets must be a list.")
        normalized = []
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("Each MoP target must be an object.")
            topic_id = int(entry.get("topic_id"))
            if topic_id not in experiment_topic_ids:
                raise ValueError("Selected topic is not part of this experiment.")
            target_group_name = str(entry.get("target_opinion_group") or "").strip()
            target_opinion = None
            if target_group_name:
                target_group = _lookup_named_option(
                    opinion_groups_by_name, target_group_name
                )
                if target_group is None:
                    raise ValueError("Selected opinion target group is not valid.")
                target_group_name = str(target_group["name"])
                target_opinion = float(target_group["value"])
            normalized.append(
                {
                    "topic_id": topic_id,
                    "topic_name": experiment_topics_by_id.get(topic_id, str(topic_id)),
                    "target_opinion": target_opinion,
                    "target_opinion_group": target_group_name,
                }
            )
        return normalized
    if param_type == "topic_targets":
        if raw_value in (None, ""):
            return []
        if isinstance(raw_value, str):
            payload = json.loads(raw_value)
        else:
            payload = raw_value
        if not isinstance(payload, list):
            raise ValueError("Topic targets must be a list.")
        normalized = []
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("Each topic target must be an object.")
            topic_id = int(entry.get("topic_id"))
            if topic_id not in experiment_topic_ids:
                raise ValueError("Selected topic is not part of this experiment.")
            target_group_name = str(entry.get("target_opinion_group") or "").strip()
            if target_group_name:
                target_group = _lookup_named_option(
                    opinion_groups_by_name, target_group_name
                )
                if target_group is None:
                    raise ValueError("Selected opinion target group is not valid.")
                target_group_name = str(target_group["name"])
                target_opinion = float(target_group["value"])
            else:
                target_opinion = float(entry.get("target_opinion"))
            if target_opinion < 0.0 or target_opinion > 1.0:
                raise ValueError("Target opinion must be in the [0, 1] range.")
            target_agent_opinion_group = str(
                entry.get("target_agent_opinion_group") or ""
            ).strip()
            target_agent_opinion_group_bounds = None
            if target_agent_opinion_group:
                target_agent_group = _lookup_named_option(
                    opinion_groups_by_name, target_agent_opinion_group
                )
                if target_agent_group is None:
                    raise ValueError(
                        "Selected target agent opinion group is not valid."
                    )
                target_agent_opinion_group = str(target_agent_group["name"])
                target_agent_opinion_group_bounds = {
                    "name": str(target_agent_group["name"]),
                    "lower_bound": float(target_agent_group["lower_bound"]),
                    "upper_bound": float(target_agent_group["upper_bound"]),
                    "value": float(target_agent_group["value"]),
                }
            target_leaning = str(entry.get("target_leaning") or "").strip()
            if target_leaning and _lookup_name(leaning_names, target_leaning) is None:
                raise ValueError("Selected political leaning is not valid.")
            if target_leaning:
                target_leaning = (
                    _lookup_name(leaning_names, target_leaning) or target_leaning
                )
            target_age_classes = []
            for age_name in entry.get("target_age_classes") or []:
                normalized_age_name = str(age_name).strip()
                age_class = _lookup_named_option(
                    age_classes_by_name, normalized_age_name
                )
                if age_class is None:
                    raise ValueError("Selected age class is not valid.")
                target_age_classes.append(age_class)
            normalized.append(
                {
                    "topic_id": topic_id,
                    "topic_name": experiment_topics_by_id.get(topic_id, str(topic_id)),
                    "target_opinion": target_opinion,
                    "target_opinion_group": target_group_name,
                    "target_agent_opinion_group": target_agent_opinion_group,
                    "target_agent_opinion_group_bounds": target_agent_opinion_group_bounds,
                    "target_leaning": target_leaning,
                    "target_age_classes": target_age_classes,
                }
            )
        return normalized
    if raw_value in (None, ""):
        default = parameter.get("default")
        if default not in (None, ""):
            raw_value = default
        elif parameter.get("required"):
            raise ValueError(f"{parameter.get('name', 'Setting')} is required.")
        else:
            return None
    if param_type in {"integer", "int"}:
        return int(raw_value)
    if param_type in {"float", "number"}:
        return float(str(raw_value).replace(",", "."))
    return str(raw_value)


def _build_adhoc_client_agent_settings(spec: dict, experiment) -> dict:
    topics = Exp_Topic.query.filter_by(exp_id=experiment.idexp).all()
    topic_ids = [topic.topic_id for topic in topics]
    topic_rows = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topic_ids)).all()
        if topic_ids
        else []
    )
    experiment_topics_by_id = {int(topic.id): topic.name for topic in topic_rows}
    experiment_topic_ids = set(experiment_topics_by_id)
    opinion_groups_by_name = {
        str(group.name): {
            "name": str(group.name),
            "lower_bound": float(group.lower_bound),
            "upper_bound": float(group.upper_bound),
            "value": (float(group.lower_bound) + float(group.upper_bound)) / 2.0,
        }
        for group in OpinionGroup.query.order_by(OpinionGroup.lower_bound.asc()).all()
    }
    age_classes_by_name = {
        str(age_class.name): {
            "name": str(age_class.name),
            "age_start": int(age_class.age_start),
            "age_end": int(age_class.age_end),
        }
        for age_class in AgeClass.query.order_by(AgeClass.age_start.asc()).all()
    }
    leaning_names = {
        str(leaning.leaning)
        for leaning in Leanings.query.order_by(Leanings.leaning.asc()).all()
    }

    settings: dict[str, object] = {}
    for parameter in spec.get("client_parameters", []):
        name = str(parameter.get("name") or "").strip()
        if not name:
            continue
        raw_value = request.form.get(f"agent_setting__{name}")
        value = _coerce_adhoc_client_setting(
            parameter,
            raw_value,
            experiment_topic_ids=experiment_topic_ids,
            experiment_topics_by_id=experiment_topics_by_id,
            opinion_groups_by_name=opinion_groups_by_name,
            age_classes_by_name=age_classes_by_name,
            leaning_names=leaning_names,
        )
        if value in (None, ""):
            continue
        if parameter.get("type") == "topic_targets" and not value:
            raise ValueError("Configure at least one propaganda topic target.")
        if parameter.get("type") == "mop_targets" and not value:
            raise ValueError("Configure at least one MoP campaign target.")
        settings[name] = value
    return settings


def _normalize_name_key(value: str) -> str:
    return str(value or "").strip().casefold()


def _lookup_named_option(options_by_name: dict[str, dict], raw_name: str):
    normalized = _normalize_name_key(raw_name)
    for name, value in options_by_name.items():
        if _normalize_name_key(name) == normalized:
            return value
    return None


def _lookup_name(options: set[str], raw_name: str) -> str | None:
    normalized = _normalize_name_key(raw_name)
    for value in options:
        if _normalize_name_key(value) == normalized:
            return value
    return None


def _sanitize_client_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._")
    return cleaned or "adhoc_client"


def _build_adhoc_client_initial_values(config: dict) -> dict:
    client = config.get("client", {}) if isinstance(config, dict) else {}
    metadata = client.get("metadata", {}) if isinstance(client, dict) else {}
    servers = client.get("servers", {}) if isinstance(client, dict) else {}
    simulation = client.get("simulation", {}) if isinstance(client, dict) else {}
    agent_settings = (
        client.get("agent_settings", {}) if isinstance(client, dict) else {}
    )
    days = int(simulation.get("days") or 30)
    infinite = bool(simulation.get("run_until_stopped"))
    llm_agents = client.get("agents", {}).get("llm_agents") or []
    llm_model = llm_agents[0] if llm_agents else ""
    return {
        "name": str(metadata.get("name") or client.get("client_id") or ""),
        "descr": str(metadata.get("description") or ""),
        "agent_type": str(
            metadata.get("agent_type_slug") or client.get("agent_type") or ""
        ),
        "population_id": metadata.get("population_id"),
        "llm_backend": str(servers.get("llm_backend") or "ollama"),
        "llm": str(servers.get("llm") or ""),
        "llm_api_key": str(servers.get("llm_api_key") or ""),
        "llm_max_tokens": servers.get("llm_max_tokens"),
        "llm_temperature": servers.get("llm_temperature"),
        "llm_agent": str(llm_model or ""),
        "days": days,
        "infinite_duration": infinite,
        "clock_mode": str(simulation.get("clock_mode") or "simulated"),
        "clock_timezone": str(simulation.get("clock_timezone") or "Europe/Rome"),
        "clock_feed_refresh": str(simulation.get("feed_refresh") or "hourly"),
        "agent_settings": agent_settings if isinstance(agent_settings, dict) else {},
    }


def _apply_adhoc_client_form_updates(config: dict, spec: dict, exp) -> dict:
    updated = json.loads(json.dumps(config))
    client = updated.setdefault("client", {})
    servers = client.setdefault("servers", {})
    simulation = client.setdefault("simulation", {})
    metadata = client.setdefault("metadata", {})
    agents = client.setdefault("agents", {})

    descr = (request.form.get("descr") or "").strip()
    metadata["description"] = descr

    infinite_duration = str(
        request.form.get("infinite_duration", "")
    ).strip().lower() in {"on", "true", "1", "yes"}
    days = int(request.form.get("days") or simulation.get("days") or 30)
    days = max(days, 1)
    config_days = 365000 if infinite_duration else days
    max_ticks = None if infinite_duration else config_days * 24

    simulation["days"] = config_days
    simulation["run_until_stopped"] = infinite_duration
    simulation["clock_mode"] = (
        (request.form.get("clock_mode") or simulation.get("clock_mode") or "simulated")
        .strip()
        .lower()
    )
    simulation["clock_timezone"] = (
        request.form.get("clock_timezone")
        or simulation.get("clock_timezone")
        or "Europe/Rome"
    ).strip()
    simulation["feed_refresh"] = (
        request.form.get("clock_feed_refresh")
        or simulation.get("feed_refresh")
        or "hourly"
    ).strip()
    client["max_ticks"] = max_ticks

    current_llm_model = ""
    llm_agents = agents.get("llm_agents") or []
    if llm_agents:
        current_llm_model = str(llm_agents[0] or "")
    llm_defaults = _adhoc_llm_defaults_for_experiment(exp.idexp)
    if spec.get("requires_llm"):
        llm = (request.form.get("llm") or "").strip() or str(
            servers.get("llm") or llm_defaults["llm"]
        )
        llm_api_key = (request.form.get("llm_api_key") or "").strip() or str(
            servers.get("llm_api_key") or llm_defaults["llm_api_key"]
        )
        llm_max_tokens = int(
            request.form.get("llm_max_tokens")
            or servers.get("llm_max_tokens")
            or llm_defaults["llm_max_tokens"]
        )
        llm_temperature = float(
            request.form.get("llm_temperature")
            or servers.get("llm_temperature")
            or llm_defaults["llm_temperature"]
        )
        llm_model = (request.form.get("llm_agent") or "").strip() or current_llm_model
        llm_backend = (
            request.form.get("llm_backend") or servers.get("llm_backend") or "ollama"
        ).strip()
        servers["llm"] = llm
        servers["llm_api_key"] = llm_api_key
        servers["llm_max_tokens"] = llm_max_tokens
        servers["llm_temperature"] = llm_temperature
        servers["llm_backend"] = llm_backend
        agents["llm_agents"] = [llm_model] if llm_model else []

    client["agent_settings"] = _build_adhoc_client_agent_settings(spec, exp)
    return updated


def _adhoc_activity_profiles_for_population(population_id: int) -> dict[str, str]:
    agent_links = Agent_Population.query.filter_by(population_id=population_id).all()
    agent_ids = [link.agent_id for link in agent_links]
    if not agent_ids:
        return {"Always On": ",".join(str(slot) for slot in range(24))}

    profile_ids = [
        profile_id
        for (profile_id,) in db.session.query(Agent.activity_profile)
        .filter(Agent.id.in_(agent_ids))
        .all()
        if profile_id is not None
    ]
    profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_(profile_ids))
        .all()
        if profile_ids
        else []
    )
    if not profiles:
        return {"Always On": ",".join(str(slot) for slot in range(24))}
    return {profile.name: profile.hours for profile in profiles}


def _export_adhoc_population_json(population, spec: dict, *, owner: str | None) -> dict:
    agent_links = Agent_Population.query.filter_by(population_id=population.id).all()
    agents = [Agent.query.filter_by(id=link.agent_id).first() for link in agent_links]
    agents = [agent for agent in agents if agent is not None]
    ext_entries = (
        Agent_Ext.query.filter(
            Agent_Ext.agent_id.in_([agent.id for agent in agents])
        ).all()
        if agents
        else []
    )
    ext_map: dict[int, dict[str, str]] = {}
    for entry in ext_entries:
        ext_map.setdefault(entry.agent_id, {})[entry.feature_name] = entry.feature_value

    payload = {"agents": []}
    for agent in agents:
        activity_profile_obj = (
            db.session.query(ActivityProfile)
            .filter_by(id=agent.activity_profile)
            .first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )
        feature_values = ext_map.get(agent.id, {})
        daily_budget = feature_values.get(
            "daily_budget", agent.daily_activity_level or 1
        )
        parameters = {
            key: value for key, value in feature_values.items() if key != "daily_budget"
        }
        payload["agents"].append(
            {
                "name": agent.name,
                "username": agent.name,
                "email": f"{agent.name}@ysocial.it",
                "password": agent.name,
                "agent_type": spec["agent_type"],
                "activity_profile": activity_profile_name,
                "daily_budget": float(daily_budget),
                "language": agent.language or "en",
                "owner": owner,
                "parameters": parameters,
            }
        )
    return payload


def _adhoc_llm_defaults_for_experiment(idexp):
    defaults = {
        "llm": "http://127.0.0.1:11434/v1",
        "llm_api_key": "NULL",
        "llm_max_tokens": -1,
        "llm_temperature": 1.5,
        "llm_v_agent": "qwen3-vl:8b",
        "llm_v": "http://127.0.0.1:11434/v1",
        "llm_v_api_key": "NULL",
        "llm_v_max_tokens": 300,
        "llm_v_temperature": 0.5,
    }
    latest_client = (
        Client.query.filter_by(id_exp=idexp).order_by(Client.id.desc()).first()
    )
    if latest_client is None:
        return defaults
    defaults.update(
        {
            "llm": latest_client.llm or defaults["llm"],
            "llm_api_key": latest_client.llm_api_key or defaults["llm_api_key"],
            "llm_max_tokens": (
                latest_client.llm_max_tokens
                if latest_client.llm_max_tokens is not None
                else defaults["llm_max_tokens"]
            ),
            "llm_temperature": (
                latest_client.llm_temperature
                if latest_client.llm_temperature is not None
                else defaults["llm_temperature"]
            ),
            "llm_v_agent": latest_client.llm_v_agent or defaults["llm_v_agent"],
            "llm_v": latest_client.llm_v or defaults["llm_v"],
            "llm_v_api_key": latest_client.llm_v_api_key or defaults["llm_v_api_key"],
            "llm_v_max_tokens": (
                latest_client.llm_v_max_tokens
                if latest_client.llm_v_max_tokens is not None
                else defaults["llm_v_max_tokens"]
            ),
            "llm_v_temperature": (
                latest_client.llm_v_temperature
                if latest_client.llm_v_temperature is not None
                else defaults["llm_v_temperature"]
            ),
        }
    )
    return defaults


def _collect_population_agent_attributes(population_id):
    """Return normalized per-agent attributes for a population, skipping broken rows."""
    agent_links = Agent_Population.query.filter_by(population_id=population_id).all()
    agents = []
    for link in agent_links:
        agent = Agent.query.filter_by(id=link.agent_id).first()
        if agent is not None:
            agents.append(agent)

    return {
        "agents": agents,
        "political_leanings": sorted(
            {a.leaning for a in agents if getattr(a, "leaning", None) not in (None, "")}
        ),
        "ages": sorted(
            {int(a.age) for a in agents if getattr(a, "age", None) not in (None, "")}
        ),
        "toxicity_levels": sorted(
            {
                a.toxicity
                for a in agents
                if getattr(a, "toxicity", None) not in (None, "")
            }
        ),
        "languages": sorted(
            {
                a.language
                for a in agents
                if getattr(a, "language", None) not in (None, "")
            }
        ),
        "llm_agents": sorted(
            {a.ag_type for a in agents if getattr(a, "ag_type", None) not in (None, "")}
        ),
        "education_levels": sorted(
            {
                a.education_level
                for a in agents
                if getattr(a, "education_level", None) not in (None, "")
            }
        ),
    }


def _apply_population_attributes_to_client_config(config, population_id):
    summary = _collect_population_agent_attributes(population_id)
    ages = summary["ages"]
    if not summary["agents"] or not ages:
        return False

    config["agents"]["political_leanings"] = summary["political_leanings"]
    config["agents"]["age"]["min"] = min(ages)
    config["agents"]["age"]["max"] = max(ages)
    config["agents"]["toxicity_levels"] = summary["toxicity_levels"]
    config["agents"]["languages"] = summary["languages"]
    config["agents"]["llm_agents"] = summary["llm_agents"]
    config["agents"]["education_levels"] = summary["education_levels"]
    config["agents"]["round_actions"] = {"min": 1, "max": 3}
    config["agents"]["n_interests"] = {"min": 1, "max": 5}
    return True


def _build_client_creation_context(idexp, recsys_mode):
    """Build the shared context used by client creation pages."""
    ensure_population_username_type_column()
    exp = Exps.query.filter_by(idexp=idexp).first()

    pop_exp_associations = Population_Experiment.query.filter_by(id_exp=idexp).all()
    population_ids = [pe.id_population for pe in pop_exp_associations]

    pops = (
        Population.query.filter(~Population.id.in_(population_ids)).all()
        if population_ids
        else Population.query.all()
    )
    all_unassigned_pops = list(pops)
    pops = [p for p in pops if population_matches_platform(p, exp.platform_type)]
    incompatible_population_count = max(0, len(all_unassigned_pops) - len(pops))

    topics = Exp_Topic.query.filter_by(exp_id=idexp).all()
    topics_ids = [t.topic_id for t in topics]
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topics_list = [{"id": t.id, "name": t.name} for t in topics_objs]

    llm_agents_enabled = _experiment_uses_llm_agents(exp) if exp is not None else True

    crecsys_all = Content_Recsys.query.all()
    frecsys_all = Follow_Recsys.query.all()
    crecsys = [r for r in crecsys_all if r.enabled and recsys_mode in r.enabled]
    frecsys = [r for r in frecsys_all if r.enabled and recsys_mode in r.enabled]

    experiment_clock = {
        "mode": "simulated",
        "timezone": "Europe/Rome",
        "feed_refresh": "hourly",
    }
    experiment_embedding_settings = {
        "service": "",
        "host": "",
        "model": "",
    }
    experiment_memory_enabled = False
    memory_configuration_supported = False
    experiment_opinion_dynamics_enabled = False
    exp_llm_defaults = {
        "llm": "http://127.0.0.1:11434/v1",
        "llm_api_key": "NULL",
        "llm_max_tokens": -1,
        "llm_temperature": 1.5,
        "llm_v_agent": "qwen3-vl:8b",
        "llm_v": "http://127.0.0.1:11434/v1",
        "llm_v_api_key": "NULL",
        "llm_v_max_tokens": 300,
        "llm_v_temperature": 0.5,
    }

    if exp is not None:
        try:
            from y_web.src.system.path_utils import get_writable_path

            writable_base = get_writable_path()
            if "database_server.db" in exp.db_name:
                exp_uid = exp.db_name.split(os.sep)[1]
            else:
                exp_uid = exp.db_name.removeprefix("experiments_")
            config_path = os.path.join(
                writable_base,
                "y_web",
                "experiments",
                exp_uid,
                (
                    "server_config.json"
                    if getattr(exp, "simulator_type", "Standard") == "HPC"
                    else "config_server.json"
                ),
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as config_file:
                    experiment_config = json.load(config_file)
                raw_clock = experiment_config.get("clock", {}) or {}
                experiment_clock["mode"] = raw_clock.get("mode", "simulated")
                experiment_clock["timezone"] = raw_clock.get("timezone", "Europe/Rome")
                experiment_clock["feed_refresh"] = raw_clock.get(
                    "feed_refresh", "hourly"
                )
                experiment_memory_enabled = _memory_enabled_for_client_creation(exp)
                raw_embeddings = experiment_config.get("memory_embeddings", {}) or {}
                if isinstance(raw_embeddings, dict):
                    experiment_embedding_settings["service"] = str(
                        raw_embeddings.get("service") or ""
                    ).strip()
                    experiment_embedding_settings["host"] = str(
                        raw_embeddings.get("host") or ""
                    ).strip()
                    experiment_embedding_settings["model"] = str(
                        raw_embeddings.get("model") or ""
                    ).strip()
        except Exception:
            pass

    if exp is not None:
        experiment_opinion_dynamics_enabled = (
            _opinion_dynamics_enabled_for_client_creation(exp)
        )
        memory_configuration_supported = bool(llm_agents_enabled)

    if exp is not None and getattr(exp, "platform_type", "microblogging") == "forum":
        latest_client = (
            Client.query.filter_by(id_exp=idexp).order_by(Client.id.desc()).first()
        )
        if latest_client is not None:
            exp_llm_defaults.update(
                {
                    "llm": latest_client.llm or exp_llm_defaults["llm"],
                    "llm_api_key": latest_client.llm_api_key
                    or exp_llm_defaults["llm_api_key"],
                    "llm_max_tokens": (
                        latest_client.llm_max_tokens
                        if latest_client.llm_max_tokens is not None
                        else exp_llm_defaults["llm_max_tokens"]
                    ),
                    "llm_temperature": (
                        latest_client.llm_temperature
                        if latest_client.llm_temperature is not None
                        else exp_llm_defaults["llm_temperature"]
                    ),
                    "llm_v_agent": latest_client.llm_v_agent
                    or exp_llm_defaults["llm_v_agent"],
                    "llm_v": latest_client.llm_v or exp_llm_defaults["llm_v"],
                    "llm_v_api_key": latest_client.llm_v_api_key
                    or exp_llm_defaults["llm_v_api_key"],
                    "llm_v_max_tokens": (
                        latest_client.llm_v_max_tokens
                        if latest_client.llm_v_max_tokens is not None
                        else exp_llm_defaults["llm_v_max_tokens"]
                    ),
                    "llm_v_temperature": (
                        latest_client.llm_v_temperature
                        if latest_client.llm_v_temperature is not None
                        else exp_llm_defaults["llm_v_temperature"]
                    ),
                }
            )

    return {
        "experiment": exp,
        "populations": pops,
        "incompatible_population_count": incompatible_population_count,
        "crecsys": crecsys,
        "frecsys": frecsys,
        "llm_agents_enabled": llm_agents_enabled,
        "topics": topics_list,
        "experiment_clock": experiment_clock,
        "experiment_memory_enabled": experiment_memory_enabled,
        "memory_configuration_supported": memory_configuration_supported,
        "experiment_opinion_dynamics_enabled": experiment_opinion_dynamics_enabled,
        "experiment_embedding_settings": experiment_embedding_settings,
        "exp_llm_defaults": exp_llm_defaults,
    }


@clientsr.route("/admin/clients/<idexp>")
@login_required
def clients(idexp):
    """Dispatch client creation to the route dedicated to the experiment modality."""
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=idexp).first()
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    experiment_mode = _get_experiment_mode(exp)
    if experiment_mode == "hpc":
        return redirect(url_for("clientsr.clients_hpc", idexp=idexp))
    if experiment_mode == "forum":
        return redirect(url_for("clientsr.clients_forum", idexp=idexp))
    return redirect(url_for("clientsr.clients_standard", idexp=idexp))


@clientsr.route("/admin/clients_standard/<idexp>")
@login_required
def clients_standard(idexp):
    """Render the standard microblogging client creation page."""
    check_privileges(current_user.username)

    context = _build_client_creation_context(idexp, "Standard")
    exp = context["experiment"]
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if getattr(exp, "simulator_type", "Standard") == "HPC":
        return redirect(url_for("clientsr.clients_hpc", idexp=idexp))
    if exp.platform_type == "forum":
        return redirect(url_for("clientsr.clients_forum", idexp=idexp))
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before creating clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    return render_template("admin/clients.html", **context)


@clientsr.route("/admin/clients_forum/<idexp>")
@login_required
def clients_forum(idexp):
    """Render the dedicated forum client creation page."""
    check_privileges(current_user.username)

    context = _build_client_creation_context(idexp, "Standard")
    exp = context["experiment"]
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if getattr(exp, "simulator_type", "Standard") == "HPC":
        return redirect(url_for("clientsr.clients_hpc", idexp=idexp))
    if exp.platform_type != "forum":
        return redirect(url_for("clientsr.clients_standard", idexp=idexp))
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before creating clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    return render_template("admin/clients_forum.html", **context)


@clientsr.route("/admin/clients_hpc/<idexp>")
@login_required
def clients_hpc(idexp):
    """Render the dedicated HPC client creation page."""
    check_privileges(current_user.username)

    context = _build_client_creation_context(idexp, "HPC")
    exp = context["experiment"]
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if getattr(exp, "simulator_type", "Standard") != "HPC":
        if exp.platform_type == "forum":
            return redirect(url_for("clientsr.clients_forum", idexp=idexp))
        return redirect(url_for("clientsr.clients_standard", idexp=idexp))
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before creating clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    context["embedded_vllm_available"] = bool(is_vllm_installed())
    return render_template("admin/clients_hpc.html", **context)


@clientsr.route("/admin/clients_adhoc/<idexp>")
@login_required
def clients_adhoc(idexp):
    """Render the dedicated ad hoc agent client creation page."""
    check_privileges(current_user.username)

    context = _build_client_creation_context(idexp, "Standard")
    exp = context["experiment"]
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if exp.is_remote == 1:
        flash(
            "Ad hoc agent clients are not available for remote experiments.", "warning"
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    if not _experiment_uses_llm_agents(exp):
        flash(
            "Ad hoc agent clients are not available for rule-based experiments.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before creating clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    agent_specs = _adhoc_agent_specs()
    if not context["experiment_opinion_dynamics_enabled"]:
        agent_specs = [
            spec for spec in agent_specs if not spec.get("requires_opinion_dynamics")
        ]
    if not agent_specs:
        flash("No ad hoc agent plugins are currently installed.", "warning")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    context.update(
        {
            "adhoc_agent_specs": agent_specs,
            "adhoc_populations_by_type": _adhoc_population_choices(idexp, agent_specs),
            "adhoc_experiment_topics": context.get("topics", []),
            "adhoc_opinion_groups": [
                {
                    "name": group.name,
                    "lower_bound": group.lower_bound,
                    "upper_bound": group.upper_bound,
                    "value": (group.lower_bound + group.upper_bound) / 2.0,
                }
                for group in OpinionGroup.query.order_by(
                    OpinionGroup.lower_bound.asc()
                ).all()
            ],
            "adhoc_age_classes": [
                {
                    "name": age_class.name,
                    "age_start": age_class.age_start,
                    "age_end": age_class.age_end,
                }
                for age_class in AgeClass.query.order_by(AgeClass.age_start.asc()).all()
            ],
            "adhoc_leanings": [
                {
                    "name": leaning.leaning,
                }
                for leaning in Leanings.query.order_by(Leanings.leaning.asc()).all()
            ],
            "adhoc_form_mode": "create",
            "adhoc_form_action": "/admin/create_adhoc_client",
            "adhoc_submit_label": "Create",
            "adhoc_form_title": "New AdHoc Agent Client",
            "adhoc_form_breadcrumb": "Create New AdHoc Agent Client",
            "adhoc_form_readonly_identity": False,
            "adhoc_initial_client": None,
        }
    )
    return render_template("admin/clients_adhoc.html", **context)


@clientsr.route("/admin/edit_adhoc_client/<int:idexp>/<path:client_key>")
@login_required
def edit_adhoc_client(idexp, client_key):
    """Render the edit form for an existing ad hoc agent client."""
    check_privileges(current_user.username)

    context = _build_client_creation_context(idexp, "Standard")
    exp = context["experiment"]
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if exp.is_remote == 1:
        flash(
            "Ad hoc agent clients are not available for remote experiments.", "warning"
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    if not _experiment_uses_llm_agents(exp):
        flash(
            "Ad hoc agent clients are not available for rule-based experiments.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before modifying clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    try:
        config_path = config_path_for_client(exp, client_key)
    except FileNotFoundError:
        flash("Ad hoc client configuration not found.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    config = read_adhoc_json(config_path)
    if not isinstance(config, dict):
        flash("Ad hoc client configuration is invalid.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    initial_client = _build_adhoc_client_initial_values(config)
    selected_agent_type = str(initial_client.get("agent_type") or "")
    selected_population_id = initial_client.get("population_id")
    agent_specs = _adhoc_agent_specs()
    if not context["experiment_opinion_dynamics_enabled"]:
        agent_specs = [
            spec for spec in agent_specs if not spec.get("requires_opinion_dynamics")
        ]
    spec = _find_adhoc_agent_spec(selected_agent_type)
    if spec is None:
        flash("The referenced ad hoc agent type is no longer available.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    population_choices = _adhoc_population_choices(idexp, agent_specs)
    if selected_population_id and spec:
        existing_choices = population_choices.get(spec["slug"], [])
        if not any(
            str(item.get("id")) == str(selected_population_id)
            for item in existing_choices
        ):
            population = Population.query.filter_by(id=selected_population_id).first()
            if population is not None:
                existing_choices.append(
                    {
                        "id": population.id,
                        "name": population.name,
                        "descr": population.descr or "",
                    }
                )
                population_choices[spec["slug"]] = existing_choices

    context.update(
        {
            "adhoc_agent_specs": agent_specs,
            "adhoc_populations_by_type": population_choices,
            "adhoc_experiment_topics": context.get("topics", []),
            "adhoc_opinion_groups": [
                {
                    "name": group.name,
                    "lower_bound": group.lower_bound,
                    "upper_bound": group.upper_bound,
                    "value": (group.lower_bound + group.upper_bound) / 2.0,
                }
                for group in OpinionGroup.query.order_by(
                    OpinionGroup.lower_bound.asc()
                ).all()
            ],
            "adhoc_age_classes": [
                {
                    "name": age_class.name,
                    "age_start": age_class.age_start,
                    "age_end": age_class.age_end,
                }
                for age_class in AgeClass.query.order_by(AgeClass.age_start.asc()).all()
            ],
            "adhoc_leanings": [
                {"name": leaning.leaning}
                for leaning in Leanings.query.order_by(Leanings.leaning.asc()).all()
            ],
            "adhoc_form_mode": "edit",
            "adhoc_form_action": f"/admin/update_adhoc_client/{idexp}/{client_key}",
            "adhoc_submit_label": "Update",
            "adhoc_form_title": "Update AdHoc Agent Client",
            "adhoc_form_breadcrumb": "Update AdHoc Agent Client",
            "adhoc_form_readonly_identity": True,
            "adhoc_initial_client": initial_client,
        }
    )
    return render_template("admin/clients_adhoc.html", **context)


@clientsr.route("/admin/create_adhoc_client", methods=["POST"])
@login_required
def create_adhoc_client():
    """Create plugin-runtime config files for an ad hoc agent client."""
    check_privileges(current_user.username)

    exp_id = request.form.get("id_exp")
    exp = Exps.query.filter_by(idexp=exp_id).first()
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before creating clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=exp_id))

    name = (request.form.get("name") or "").strip()
    descr = (request.form.get("descr") or "").strip()
    agent_type_slug = (request.form.get("agent_type") or "").strip()
    population_id = request.form.get("population_id")
    spec = _find_adhoc_agent_spec(agent_type_slug)

    if not name:
        flash("Client name is required.", "error")
        return redirect(url_for("clientsr.clients_adhoc", idexp=exp_id))
    if spec is None:
        flash("Select a valid ad hoc agent type.", "error")
        return redirect(url_for("clientsr.clients_adhoc", idexp=exp_id))
    if spec.get(
        "requires_opinion_dynamics"
    ) and not _opinion_dynamics_enabled_for_client_creation(exp):
        flash(
            "The selected ad hoc agent type requires opinion dynamics to be enabled for this experiment.",
            "error",
        )
        return redirect(url_for("clientsr.clients_adhoc", idexp=exp_id))

    population = Population.query.filter_by(id=population_id).first()
    if population is None or population.pop_type not in spec["accepted_slugs"]:
        flash(
            "Select a population compatible with the chosen ad hoc agent type.", "error"
        )
        return redirect(url_for("clientsr.clients_adhoc", idexp=exp_id))

    agent_links = Agent_Population.query.filter_by(population_id=population.id).all()
    if not agent_links:
        flash("The selected population does not contain any agents.", "error")
        return redirect(url_for("clientsr.clients_adhoc", idexp=exp_id))

    from y_web.src.system.path_utils import get_writable_path

    writable_base = get_writable_path()
    exp_folder = os.path.join(
        writable_base, "y_web", "experiments", _get_experiment_folder_name(exp)
    )
    os.makedirs(exp_folder, exist_ok=True)

    safe_client_name = _sanitize_client_filename(name)
    safe_agent_slug = _sanitize_client_filename(spec["slug"])
    file_stem = f"{safe_agent_slug}_{safe_client_name}"

    agents_filename = f"{exp_folder}{os.sep}adhoc_agents_{file_stem}.json"
    config_filename = f"{exp_folder}{os.sep}adhoc_client_{file_stem}.json"

    if os.path.exists(config_filename):
        flash(
            f"An ad hoc client config named '{safe_client_name}' already exists.",
            "error",
        )
        return redirect(url_for("clientsr.clients_adhoc", idexp=exp_id))

    activity_profiles = _adhoc_activity_profiles_for_population(population.id)
    population_payload = _export_adhoc_population_json(
        population, spec, owner=exp.owner
    )

    infinite_duration = str(
        request.form.get("infinite_duration", "")
    ).strip().lower() in {
        "on",
        "true",
        "1",
        "yes",
    }
    days = int(request.form.get("days") or 30)
    days = max(days, 1)
    config_days = 365000 if infinite_duration else days
    max_ticks = None if infinite_duration else config_days * 24

    llm_defaults = _adhoc_llm_defaults_for_experiment(exp.idexp)
    llm = (request.form.get("llm") or "").strip() or llm_defaults["llm"]
    llm_api_key = (request.form.get("llm_api_key") or "").strip() or llm_defaults[
        "llm_api_key"
    ]
    llm_max_tokens = int(
        request.form.get("llm_max_tokens") or llm_defaults["llm_max_tokens"]
    )
    llm_temperature = float(
        request.form.get("llm_temperature") or llm_defaults["llm_temperature"]
    )
    llm_model = (request.form.get("llm_agent") or "").strip()
    try:
        agent_settings = _build_adhoc_client_agent_settings(spec, exp)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("clientsr.clients_adhoc", idexp=exp_id))

    client_payload = {
        "database": {
            "sqlite_path": (
                os.path.join(exp_folder, "database_server.db")
                if get_db_type() == "sqlite"
                else None
            ),
            "sqlalchemy_url": (
                None
                if get_db_type() == "sqlite"
                else current_app.config["SQLALCHEMY_BINDS"]["db_exp"]
            ),
            "poll_interval_seconds": 1.0,
        },
        "client": {
            "client_id": safe_client_name,
            "agent_type": spec["agent_type"],
            "agents_json_path": agents_filename,
            "servers": {
                "llm_backend": (request.form.get("llm_backend") or "ollama").strip(),
                "llm": llm,
                "llm_api_key": llm_api_key,
                "llm_max_tokens": llm_max_tokens,
                "llm_temperature": llm_temperature,
                "llm_v": llm_defaults["llm_v"],
                "llm_v_api_key": llm_defaults["llm_v_api_key"],
                "llm_v_max_tokens": llm_defaults["llm_v_max_tokens"],
                "llm_v_temperature": llm_defaults["llm_v_temperature"],
                "api": f"http://{exp.server}:{exp.port}/",
            },
            "simulation": {
                "days": config_days,
                "slots": 24,
                "population_json_path": agents_filename,
                "activity_profiles": activity_profiles,
                "run_until_stopped": infinite_duration,
                "clock_mode": (request.form.get("clock_mode") or "simulated")
                .strip()
                .lower(),
                "clock_timezone": (
                    request.form.get("clock_timezone") or "Europe/Rome"
                ).strip(),
                "feed_refresh": (
                    request.form.get("clock_feed_refresh") or "hourly"
                ).strip(),
            },
            "agents": {
                "llm_agents": [llm_model] if llm_model else [],
                "llm_v_agent": llm_defaults["llm_v_agent"],
                "reading_from_follower_ratio": float(
                    request.form.get("reading_from_follower_ratio") or 0.6
                ),
                "max_length_thread_reading": int(
                    request.form.get("max_length_thread_reading") or 10
                ),
            },
            "agent_settings": agent_settings,
            "recent_posts_limit": 25,
            "max_ticks": max_ticks,
            "metadata": {
                "name": name,
                "description": descr,
                "population": population.name,
                "population_id": population.id,
                "population_name": population.name,
                "agent_type_slug": spec["slug"],
                "agent_type_display": spec["display_name"],
                "plugin_repository": spec["repo_name"],
            },
        },
    }

    with open(agents_filename, "w", encoding="utf-8") as handle:
        json.dump(population_payload, handle, indent=2)
    with open(config_filename, "w", encoding="utf-8") as handle:
        json.dump(client_payload, handle, indent=2)
    initialize_state_for_config(config_filename)

    flash(f"Ad hoc client configuration '{name}' saved.", "success")
    return redirect(url_for("experiments.experiment_details", uid=exp_id))


@clientsr.route(
    "/admin/update_adhoc_client/<int:idexp>/<path:client_key>", methods=["POST"]
)
@login_required
def update_adhoc_client(idexp, client_key):
    """Update an existing ad hoc client configuration in place."""
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=idexp).first()
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before modifying clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    try:
        config_path = config_path_for_client(exp, client_key)
    except FileNotFoundError:
        flash("Ad hoc client configuration not found.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    config = read_adhoc_json(config_path)
    if not isinstance(config, dict):
        flash("Ad hoc client configuration is invalid.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    metadata = (config.get("client", {}) or {}).get("metadata", {}) or {}
    agent_type_slug = str(
        metadata.get("agent_type_slug")
        or (config.get("client", {}) or {}).get("agent_type")
        or ""
    ).strip()
    spec = _find_adhoc_agent_spec(agent_type_slug)
    if spec is None:
        flash("The ad hoc agent type is no longer available.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    if spec.get(
        "requires_opinion_dynamics"
    ) and not _opinion_dynamics_enabled_for_client_creation(exp):
        flash(
            "The selected ad hoc agent type requires opinion dynamics to remain enabled for this experiment.",
            "error",
        )
        return redirect(
            url_for("clientsr.edit_adhoc_client", idexp=idexp, client_key=client_key)
        )

    try:
        updated = _apply_adhoc_client_form_updates(config, spec, exp)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(
            url_for("clientsr.edit_adhoc_client", idexp=idexp, client_key=client_key)
        )

    write_adhoc_json(config_path, updated)
    initialize_state_for_config(config_path)
    flash(
        "Ad hoc client settings updated. Running clients will pick up the changes on the next round.",
        "success",
    )
    return redirect(url_for("experiments.experiment_details", uid=idexp))


def generate_hpc_client_config(
    client_name,
    namespace,
    llm_backend,
    llm_config,
    llm_v_config,
    simulation_config,
    agents_config,
    logging_config,
    enable_sentiment,
    emotion_annotation,
    enable_toxicity,
    perspective_api_key,
    server_address=None,
    server_port=None,
):
    """Generate client configuration for HPC simulator type.

    Args:
        client_name: Name of the client
        namespace: Experiment name (not db_name)
        server_address: Server address for remote experiments
        server_port: Server port for remote experiments
        ...
    """
    config = {
        "client_name": client_name,
        "namespace": namespace,
        "server": {"address": server_address, "port": server_port},
        "llm": llm_config,
        "simulation": simulation_config,
        "agents": agents_config,
        "logging": logging_config,
    }

    # Only include llm_v in config if it's provided (VLLM: when Image Transcription is enabled; Ollama: always included)
    if llm_v_config is not None:
        config["llm_v"] = llm_v_config

    return config


def create_hpc_client(exp, name, descr, population_id, form_data):
    """Create an HPC client with comprehensive configuration from form and server config."""
    import json
    import shutil

    from y_web.src.system.path_utils import get_resource_path, get_writable_path

    BASE_DIR = get_writable_path()

    # Get population
    population = Population.query.filter_by(id=population_id).first()
    if not population:
        flash("Population not found")
        return redirect(request.referrer)

    # Check if client name already exists
    if Client.query.filter_by(name=name).first():
        flash("Client name already exists.", "error")
        return redirect(request.referrer)

    # Extract all form data
    days = int(form_data.get("days", "3"))
    percentage_new_agents_iteration = float(
        form_data.get("percentage_new_agents_iteration", "0.0")
    )
    percentage_removed_agents_iteration = float(
        form_data.get("percentage_removed_agents_iteration", "0.0")
    )
    max_length_thread_reading = int(form_data.get("max_length_thread_reading", "5"))
    reading_from_follower_ratio = float(
        form_data.get("reading_from_follower_ratio", "0.8")
    )
    probability_of_daily_follow = float(
        form_data.get("probability_of_daily_follow", "0.1")
    )
    probability_of_secondary_follow = float(
        form_data.get("probability_of_secondary_follow", "0.1")
    )
    attention_window = int(form_data.get("attention_window", "336"))
    visibility_rounds = int(form_data.get("visibility_rounds", "36"))
    batch_size = int(form_data.get("batch_size", "100"))
    recommendations_default_limit = int(
        form_data.get("recommendations_default_limit", "12")
    )
    memory_enabled = form_data.get("memory_enabled") in {"on", "true", "1", "yes"}
    memory_pair_limit = int(form_data.get("memory_pair_limit", "5"))
    memory_prompt_max_chars = int(form_data.get("memory_prompt_max_chars", "1600"))
    memory_social_decay_lambda = float(
        form_data.get("memory_social_decay_lambda", "0.05")
    )
    memory_social_corruption_rate = float(
        form_data.get("memory_social_corruption_rate", "0.02")
    )
    memory_social_resummarize_every_events = int(
        form_data.get("memory_social_resummarize_every_events", "4")
    )
    memory_thread_decay_lambda = float(
        form_data.get("memory_thread_decay_lambda", "0.03")
    )
    memory_thread_corruption_rate = float(
        form_data.get("memory_thread_corruption_rate", "0.01")
    )
    memory_thread_resummarize_every_events = int(
        form_data.get("memory_thread_resummarize_every_events", "4")
    )
    memory_evidence_tail_max = int(form_data.get("memory_evidence_tail_max", "8"))
    memory_digest_update_cadence_rounds = int(
        form_data.get("memory_digest_update_cadence_rounds", "3")
    )
    memory_digest_events_limit = int(form_data.get("memory_digest_events_limit", "80"))
    memory_cold_start_window = int(form_data.get("memory_cold_start_window", "5"))
    memory_semantic_enabled = form_data.get("memory_semantic_enabled") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_search_k = int(form_data.get("memory_search_k", "8"))
    memory_search_max_chars = int(form_data.get("memory_search_max_chars", "900"))
    memory_search_time_window_rounds = int(
        form_data.get("memory_search_time_window_rounds", "40")
    )
    memory_tier_a_max_chars = int(form_data.get("memory_tier_a_max_chars", "350"))
    memory_tier_b_max_chars = int(form_data.get("memory_tier_b_max_chars", "900"))
    memory_tier_c_max_chars = int(form_data.get("memory_tier_c_max_chars", "900"))
    memory_total_max_chars = int(form_data.get("memory_total_max_chars", "2200"))
    memory_tier_c_uncertainty_threshold = float(
        form_data.get("memory_tier_c_uncertainty_threshold", "0.45")
    )
    memory_reflection_cadence_rounds = int(
        form_data.get("memory_reflection_cadence_rounds", "3")
    )
    memory_reflection_min_events = int(
        form_data.get("memory_reflection_min_events", "12")
    )
    memory_reflection_trigger_importance_sum = float(
        form_data.get("memory_reflection_trigger_importance_sum", "3.5")
    )
    memory_reflection_max_items_per_run = int(
        form_data.get("memory_reflection_max_items_per_run", "60")
    )
    memory_embedding_model = str(
        form_data.get("memory_embedding_model", "snowflake-arctic-embed:110m")
    ).strip()
    memory_embedding_async = form_data.get("memory_embedding_async") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_importance_mode = str(
        form_data.get("memory_importance_mode", "heuristic_then_batch_llm")
    ).strip()

    if not memory_semantic_enabled:
        memory_embedding_async = False

    experiment_memory_enabled = _memory_enabled_for_client_creation(exp)
    if not experiment_memory_enabled:
        memory_enabled = False
        memory_semantic_enabled = False
        memory_embedding_async = False

    # Follow action decay parameters
    follow_decay_enabled = form_data.get("follow_decay_enabled") == "on"
    follow_decay_function = form_data.get("follow_decay_function", "exponential")
    follow_decay_half_life = int(form_data.get("follow_decay_half_life", "168"))
    follow_decay_rate = float(form_data.get("follow_decay_rate", "0.01"))
    follow_decay_min_ratio = float(form_data.get("follow_decay_min_ratio", "0.1"))

    # Action likelihoods
    post = float(form_data.get("post", "3.0"))
    share = float(form_data.get("share", "1.0"))
    image = float(form_data.get("image", "0.0"))
    comment = float(form_data.get("comment", "5.0"))
    read = float(form_data.get("read", "2.0"))
    news = float(form_data.get("news", "0.0"))
    search = float(form_data.get("search", "5.0"))
    vote = float(form_data.get("vote", "0.0"))
    share_link = float(form_data.get("share_link", "0.0"))
    # Follow action - default 0.0 matches form default. Previously hardcoded at 0.1,
    # now configurable via form field
    follow = float(form_data.get("follow", "0.0"))

    # RecSys
    crecsys = form_data.get("recsys_type", "random")
    if crecsys == "ContentRecSys":
        crecsys = "random"
    frecsys = form_data.get("frecsys_type", "random")
    if frecsys == "FollowRecSys":
        frecsys = "random"

    # Agent archetypes
    enable_archetypes = form_data.get("enable_archetypes") == "on"
    agent_downcast = form_data.get("agent_downcast") == "on"
    archetype_validator = float(form_data.get("archetype_validator", "0.33"))
    archetype_broadcaster = float(form_data.get("archetype_broadcaster", "0.33"))
    archetype_explorer = float(form_data.get("archetype_explorer", "0.34"))

    # Archetype transitions
    trans_val_val = float(form_data.get("trans_val_val", "0.85"))
    trans_val_broad = float(form_data.get("trans_val_broad", "0.1"))
    trans_val_expl = float(form_data.get("trans_val_expl", "0.05"))
    trans_broad_val = float(form_data.get("trans_broad_val", "0.1"))
    trans_broad_broad = float(form_data.get("trans_broad_broad", "0.8"))
    trans_broad_expl = float(form_data.get("trans_broad_expl", "0.1"))
    trans_expl_val = float(form_data.get("trans_expl_val", "0.05"))
    trans_expl_broad = float(form_data.get("trans_expl_broad", "0.1"))
    trans_expl_expl = float(form_data.get("trans_expl_expl", "0.85"))

    # Extract LLM backend
    llm_backend = form_data.get(
        "llm_backend", "ollama"
    )  # Changed default from vllm to ollama for HPC

    llm = request.form.get("llm")
    llm_v = form_data.get("llm_v", "http://127.0.0.1:11434/v1")
    llm_v_agent = form_data.get("llm_v_agent", "minicpm-v:latest")
    llm_v_temperature = form_data.get("llm_v_temperature", "0.5")
    llm_v_api_key = form_data.get("llm_v_api_key", "NULL")
    llm_v_max_tokens = form_data.get("llm_v_max_tokens", "300")

    # Check if LLM agents are enabled
    llm_agents_enabled = (
        bool(exp.llm_agents_enabled) if hasattr(exp, "llm_agents_enabled") else True
    )

    # Check if Image Transcription is enabled
    enable_image_transcription = form_data.get("enable_image_transcription") == "true"

    # Build LLM config based on backend and LLM agents enabled status
    if not llm_agents_enabled:
        # LLM agents not enabled - use Ollama defaults for consistency
        llm_config = {
            "address": llm,
            "port": 11434,
            "model": "llama3.2",
            "temperature": 0.9,
            "llm_api_key": "NULL",
            "llm_max_tokens": -1,
            "api_format": "auto",
            "batching_policy": "auto",
        }
        llm_v_config = {
            "address": llm_v,
            "port": 11434,
            "model": llm_v_agent or "minicpm-v:latest",
            "temperature": float(llm_v_temperature or "0.5"),
            "llm_api_key": llm_v_api_key or "NULL",
            "llm_max_tokens": int(llm_v_max_tokens or "300"),
            "api_format": "auto",
            "batching_policy": "auto",
        }
    elif llm_backend == "vllm":
        llm_config = {
            "backend": "vllm",
            "model": form_data.get("llm_model", "AMead10/Llama-3.2-3B-Instruct-AWQ"),
            "temperature": float(form_data.get("llm_temperature", "0.9")),
            "max_tokens": int(form_data.get("llm_max_tokens", "256")),
            "max_model_len": int(form_data.get("llm_max_model_len", "4096")),
            "tensor_parallel_size": int(form_data.get("llm_tensor_parallel_size", "1")),
            "gpu_memory_utilization": float(
                form_data.get("llm_gpu_memory_utilization", "0.15")
            ),
            "enable_flashattention": form_data.get("llm_enable_flashattention")
            == "true",
            "num_actors": int(form_data.get("llm_num_actors", "4")),
            "gpu_per_actor": float(form_data.get("llm_gpu_per_actor", "1.0")),
            "reuse_actors": form_data.get("llm_reuse_actors") == "true",
            "actor_name_prefix": form_data.get("llm_actor_name_prefix", "ysim_llm"),
        }

        # Only include llm_v_config if Image Transcription is enabled
        if enable_image_transcription:
            llm_v_config = {
                "model": form_data.get("llm_v_model", "openbmb/MiniCPM-V-2_6-int4"),
                "temperature": float(form_data.get("llm_v_temperature", "0.5")),
                "max_tokens": int(form_data.get("llm_v_max_tokens", "300")),
                "max_model_len": int(form_data.get("llm_v_max_model_len", "4096")),
                "gpu_memory_utilization": float(
                    form_data.get("llm_v_gpu_memory_utilization", "0.15")
                ),
            }
        else:
            llm_v_config = None
    else:  # ollama
        llm_config = {
            "address": llm,
            "port": 11434,
            "model": form_data.get("user_type", "llama3.2"),
            "temperature": float(form_data.get("llm_temperature", "0.7")),
            "llm_api_key": "NULL",
            "llm_max_tokens": -1,
            "api_format": "auto",
            "batching_policy": "auto",
        }
        llm_v_config = {
            "address": llm_v,
            "port": 11434,
            "model": form_data.get("llm_v_agent", "minicpm-v:latest"),
            "temperature": float(form_data.get("llm_v_temperature", "0.5")),
            "llm_api_key": form_data.get("llm_v_api_key", "NULL"),
            "llm_max_tokens": int(form_data.get("llm_v_max_tokens", "300")),
            "api_format": "auto",
            "batching_policy": "auto",
        }

    # Get activity profiles for population
    activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population_id)
        .all()
    )
    activity_profiles = [a.activity_profile for a in activity_profiles]
    activity_profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_([a for a in activity_profiles]))
        .all()
    )
    profiles = {ap.name: ap.hours for ap in activity_profiles}

    # Fetch optional hourly activity rates
    hourly_activity_custom = {}
    for hour in range(24):
        hourly_val = form_data.get(f"hourly_{hour}")
        if hourly_val and hourly_val.strip():
            try:
                hourly_activity_custom[str(hour)] = float(hourly_val)
            except ValueError:
                pass

    default_hourly_activity = {
        "0": 0.023,
        "1": 0.021,
        "2": 0.020,
        "3": 0.020,
        "4": 0.018,
        "5": 0.017,
        "6": 0.017,
        "7": 0.018,
        "8": 0.020,
        "9": 0.020,
        "10": 0.021,
        "11": 0.022,
        "12": 0.024,
        "13": 0.027,
        "14": 0.030,
        "15": 0.032,
        "16": 0.032,
        "17": 0.032,
        "18": 0.032,
        "19": 0.031,
        "20": 0.030,
        "21": 0.029,
        "22": 0.027,
        "23": 0.025,
    }

    hourly_activity = {
        str(h): (
            hourly_activity_custom.get(str(h), default_hourly_activity[str(h)])
            if hourly_activity_custom
            else default_hourly_activity[str(h)]
        )
        for h in range(24)
    }

    # Get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=exp.idexp).all()
    topics_ids = [t.topic_id for t in topics]
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    discussion_topics = [t.name for t in topics_objs]
    topics = discussion_topics  # Use topic names (strings) for JSON serialization

    # Get topic interest percentages from form
    topic_percentages = {}
    for topic_obj in topics_objs:
        percentage_key = f"topic_interest_{topic_obj.id}"
        percentage_value = form_data.get(percentage_key, "100")
        try:
            topic_percentages[topic_obj.name] = float(percentage_value)
        except (ValueError, TypeError):
            topic_percentages[topic_obj.name] = 100.0  # Default to 100% if invalid

    # Read server config to get shared values
    if "database_server.db" in exp.db_name:
        uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")

    exp_dir = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}"
    server_config_path = f"{exp_dir}{os.sep}config_server.json"

    # Get sentiment and emotion annotation from server config
    annotations = exp.annotations.split(",") if exp.annotations else []
    enable_sentiment = "sentiment" in annotations
    emotion_annotation = "emotion" in annotations
    enable_toxicity = "toxicity" in annotations
    perspective_api_key = (
        exp.perspective_api if hasattr(exp, "perspective_api") else None
    )

    # Build simulation config (with annotation fields inside)
    simulation_config = {
        "num_days": days,
        "num_slots_per_day": 24,
        "heartbeat_interval": 5,
        "note": "num_days=0 means infinite simulation, set to a positive number to limit duration. heartbeat_interval in seconds (default: 5).",
        "percentage_new_agents_iteration": percentage_new_agents_iteration,
        "percentage_removed_agents_iteration": percentage_removed_agents_iteration,
        "discussion_topics": discussion_topics,
        "activity_profiles": profiles,
        "hourly_activity": hourly_activity,
        "actions_likelihood": {
            "post": post,
            "image": image,
            "news": news,
            "comment": comment,
            "read": read,
            "share": share,
            "search": search,
            "cast": vote,
            "share_link": share_link,
            "follow": follow,
        },
        "agent_archetypes": {
            "enabled": enable_archetypes,
            "agent_downcast": agent_downcast,
            "distribution": {
                "validator": archetype_validator,
                "broadcaster": archetype_broadcaster,
                "explorer": archetype_explorer,
            },
        },
        "enable_sentiment": enable_sentiment,
        "emotion_annotation": emotion_annotation,
        "enable_toxicity": enable_toxicity,
        "perspective_api_key": perspective_api_key,
    }

    # Tie churn/new-agents runtime toggles and probabilities to HPC form inputs.
    # The form exposes daily percentages for both dynamics; zero means disabled.
    churn_enabled = percentage_removed_agents_iteration > 0.0
    new_agents_enabled = percentage_new_agents_iteration > 0.0

    # Build agents config
    agents_config = {
        "reading_from_follower_ratio": reading_from_follower_ratio,
        "max_length_thread_reading": max_length_thread_reading,
        "attention_window": attention_window,
        "probability_of_daily_follow": probability_of_daily_follow,
        "probability_of_secondary_follow": probability_of_secondary_follow,
        "follow_action_decay": {
            "enabled": follow_decay_enabled,
            "decay_function": follow_decay_function,
            "half_life_rounds": follow_decay_half_life,
            "decay_rate": follow_decay_rate,
            "min_probability_ratio": follow_decay_min_ratio,
        },
        "batch_size": batch_size,
        "churn": {
            "enabled": churn_enabled,
            "churn_probability": percentage_removed_agents_iteration,
            "inactivity_threshold": 5,
            "churn_percentage": percentage_removed_agents_iteration,
        },
        "new_agents": {
            "enabled": new_agents_enabled,
            "probability_new_agents": percentage_new_agents_iteration,
            "percentage_new_agents": percentage_new_agents_iteration,
        },
        "memory_enabled": bool(memory_enabled),
        "memory_pair_limit": memory_pair_limit,
        "memory_prompt_max_chars": memory_prompt_max_chars,
        "memory_social_decay_lambda": memory_social_decay_lambda,
        "memory_social_corruption_rate": memory_social_corruption_rate,
        "memory_social_resummarize_every_events": memory_social_resummarize_every_events,
        "memory_thread_decay_lambda": memory_thread_decay_lambda,
        "memory_thread_corruption_rate": memory_thread_corruption_rate,
        "memory_thread_resummarize_every_events": memory_thread_resummarize_every_events,
        "memory_evidence_tail_max": memory_evidence_tail_max,
        "memory_digest_update_cadence_rounds": memory_digest_update_cadence_rounds,
        "memory_digest_events_limit": memory_digest_events_limit,
        "memory_cold_start_window": memory_cold_start_window,
        "memory_semantic_enabled": bool(memory_semantic_enabled),
        "memory_search_k": memory_search_k,
        "memory_search_max_chars": memory_search_max_chars,
        "memory_search_time_window_rounds": memory_search_time_window_rounds,
        "memory_tier_a_max_chars": memory_tier_a_max_chars,
        "memory_tier_b_max_chars": memory_tier_b_max_chars,
        "memory_tier_c_max_chars": memory_tier_c_max_chars,
        "memory_total_max_chars": memory_total_max_chars,
        "memory_tier_c_uncertainty_threshold": memory_tier_c_uncertainty_threshold,
        "memory_reflection_cadence_rounds": memory_reflection_cadence_rounds,
        "memory_reflection_min_events": memory_reflection_min_events,
        "memory_reflection_trigger_importance_sum": memory_reflection_trigger_importance_sum,
        "memory_reflection_max_items_per_run": memory_reflection_max_items_per_run,
        "memory_embedding_model": memory_embedding_model,
        "memory_embedding_async": bool(memory_embedding_async),
        "memory_importance_mode": memory_importance_mode,
        "memory_backend": (
            "hybrid_semantic" if bool(memory_semantic_enabled) else "simple_recent"
        ),
        "memory_prompt_mode": "subtle_timeline",
        "memory_reply_context_max_chars": max_length_thread_reading * 320,
        "memory_vote_signal_only": False,
    }

    # Logging config
    logging_config = {
        "enable_execution_log": True,
        "enable_actor_log": True,
        "enable_client_log": True,
        "enable_console_log": True,
        "enable_llm_usage_log": True,
    }

    # Generate HPC client config
    # For remote experiments, include server address and port
    server_address = exp.server if exp.is_remote == 1 else None
    server_port = exp.port if exp.is_remote == 1 else None

    config = generate_hpc_client_config(
        client_name=name,
        namespace=exp.exp_name,
        llm_backend=llm_backend,
        llm_config=llm_config,
        llm_v_config=llm_v_config,
        simulation_config=simulation_config,
        agents_config=agents_config,
        logging_config=logging_config,
        enable_sentiment=enable_sentiment,
        emotion_annotation=emotion_annotation,
        enable_toxicity=enable_toxicity,
        perspective_api_key=perspective_api_key,
        server_address=server_address,
        server_port=server_port,
    )
    config["recommendations"] = {"default_limit": recommendations_default_limit}

    # Save config file using standard naming pattern
    config_filename = f"{exp_dir}{os.sep}client_{name}-{population.name}.json"
    with open(config_filename, "w") as f:
        json.dump(config, f, indent=2)

    # Create agent population file (same as standard pipeline)
    population_filename = f"{exp_dir}{os.sep}{population.name}.json"

    # Get agents for this population
    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

    # Assign archetypes to agents based on distribution probabilities
    num_agents = len(agents)
    archetype_assignments = []

    if enable_archetypes and num_agents > 0:
        # Build list of active archetypes and their probabilities
        active_archetypes = []
        active_probabilities = []

        if archetype_validator > 0:
            active_archetypes.append("validator")
            active_probabilities.append(archetype_validator)

        if archetype_broadcaster > 0:
            active_archetypes.append("broadcaster")
            active_probabilities.append(archetype_broadcaster)

        if archetype_explorer > 0:
            active_archetypes.append("explorer")
            active_probabilities.append(archetype_explorer)

        # Normalize probabilities if they don't sum to 1
        if len(active_probabilities) > 0:
            total_prob = sum(active_probabilities)
            if total_prob > 0:
                active_probabilities = [p / total_prob for p in active_probabilities]
                # Assign archetypes to agents using numpy random choice
                import numpy as np

                archetype_assignments = np.random.choice(
                    active_archetypes, size=num_agents, p=active_probabilities
                ).tolist()
            else:
                archetype_assignments = [None] * num_agents
        else:
            archetype_assignments = [None] * num_agents
    else:
        archetype_assignments = [None] * num_agents

    # Build agent population JSON
    import random
    import uuid

    import faker

    posted_opinion_flag = (
        str(request.form.get("experiment_opinion_dynamics_enabled", "")).strip().lower()
    )
    if posted_opinion_flag in {"true", "1", "yes", "on"}:
        opinions_enabled = True
    elif posted_opinion_flag in {"false", "0", "no", "off"}:
        opinions_enabled = False
    else:
        opinions_enabled = _opinion_dynamics_enabled_for_client_creation(exp)

    population_data = {"agents": []}
    for idx, agent in enumerate(agents):
        custom_prompt = Agent_Profile.query.filter_by(agent_id=agent.id).first()
        custom_prompt = custom_prompt.profile if custom_prompt else None

        # Allocate topics based on specified percentages
        interests = allocate_topics_by_percentage(topics, topic_percentages)

        activity_profile_obj = (
            db.session.query(ActivityProfile)
            .filter_by(id=agent.activity_profile)
            .first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        agent_data = {
            "id": str(uuid.uuid4()),
            "username": agent.name,
            "email": f"{agent.name}@ysocial.it",
            "password": f"{agent.name}",
            "age": agent.age,
            "user_type": "agent",
            "leaning": agent.leaning,
            "interests": [interests, len(interests)],
            "oe": agent.oe,
            "co": agent.co,
            "ex": agent.ex,
            "ag": agent.ag,
            "ne": agent.ne,
            "recsys_type": crecsys,
            "frecsys_type": frecsys,
            "language": agent.language,
            "owner": exp.owner,
            "education_level": agent.education_level,
            "round_actions": int(agent.round_actions),
            "gender": agent.gender,
            "nationality": agent.nationality,
            "toxicity": agent.toxicity,
            "is_page": 0,
            "prompts": custom_prompt,
            "daily_activity_level": agent.daily_activity_level,
            "profession": agent.profession,
            "activity_profile": activity_profile_name,
            "archetype": archetype_assignments[idx],
            "opinions": (
                {i: random.random() for i in interests}
                if bool(opinions_enabled)
                else None
            ),
            "llm": bool(exp.llm_agents_enabled),
        }
        population_data["agents"].append(agent_data)

    # Add pages to population data
    pages = Page_Population.query.filter_by(population_id=population.id).all()
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

    for page in pages:
        # Get page topics
        page_topics = (
            db.session.query(Exp_Topic, Topic_List)
            .join(Topic_List)
            .filter(Exp_Topic.exp_id == exp.idexp, Exp_Topic.topic_id == Topic_List.id)
            .all()
        )
        page_topics = [t[1].name for t in page_topics]
        page_topics = list(set(page_topics) & set(topics))

        activity_profile_obj = (
            db.session.query(ActivityProfile)
            .filter_by(id=page.activity_profile)
            .first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        page_data = {
            "id": str(uuid.uuid4()),
            "username": page.name,
            "email": f"{page.name}@ysocial.it",
            "password": f"{page.name}",
            "age": 0,
            "user_type": "page",
            "leaning": page.leaning,
            "interests": [page_topics, len(page_topics)],
            "oe": "",
            "co": "",
            "ex": "",
            "ag": "",
            "ne": "",
            "recsys_type": "",
            "frecsys_type": "",
            "language": "english",
            "owner": exp.owner,
            "education_level": "",
            "round_actions": 3,
            "gender": "",
            "nationality": "",
            "toxicity": "none",
            "is_page": 1,
            "feed_url": page.feed,
            "activity_profile": activity_profile_name,
            "llm": bool(exp.llm_agents_enabled),
        }
        population_data["agents"].append(page_data)

    # Save population file
    with open(population_filename, "w") as f:
        json.dump(population_data, f, indent=4)

    # Copy prompts file into the experiment folder
    # For HPC experiments, use prompts_hpc.json from data_schema and rename to prompts.json
    # Always copy for HPC to ensure correct prompts file (overwrites if exists)
    prompts_dest = f"{exp_dir}{os.sep}prompts.json"

    if exp.platform_type == "microblogging":
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts_hpc.json"))
        shutil.copyfile(prompts_src, prompts_dest)
    elif exp.platform_type == "forum":
        prompts_src = get_resource_path(
            os.path.join("data_schema", "prompts_forum.json")
        )
        shutil.copyfile(prompts_src, prompts_dest)

    # Create population assignment if not exists
    pop_exp = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=exp.idexp
    ).first()
    if not pop_exp:
        pop_exp = Population_Experiment(id_population=population_id, id_exp=exp.idexp)
        db.session.add(pop_exp)
        db.session.commit()

    # Create client record in database
    client = Client(
        name=name,
        descr=descr,
        id_exp=exp.idexp,
        population_id=population_id,
        days=days,
        percentage_new_agents_iteration=percentage_new_agents_iteration,
        percentage_removed_agents_iteration=percentage_removed_agents_iteration,
        max_length_thread_reading=max_length_thread_reading,
        reading_from_follower_ratio=reading_from_follower_ratio,
        probability_of_daily_follow=probability_of_daily_follow,
        probability_of_secondary_follow=probability_of_secondary_follow,
        attention_window=attention_window,
        visibility_rounds=visibility_rounds,
        post=post,
        share=share,
        image=image,
        comment=comment,
        read=read,
        news=news,
        search=search,
        vote=vote,
        share_link=share_link,
        follow=follow,
        crecsys=crecsys,
        frecsys=frecsys,
        archetype_validator=archetype_validator,
        archetype_broadcaster=archetype_broadcaster,
        archetype_explorer=archetype_explorer,
        trans_val_val=trans_val_val,
        trans_val_broad=trans_val_broad,
        trans_val_expl=trans_val_expl,
        trans_broad_broad=trans_broad_broad,
        trans_broad_val=trans_broad_val,
        trans_broad_expl=trans_broad_expl,
        trans_expl_expl=trans_expl_expl,
        trans_expl_val=trans_expl_val,
        trans_expl_broad=trans_expl_broad,
        status=0,
    )
    db.session.add(client)
    db.session.commit()

    # Create Client_Execution entry for progress tracking
    # For infinite clients (days = -1), set expected_duration_rounds to -1
    # HPC uses 24 slots per day
    expected_rounds = -1 if days == -1 else days * 24
    client_exec = Client_Execution(
        client_id=client.id,
        last_active_hour=-1,
        last_active_day=-1,
        expected_duration_rounds=expected_rounds,
    )
    db.session.add(client_exec)
    db.session.commit()

    # Handle optional network configuration (same logic as Standard clients)
    network_model = form_data.get("network_model")
    network_p = form_data.get("network_p")
    network_m = form_data.get("network_m")
    network_file = request.files.get(
        "network_file"
    )  # Get from request.files, not form_data

    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"HPC client network config - model: {network_model}, file: {network_file.filename if network_file else None}"
    )

    if network_model or (network_file and network_file.filename):
        # Get agents and pages for the population (same logic as Standard)
        agent_pops = Agent_Population.query.filter_by(population_id=population_id).all()
        agents = [Agent.query.filter_by(id=ap.agent_id).first() for ap in agent_pops]
        agent_ids = [a.name for a in agents if a]

        page_pops = Page_Population.query.filter_by(population_id=population_id).all()
        pages_list = [Page.query.filter_by(id=pp.page_id).first() for pp in page_pops]
        page_ids = [p.name for p in pages_list if p]

        # Combine agent and page IDs
        all_node_ids = agent_ids + page_ids

        network_path = f"{exp_dir}{os.sep}{client.name}_network.csv"

        if network_file and network_file.filename:
            # Handle uploaded network file (replicate Standard logic exactly)
            temp_path = network_path.replace("_network.csv", "_network_temp.csv")
            network_file.save(temp_path)

            try:
                with open(network_path, "w") as o:
                    error, error2 = False, False
                    with open(temp_path, "r") as f:
                        for l in f:
                            l = l.rstrip().split(",")
                            if len(l) < 2:
                                continue

                            # Validate agent_1 (same logic as Standard)
                            agent_1 = Agent.query.filter_by(name=l[0]).all()
                            aids = [a.id for a in agent_1]

                            if agent_1 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error = len(test) == 0
                            else:
                                agent_1 = Page.query.filter_by(name=l[0]).all()
                                aids = [a.id for a in agent_1]

                                if agent_1 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error = len(test) == 0
                                if agent_1 is None:
                                    error = True

                            # Validate agent_2 (same logic as Standard)
                            agent_2 = Agent.query.filter_by(name=l[1]).all()
                            aids = [a.id for a in agent_2]

                            if agent_2 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error2 = len(test) == 0
                            else:
                                agent_2 = Page.query.filter_by(name=l[1]).all()
                                aids = [a.id for a in agent_2]

                                if agent_2 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error2 = len(test) == 0

                                if agent_2 is None:
                                    error2 = True

                            if not error and not error2:
                                o.write(f"{l[0]},{l[1]}\n")
                            else:
                                flash(
                                    f"Agent {l[0]} or {l[1]} not found in network file.",
                                    "warning",
                                )

                os.remove(temp_path)
                client.network_type = "Custom Network"
                db.session.commit()
                logger.info(f"HPC client network file created: {network_path}")
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(network_path):
                    os.remove(network_path)
                flash(
                    "Network file format error: provide a csv file containing two columns with agent names. No header required.",
                    "error",
                )

        elif network_model:
            # Handle synthetic network generation (replicate Standard logic exactly)
            # Extract parameters with defaults
            m = int(network_m) if network_m else 2
            p = float(network_p) if network_p else 0.1
            k = int(form_data.get("network_k")) if form_data.get("network_k") else 4
            ws_p = (
                float(form_data.get("network_ws_p"))
                if form_data.get("network_ws_p")
                else 0.3
            )
            plc_m = (
                int(form_data.get("network_plc_m"))
                if form_data.get("network_plc_m")
                else 2
            )
            plc_p = (
                float(form_data.get("network_plc_p"))
                if form_data.get("network_plc_p")
                else 0.5
            )
            blocks = (
                int(form_data.get("network_blocks"))
                if form_data.get("network_blocks")
                else 3
            )
            p_in = (
                float(form_data.get("network_p_in"))
                if form_data.get("network_p_in")
                else 0.3
            )
            p_out = (
                float(form_data.get("network_p_out"))
                if form_data.get("network_p_out")
                else 0.05
            )
            tau1 = (
                float(form_data.get("network_tau1"))
                if form_data.get("network_tau1")
                else 2.5
            )
            tau2 = (
                float(form_data.get("network_tau2"))
                if form_data.get("network_tau2")
                else 1.5
            )
            mu = (
                float(form_data.get("network_mu"))
                if form_data.get("network_mu")
                else 0.1
            )
            avg_degree = (
                int(form_data.get("network_avg_degree"))
                if form_data.get("network_avg_degree")
                else 5
            )

            n = len(all_node_ids)

            # Generate network based on selected model
            if network_model == "BA":
                g = nx.barabasi_albert_graph(n, m=m)
            elif network_model == "ER":
                g = nx.erdos_renyi_graph(n, p=p)
            elif network_model == "WS":
                g = nx.watts_strogatz_graph(n, k=k, p=ws_p)
            elif network_model == "PLC":
                g = nx.powerlaw_cluster_graph(n, m=plc_m, p=plc_p)
            elif network_model == "C":
                g = nx.complete_graph(n)
            elif network_model == "SBM":
                # Divide nodes into blocks
                block_sizes = [n // blocks] * blocks
                # Add remaining nodes to last block
                block_sizes[-1] += n % blocks
                # Create probability matrix
                probs = [
                    [p_in if i == j else p_out for j in range(blocks)]
                    for i in range(blocks)
                ]
                g = nx.stochastic_block_model(block_sizes, probs)
            elif network_model == "LFR":
                # LFR benchmark with community structure
                # Calculate min_community: at least 5 nodes, at most n/3 to allow multiple communities
                min_community = min(max(5, n // 10), n // 3)
                g = nx.LFR_benchmark_graph(
                    n=n,
                    tau1=tau1,
                    tau2=tau2,
                    mu=mu,
                    average_degree=avg_degree,
                    min_community=min_community,
                )
            else:
                g = None

            if g:
                # Since the network is undirected and Y assumes directed relations,
                # we need to write the edges in both directions (same as Standard)
                with open(network_path, "w") as f:
                    for n in g.edges:
                        f.write(f"{all_node_ids[n[0]]},{all_node_ids[n[1]]}\n")
                        f.write(f"{all_node_ids[n[1]]},{all_node_ids[n[0]]}\n")
                    f.flush()

                client.network_type = network_model
                db.session.commit()
                logger.info(
                    f"HPC client synthetic network created: {network_path}, type: {network_model}"
                )

    flash(f"HPC client '{name}' created successfully")

    if bool(opinions_enabled):
        return redirect(
            url_for(
                "clientsr.opinion_configuration_hpc",
                idexp=exp.idexp,
                client_id=client.id,
            )
        )

    return redirect(f"/admin/experiment_details/{exp.idexp}")


def _create_standard_client_internal():
    """Create a standard microblogging client without forum-specific branching."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    exp_id = request.form.get("id_exp")
    population_id = request.form.get("population_id")

    exp = Exps.query.filter_by(idexp=exp_id).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if getattr(exp, "simulator_type", "Standard") == "HPC":
        flash(
            "Use the dedicated HPC client creation route for this experiment.", "error"
        )
        return redirect(url_for("clientsr.clients_hpc", idexp=exp_id))
    if exp.platform_type != "microblogging":
        flash(
            "Use the dedicated forum client creation route for this experiment.",
            "error",
        )
        if exp.platform_type == "forum":
            return redirect(url_for("clientsr.clients_forum", idexp=exp_id))
        return redirect(url_for("clientsr.clients_standard", idexp=exp_id))

    days = request.form.get("days")
    percentage_new_agents_iteration = request.form.get(
        "percentage_new_agents_iteration"
    )
    percentage_removed_agents_iteration = request.form.get(
        "percentage_removed_agents_iteration"
    )
    max_length_thread_reading = request.form.get("max_length_thread_reading")
    reading_from_follower_ratio = request.form.get("reading_from_follower_ratio")
    probability_of_daily_follow = request.form.get("probability_of_daily_follow")
    probability_of_secondary_follow = request.form.get(
        "probability_of_secondary_follow"
    )
    attention_window = request.form.get("attention_window")
    visibility_rounds = request.form.get("visibility_rounds")
    post = request.form.get("post", "0")
    share = request.form.get("share", "0")
    image = request.form.get("image", "0")
    comment = request.form.get("comment", "0")
    read = request.form.get("read", "0")
    news = request.form.get("news", "0")
    search = request.form.get("search", "0")
    vote = request.form.get("vote", "0")
    share_link = request.form.get("share_link", "0")
    share_image = request.form.get("share_image", "0")
    initial_agents = request.form.get("initial_agents")
    clock_mode = (request.form.get("clock_mode") or "simulated").strip().lower()
    clock_timezone = (request.form.get("clock_timezone") or "Europe/Rome").strip()
    clock_feed_refresh = (
        (request.form.get("clock_feed_refresh") or "hourly").strip().lower()
    )
    max_thread_context_chars = request.form.get("max_thread_context_chars", "3200")
    max_replies_per_round = request.form.get("max_replies_per_round", "2")
    reply_cooldown_rounds = request.form.get("reply_cooldown_rounds", "2")
    memory_enabled = request.form.get("memory_enabled") in {"on", "true", "1", "yes"}
    memory_pair_limit = request.form.get("memory_pair_limit", "5")
    memory_prompt_max_chars = request.form.get("memory_prompt_max_chars", "1600")
    memory_social_decay_lambda = request.form.get("memory_social_decay_lambda", "0.05")
    memory_social_corruption_rate = request.form.get(
        "memory_social_corruption_rate", "0.02"
    )
    memory_social_resummarize_every_events = request.form.get(
        "memory_social_resummarize_every_events", "4"
    )
    memory_thread_decay_lambda = request.form.get("memory_thread_decay_lambda", "0.03")
    memory_thread_corruption_rate = request.form.get(
        "memory_thread_corruption_rate", "0.01"
    )
    memory_thread_resummarize_every_events = request.form.get(
        "memory_thread_resummarize_every_events", "4"
    )
    memory_evidence_tail_max = request.form.get("memory_evidence_tail_max", "8")
    memory_digest_update_cadence_rounds = request.form.get(
        "memory_digest_update_cadence_rounds", "3"
    )
    memory_digest_events_limit = request.form.get("memory_digest_events_limit", "80")
    memory_cold_start_window = request.form.get("memory_cold_start_window", "5")
    memory_semantic_enabled = request.form.get("memory_semantic_enabled") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_search_k = request.form.get("memory_search_k", "8")
    memory_search_max_chars = request.form.get("memory_search_max_chars", "900")
    memory_search_time_window_rounds = request.form.get(
        "memory_search_time_window_rounds", "40"
    )
    memory_tier_a_max_chars = request.form.get("memory_tier_a_max_chars", "350")
    memory_tier_b_max_chars = request.form.get("memory_tier_b_max_chars", "900")
    memory_tier_c_max_chars = request.form.get("memory_tier_c_max_chars", "900")
    memory_total_max_chars = request.form.get("memory_total_max_chars", "2200")
    memory_tier_c_uncertainty_threshold = request.form.get(
        "memory_tier_c_uncertainty_threshold", "0.45"
    )
    memory_reflection_cadence_rounds = request.form.get(
        "memory_reflection_cadence_rounds", "3"
    )
    memory_reflection_min_events = request.form.get(
        "memory_reflection_min_events", "12"
    )
    memory_reflection_trigger_importance_sum = request.form.get(
        "memory_reflection_trigger_importance_sum", "3.5"
    )
    memory_reflection_max_items_per_run = request.form.get(
        "memory_reflection_max_items_per_run", "60"
    )
    memory_embedding_model = request.form.get(
        "memory_embedding_model", "snowflake-arctic-embed:110m"
    )
    memory_embedding_async = request.form.get("memory_embedding_async") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_importance_mode = request.form.get(
        "memory_importance_mode", "heuristic_then_batch_llm"
    )

    if not memory_semantic_enabled:
        memory_embedding_async = False

    llm_agents_enabled = (
        exp.llm_agents_enabled if (exp and hasattr(exp, "llm_agents_enabled")) else True
    )
    experiment_memory_enabled = _memory_enabled_for_client_creation(exp)
    if not experiment_memory_enabled:
        memory_enabled = False
        memory_semantic_enabled = False
        memory_embedding_async = False

    posted_opinion_flag = (
        str(request.form.get("experiment_opinion_dynamics_enabled", "")).strip().lower()
    )
    if posted_opinion_flag in {"true", "1", "yes", "on"}:
        opinions_enabled = True
    elif posted_opinion_flag in {"false", "0", "no", "off"}:
        opinions_enabled = False
    else:
        opinions_enabled = _opinion_dynamics_enabled_for_client_creation(exp)

    # Get LLM parameters from form, or use defaults if LLM agents are disabled
    if llm_agents_enabled:
        llm = request.form.get("llm")
        llm_api_key = request.form.get("llm_api_key")
        llm_max_tokens = request.form.get("llm_max_tokens")
        llm_temperature = request.form.get("llm_temperature")
        llm_v_agent = request.form.get("llm_v_agent")
        llm_v = request.form.get("llm_v")
        llm_v_api_key = request.form.get("llm_v_api_key")
        llm_v_max_tokens = request.form.get("llm_v_max_tokens")
        llm_v_temperature = request.form.get("llm_v_temperature")
        user_type = request.form.get("user_type")
    else:
        # Use default values when LLM agents are disabled
        llm = "http://127.0.0.1:11434/v1"
        llm_api_key = "NULL"
        llm_max_tokens = "-1"
        llm_temperature = "1.5"
        llm_v_agent = "minicpm-v"
        llm_v = "http://127.0.0.1:11434/v1"
        llm_v_api_key = "NULL"
        llm_v_max_tokens = "300"
        llm_v_temperature = "0.5"
        user_type = ""

    crecsys = request.form.get("recsys_type")
    frecsys = request.form.get("frecsys_type")

    # Get agent archetype enabled status
    enable_archetypes = request.form.get("enable_archetypes") == "on"

    # Get agent archetype values (optional, with defaults)
    try:
        archetype_validator = (
            float(request.form.get("archetype_validator", "52")) / 100.0
        )
        archetype_broadcaster = (
            float(request.form.get("archetype_broadcaster", "20")) / 100.0
        )
        archetype_explorer = float(request.form.get("archetype_explorer", "28")) / 100.0
        trans_val_val = float(request.form.get("trans_val_val", "85.3")) / 100.0
        trans_val_broad = float(request.form.get("trans_val_broad", "8.1")) / 100.0
        trans_val_expl = float(request.form.get("trans_val_expl", "6.6")) / 100.0
        trans_broad_broad = float(request.form.get("trans_broad_broad", "72.9")) / 100.0
        trans_broad_val = float(request.form.get("trans_broad_val", "19.5")) / 100.0
        trans_broad_expl = float(request.form.get("trans_broad_expl", "7.5")) / 100.0
        trans_expl_expl = float(request.form.get("trans_expl_expl", "49.0")) / 100.0
        trans_expl_val = float(request.form.get("trans_expl_val", "36.4")) / 100.0
        trans_expl_broad = float(request.form.get("trans_expl_broad", "14.6")) / 100.0
    except (ValueError, TypeError) as e:
        flash(f"Invalid archetype values: {str(e)}", "error")
        return redirect(request.referrer)

    # Validate simulation parameters
    errors = []
    # Validate numeric fields
    try:
        days = int(days)
        # days = -1 means infinite/run-until-stopped
        if days != -1 and days < 1:
            errors.append(
                "Days must be at least 1, or use -1 for infinite duration (run until stopped)"
            )
    except (ValueError, TypeError):
        errors.append("Days must be a valid integer")
    try:
        max_length_thread_reading = int(max_length_thread_reading)
    except (ValueError, TypeError):
        errors.append("Max Length Thread Reading must be a valid integer")
    try:
        max_thread_context_chars = int(max_thread_context_chars)
        if max_thread_context_chars < 200 or max_thread_context_chars > 4800:
            errors.append("Thread Context Max Chars must be between 200 and 4800")
    except (ValueError, TypeError):
        errors.append("Thread Context Max Chars must be a valid integer")
    try:
        attention_window = int(attention_window)
    except (ValueError, TypeError):
        errors.append("Attention Window must be a valid integer")
    try:
        visibility_rounds = int(visibility_rounds)
    except (ValueError, TypeError):
        errors.append("Visibility Rounds must be a valid integer")
    try:
        max_replies_per_round = int(max_replies_per_round)
        if max_replies_per_round < 0:
            errors.append("Max Replies per Round must be at least 0")
    except (ValueError, TypeError):
        errors.append("Max Replies per Round must be a valid integer")
    try:
        reply_cooldown_rounds = int(reply_cooldown_rounds)
        if reply_cooldown_rounds < 0:
            errors.append("Reply Cooldown must be at least 0")
    except (ValueError, TypeError):
        errors.append("Reply Cooldown must be a valid integer")
    try:
        memory_pair_limit = int(memory_pair_limit)
        memory_prompt_max_chars = int(memory_prompt_max_chars)
        memory_search_k = int(memory_search_k)
        memory_search_max_chars = int(memory_search_max_chars)
        memory_search_time_window_rounds = int(memory_search_time_window_rounds)
        memory_tier_a_max_chars = int(memory_tier_a_max_chars)
        memory_tier_b_max_chars = int(memory_tier_b_max_chars)
        memory_tier_c_max_chars = int(memory_tier_c_max_chars)
        memory_total_max_chars = int(memory_total_max_chars)
        memory_reflection_cadence_rounds = int(memory_reflection_cadence_rounds)
        memory_reflection_min_events = int(memory_reflection_min_events)
        memory_reflection_max_items_per_run = int(memory_reflection_max_items_per_run)
        memory_social_resummarize_every_events = int(
            memory_social_resummarize_every_events
        )
        memory_thread_resummarize_every_events = int(
            memory_thread_resummarize_every_events
        )
        memory_evidence_tail_max = int(memory_evidence_tail_max)
        memory_digest_update_cadence_rounds = int(memory_digest_update_cadence_rounds)
        memory_digest_events_limit = int(memory_digest_events_limit)
        memory_cold_start_window = int(memory_cold_start_window)
    except (ValueError, TypeError):
        errors.append("Memory settings must use valid numeric values")
    try:
        memory_social_decay_lambda = float(memory_social_decay_lambda)
        memory_social_corruption_rate = float(memory_social_corruption_rate)
        memory_thread_decay_lambda = float(memory_thread_decay_lambda)
        memory_thread_corruption_rate = float(memory_thread_corruption_rate)
        memory_tier_c_uncertainty_threshold = float(memory_tier_c_uncertainty_threshold)
        memory_reflection_trigger_importance_sum = float(
            memory_reflection_trigger_importance_sum
        )
    except (ValueError, TypeError):
        errors.append("Memory weights must use valid numeric values")

    if clock_mode not in {"simulated", "real_time"}:
        errors.append("Experiment Clock Mode must be either simulated or real_time")
    if clock_feed_refresh not in {"hourly"}:
        errors.append("Feed refresh must be hourly")

    # Validate probability fields (must be float in [0, 1])
    try:
        percentage_new_agents_iteration = float(percentage_new_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% New Agents (daily) must be a valid number")
        percentage_new_agents_iteration = None
    try:
        percentage_removed_agents_iteration = float(percentage_removed_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% Daily Churn must be a valid number")
        percentage_removed_agents_iteration = None
    try:
        reading_from_follower_ratio = float(reading_from_follower_ratio)
    except (ValueError, TypeError):
        errors.append("Timeline Follower Ratio must be a valid number")
        reading_from_follower_ratio = None
    try:
        probability_of_daily_follow = float(probability_of_daily_follow)
    except (ValueError, TypeError):
        errors.append("Probability Daily Follow must be a valid number")
        probability_of_daily_follow = None
    try:
        probability_of_secondary_follow = float(probability_of_secondary_follow)
    except (ValueError, TypeError):
        errors.append("Probability Secondary Follow must be a valid number")
        probability_of_secondary_follow = None
    action_probability_values = {
        "Post new content": post,
        "Comment a Post": comment,
        "Read a content": read,
        "Search a Hashtag": search,
        "Share Link": share_link,
        "Share Image": share_image,
    }
    parsed_action_values = {}
    for field_name, raw_value in action_probability_values.items():
        try:
            parsed_action_values[field_name] = float(raw_value)
        except (ValueError, TypeError):
            errors.append(f"{field_name} must be a valid number")
            parsed_action_values[field_name] = None

    post = parsed_action_values["Post new content"]
    comment = parsed_action_values["Comment a Post"]
    read = parsed_action_values["Read a content"]
    search = parsed_action_values["Search a Hashtag"]
    share_link = parsed_action_values["Share Link"]
    share_image = parsed_action_values["Share Image"]
    share = 0.0
    image = 0.0
    news = 0.0
    vote = 0.0

    # Check probability ranges for true probabilities.
    probabilities = {
        "% New Agents (daily)": percentage_new_agents_iteration,
        "% Daily Churn": percentage_removed_agents_iteration,
        "Timeline Follower Ratio": reading_from_follower_ratio,
        "Probability Daily Follow": probability_of_daily_follow,
        "Probability Secondary Follow": probability_of_secondary_follow,
    }
    for field_name, value in probabilities.items():
        if value is not None and not (0 <= value <= 1):
            errors.append(f"{field_name} must be between 0 and 1")

    # Standard action relevance fields use relative weights in [0, 10].
    action_scores = {
        "Post new content": post,
        "Comment a Post": comment,
        "Read a content": read,
        "Search a Hashtag": search,
        "Share Link": share_link,
        "Share Image": share_image,
    }
    for field_name, value in action_scores.items():
        if value is not None and not (0 <= value <= 10):
            errors.append(f"{field_name} must be between 0 and 10")

    if errors:
        for error in errors:
            flash(error)
        return redirect(request.referrer)

    # Fetch optional network configuration
    network_model = request.form.get("network_model")
    network_p = request.form.get("network_p")
    network_m = request.form.get("network_m")
    network_file = request.files.get("network_file")

    # Fetch optional hourly activity rates
    hourly_activity_custom = {}
    for hour in range(24):
        hourly_val = request.form.get(f"hourly_{hour}")
        if hourly_val and hourly_val.strip():
            try:
                hourly_activity_custom[str(hour)] = float(hourly_val)
            except ValueError:
                pass  # Ignore invalid values, use defaults

    # get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=exp_id).all()
    topics_ids = [t.topic_id for t in topics]
    # get the topics names from the Topic_list table
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topics = [t.name for t in topics_objs]

    # Get topic interest percentages from form
    topic_percentages = {}
    for topic_obj in topics_objs:
        percentage_key = f"topic_interest_{topic_obj.id}"
        percentage_value = request.form.get(percentage_key, "100")
        try:
            topic_percentages[topic_obj.name] = float(percentage_value)
        except (ValueError, TypeError):
            topic_percentages[topic_obj.name] = 100.0  # Default to 100% if invalid

    # if name already exists, return to the previous page
    if Client.query.filter_by(name=name).first():
        flash("Client name already exists.", "error")
        return redirect(request.referrer)

    exp = Exps.query.filter_by(idexp=exp_id).first()

    # get population
    population = Population.query.filter_by(id=population_id).first()

    if population is None:
        flash("Population not found.", "error")
        return redirect(request.referrer)

    pop_type = infer_population_username_type(population)
    if pop_type not in {None, "microblogging"}:
        flash(
            f"Population Username Type '{pop_type}' is incompatible with experiment platform 'microblogging'.",
            "error",
        )
        return redirect(request.referrer)

    initial_agents_int = None
    if initial_agents and initial_agents.strip():
        try:
            initial_agents_int = int(initial_agents)
            if initial_agents_int < 1:
                initial_agents_int = None
        except (ValueError, TypeError):
            initial_agents_int = None

    # check if the population is already assigned to the experiment
    # if not, add it
    pop_exp = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=exp_id
    ).first()
    if not pop_exp:
        pop_exp = Population_Experiment(id_population=population_id, id_exp=exp_id)
        db.session.add(pop_exp)
        db.session.commit()

    # create the Client object
    client = Client(
        name=name,
        descr=descr,
        id_exp=exp_id,
        population_id=population_id,
        days=days,
        percentage_new_agents_iteration=percentage_new_agents_iteration,
        percentage_removed_agents_iteration=percentage_removed_agents_iteration,
        max_length_thread_reading=max_length_thread_reading,
        reading_from_follower_ratio=reading_from_follower_ratio,
        probability_of_daily_follow=probability_of_daily_follow,
        attention_window=attention_window,
        visibility_rounds=visibility_rounds,
        post=post,
        share=share,
        image=image,
        comment=comment,
        read=read,
        news=news,
        search=search,
        vote=vote,
        share_link=share_link,
        llm=llm,
        llm_api_key=llm_api_key,
        llm_max_tokens=int(llm_max_tokens),
        llm_temperature=float(llm_temperature),
        llm_v_agent=llm_v_agent,
        llm_v=llm_v,
        llm_v_api_key=llm_v_api_key,
        llm_v_max_tokens=int(llm_v_max_tokens),
        llm_v_temperature=float(llm_v_temperature),
        probability_of_secondary_follow=probability_of_secondary_follow,
        crecsys=crecsys,
        frecsys=frecsys,
        status=0,
        archetype_validator=archetype_validator,
        archetype_broadcaster=archetype_broadcaster,
        archetype_explorer=archetype_explorer,
        trans_val_val=trans_val_val,
        trans_val_broad=trans_val_broad,
        trans_val_expl=trans_val_expl,
        trans_broad_broad=trans_broad_broad,
        trans_broad_val=trans_broad_val,
        trans_broad_expl=trans_broad_expl,
        trans_expl_expl=trans_expl_expl,
        trans_expl_val=trans_expl_val,
        trans_expl_broad=trans_expl_broad,
    )

    db.session.add(client)
    db.session.commit()

    # If experiment was completed, reset status to stopped since a new client was added
    if exp.exp_status == "completed":
        exp.exp_status = "stopped"
        db.session.commit()

    # Get LLM URL from environment (set by y_social.py)
    import os

    # get population activity profiles
    activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population_id)
        .all()
    )

    activity_profiles = [a.activity_profile for a in activity_profiles]

    # get all activity profiles from the db where id in activity_profiles
    activity_profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_([a for a in activity_profiles]))
        .all()
    )

    profiles = {ap.name: ap.hours for ap in activity_profiles}

    annotations = exp.annotations.split(",")
    emotion_annotation = "emotion" in annotations

    default_hourly_activity = {
        "0": 0.023,
        "1": 0.021,
        "2": 0.020,
        "3": 0.020,
        "4": 0.018,
        "5": 0.017,
        "6": 0.017,
        "7": 0.018,
        "8": 0.020,
        "9": 0.020,
        "10": 0.021,
        "11": 0.022,
        "12": 0.024,
        "13": 0.027,
        "14": 0.030,
        "15": 0.032,
        "16": 0.032,
        "17": 0.032,
        "18": 0.032,
        "19": 0.031,
        "20": 0.030,
        "21": 0.029,
        "22": 0.027,
        "23": 0.025,
    }

    hourly_activity = {
        str(h): (
            hourly_activity_custom.get(str(h), default_hourly_activity[str(h)])
            if hourly_activity_custom
            else default_hourly_activity[str(h)]
        )
        for h in range(24)
    }

    if "database_server.db" in exp.db_name:
        uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()
    experiment_folder = os.path.join(BASE_DIR, "y_web", "experiments", uid)
    experiment_config_path = os.path.join(experiment_folder, "config_server.json")
    resolved_clock = {
        "mode": clock_mode,
        "timezone": clock_timezone or "Europe/Rome",
        "feed_refresh": clock_feed_refresh,
    }

    try:
        experiment_config = {}
        if os.path.exists(experiment_config_path):
            with open(experiment_config_path, "r") as config_file:
                experiment_config = json.load(config_file)
        experiment_config["clock"] = {
            "mode": resolved_clock["mode"],
            "timezone": resolved_clock["timezone"],
            "feed_refresh": resolved_clock["feed_refresh"],
        }
        if (
            resolved_clock["mode"] == "real_time"
            and "anchor_date" not in experiment_config["clock"]
        ):
            experiment_config["clock"]["anchor_date"] = (
                __import__("datetime").date.today().isoformat()
            )
        with open(experiment_config_path, "w") as config_file:
            json.dump(experiment_config, config_file, indent=4)
    except Exception:
        pass

    config = {
        "name": name,
        "servers": {
            "llm": llm,
            "llm_api_key": llm_api_key,
            "llm_max_tokens": int(llm_max_tokens),
            "llm_temperature": float(llm_temperature),
            "llm_v": llm_v,
            "llm_v_api_key": llm_v_api_key,
            "llm_v_max_tokens": int(llm_v_max_tokens),
            "llm_v_temperature": float(llm_v_temperature),
            "api": f"http://{exp.server}:{exp.port}/",
        },
        "simulation": {
            "name": name,
            "population": population.name,
            "client": "YClientWeb",
            "days": int(days),
            "slots": 24,
            "initial_agents": initial_agents_int,
            "clock_mode": resolved_clock["mode"],
            "clock_timezone": resolved_clock["timezone"],
            "feed_refresh": resolved_clock["feed_refresh"],
            "percentage_new_agents_iteration": float(percentage_new_agents_iteration),
            "percentage_removed_agents_iteration": float(
                percentage_removed_agents_iteration
            ),
            "activity_profiles": profiles,
            "hourly_activity": hourly_activity,
            "actions_likelihood": {
                "post": float(post),
                "image": 0.0,
                "news": 0.0,
                "comment": float(comment) if comment is not None else 0,
                "read": float(read) if read is not None else 0,
                "share": 0.0,
                "search": float(search) if search is not None else 0,
                "cast": 0.0,
                "share_link": float(share_link) if share_link is not None else 0,
                "share_image": float(share_image) if share_image is not None else 0,
            },
            "emotion_annotation": emotion_annotation,
            "opinion_dynamics": {
                "enabled": bool(opinions_enabled),
            },
            "agent_archetypes": {
                "enabled": enable_archetypes,
                "distribution": {
                    "validator": archetype_validator,
                    "broadcaster": archetype_broadcaster,
                    "explorer": archetype_explorer,
                },
                "transitions": {
                    "validator": {
                        "validator": trans_val_val,
                        "broadcaster": trans_val_broad,
                        "explorer": trans_val_expl,
                    },
                    "broadcaster": {
                        "validator": trans_broad_val,
                        "broadcaster": trans_broad_broad,
                        "explorer": trans_broad_expl,
                    },
                    "explorer": {
                        "validator": trans_expl_val,
                        "broadcaster": trans_expl_broad,
                        "explorer": trans_expl_expl,
                    },
                },
            },
        },
        "posts": {
            "visibility_rounds": int(visibility_rounds),
            "emotions": {
                "admiration": None,
                "amusement": None,
                "anger": None,
                "annoyance": None,
                "approval": None,
                "caring": None,
                "confusion": None,
                "curiosity": None,
                "desire": None,
                "disappointment": None,
                "disapproval": None,
                "disgust": None,
                "embarrassment": None,
                "excitement": None,
                "fear": None,
                "gratitude": None,
                "grief": None,
                "joy": None,
                "love": None,
                "nervousness": None,
                "optimism": None,
                "pride": None,
                "realization": None,
                "relief": None,
                "remorse": None,
                "sadness": None,
                "surprise": None,
                "trust": None,
            },
        },
        "agents": {
            "llm_v_agent": llm_v_agent or "qwen3-vl:8b",
            "reading_from_follower_ratio": float(reading_from_follower_ratio),
            "max_length_thread_reading": int(max_length_thread_reading),
            "max_thread_context_chars": int(max_thread_context_chars),
            "attention_window": int(attention_window),
            "probability_of_daily_follow": float(probability_of_daily_follow),
            "probability_of_secondary_follow": float(probability_of_secondary_follow),
            "age": {"min": 18, "max": 65},
            "political_leaning": [],
            "toxicity_levels": [],
            "languages": [],
            "llm_agents": [] if llm_agents_enabled else [None],
            "education_levels": [],
            "round_actions": {"min": 1, "max": 3},
            "n_interests": {"min": 1, "max": 5},
            "interests": [],
            "big_five": {
                "oe": ["inventive/curious", "consistent/cautious"],
                "co": ["extravagant/careless", "efficient/organized"],
                "ex": ["outgoing/energetic", "solitary/reserved"],
                "ag": ["critical/judgmental", "friendly/compassionate"],
                "ne": ["resilient/confident", "sensitive/nervous"],
            },
            "max_replies_per_round": int(max_replies_per_round),
            "reply_cooldown_rounds": int(reply_cooldown_rounds),
            "thread_browse_mode": "llm",
            "thread_browse_order": "tree_dfs",
            "thread_browse_max_nodes": 400,
            "thread_browse_chunk_size": 20,
            "thread_browse_top_k": 6,
            "thread_browse_max_llm_steps": 3,
            "thread_browse_snippet_chars": 220,
            "thread_browse_context_window": 30,
            "memory_enabled": bool(memory_enabled),
            "memory_pair_limit": int(memory_pair_limit),
            "memory_prompt_max_chars": int(memory_prompt_max_chars),
            "memory_social_decay_lambda": float(memory_social_decay_lambda),
            "memory_social_corruption_rate": float(memory_social_corruption_rate),
            "memory_social_resummarize_every_events": int(
                memory_social_resummarize_every_events
            ),
            "memory_thread_decay_lambda": float(memory_thread_decay_lambda),
            "memory_thread_corruption_rate": float(memory_thread_corruption_rate),
            "memory_thread_resummarize_every_events": int(
                memory_thread_resummarize_every_events
            ),
            "memory_evidence_tail_max": int(memory_evidence_tail_max),
            "memory_digest_update_cadence_rounds": int(
                memory_digest_update_cadence_rounds
            ),
            "memory_digest_events_limit": int(memory_digest_events_limit),
            "memory_cold_start_window": int(memory_cold_start_window),
            "memory_semantic_enabled": bool(memory_semantic_enabled),
            "memory_search_k": int(memory_search_k),
            "memory_search_max_chars": int(memory_search_max_chars),
            "memory_search_time_window_rounds": int(memory_search_time_window_rounds),
            "memory_tier_a_max_chars": int(memory_tier_a_max_chars),
            "memory_tier_b_max_chars": int(memory_tier_b_max_chars),
            "memory_tier_c_max_chars": int(memory_tier_c_max_chars),
            "memory_total_max_chars": int(memory_total_max_chars),
            "memory_tier_c_uncertainty_threshold": float(
                memory_tier_c_uncertainty_threshold
            ),
            "memory_reflection_cadence_rounds": int(memory_reflection_cadence_rounds),
            "memory_reflection_min_events": int(memory_reflection_min_events),
            "memory_reflection_trigger_importance_sum": float(
                memory_reflection_trigger_importance_sum
            ),
            "memory_reflection_max_items_per_run": int(
                memory_reflection_max_items_per_run
            ),
            "memory_embedding_model": str(memory_embedding_model).strip(),
            "memory_embedding_async": bool(memory_embedding_async),
            "memory_importance_mode": str(memory_importance_mode).strip(),
            "memory_backend": (
                "hybrid_semantic" if bool(memory_semantic_enabled) else "simple_recent"
            ),
            "memory_prompt_mode": "subtle_timeline",
            "memory_reply_context_max_chars": int(max_thread_context_chars),
            "memory_vote_signal_only": False,
        },
    }

    if not _apply_population_attributes_to_client_config(config, population_id):
        flash(
            "The selected population has no usable agents or is missing age data. Rebuild or re-upload the population before creating a client.",
            "error",
        )
        return redirect(request.referrer)

    with open(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
    ) as f:
        json.dump(config, f, indent=4)

    data_base_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
    # copy prompts.json into the experiment folder

    prompts_src = get_resource_path(os.path.join("data_schema", "prompts.json"))
    shutil.copyfile(
        prompts_src,
        f"{data_base_path}prompts.json",
    )

    # Create agent population file
    writable_base = get_writable_path()

    if "database_server.db" in exp.db_name:
        # exp.db_name is like "experiments/uid/database_server.db"
        filename = os.path.join(
            writable_base,
            "y_web",
            exp.db_name.split("database_server.db")[0],
            f"{population.name.replace(' ', '')}.json",
        )
    else:
        # Legacy format
        filename = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp.db_name.replace("experiments_", ""),
            f"{population.name.replace(' ', '')}.json",
        )

    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    # get the agent details
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

    # Assign archetypes to agents based on distribution probabilities
    num_agents = len(agents)
    archetype_assignments = []

    if enable_archetypes and num_agents > 0:
        # Build list of active archetypes and their probabilities
        active_archetypes = []
        active_probabilities = []

        if archetype_validator > 0:
            active_archetypes.append("validator")
            active_probabilities.append(archetype_validator)

        if archetype_broadcaster > 0:
            active_archetypes.append("broadcaster")
            active_probabilities.append(archetype_broadcaster)

        if archetype_explorer > 0:
            active_archetypes.append("explorer")
            active_probabilities.append(archetype_explorer)

        # Normalize probabilities if they don't sum to 1
        if len(active_probabilities) > 0:
            total_prob = sum(active_probabilities)
            if total_prob > 0:
                active_probabilities = [p / total_prob for p in active_probabilities]
                # Assign archetypes to agents using numpy random choice
                archetype_assignments = np.random.choice(
                    active_archetypes, size=num_agents, p=active_probabilities
                ).tolist()
            else:
                # If all probabilities are 0, assign None
                archetype_assignments = [None] * num_agents
        else:
            # No active archetypes
            archetype_assignments = [None] * num_agents
    else:
        # Archetypes disabled, assign None to all agents
        archetype_assignments = [None] * num_agents

    res = {"agents": []}
    for idx, a in enumerate(agents):
        custom_prompt = Agent_Profile.query.filter_by(agent_id=a.id).first()

        if custom_prompt:
            custom_prompt = custom_prompt.profile

        # Allocate topics based on specified percentages
        interests = allocate_topics_by_percentage(topics, topic_percentages)

        ints = [interests, len(interests)]

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=a.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        res["agents"].append(
            {
                "name": a.name,
                "email": f"{a.name}@ysocial.it",
                "password": f"{a.name}",
                "age": a.age,
                "type": user_type,  # ,a.ag_type,
                "leaning": a.leaning,
                "interests": ints,
                "oe": a.oe,
                "co": a.co,
                "ex": a.ex,
                "ag": a.ag,
                "ne": a.ne,
                "rec_sys": crecsys,
                "frec_sys": frecsys,
                "language": a.language,
                "owner": exp.owner,
                "education_level": a.education_level,
                "round_actions": int(a.round_actions),
                "gender": a.gender,
                "nationality": a.nationality,
                "toxicity": a.toxicity,
                "is_page": 0,
                "prompts": custom_prompt if custom_prompt else None,
                "daily_activity_level": a.daily_activity_level,
                "profession": a.profession,
                "activity_profile": activity_profile_name,
                "archetype": archetype_assignments[idx],
                "opinions": (
                    {i: random.random() for i in ints[0]} if opinions_enabled else None
                ),  # @todo: check initial opinions
            }
        )

    # get the pages associated with the population
    pages = Page_Population.query.filter_by(population_id=population.id).all()
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

    for p in pages:
        # get pages topics
        page_topics = (
            db.session.query(Exp_Topic, Topic_List)
            .join(Topic_List)
            .filter(Exp_Topic.exp_id == exp_id, Exp_Topic.topic_id == Topic_List.id)
            .all()
        )
        page_topics = [t[1].name for t in page_topics]
        page_topics = list(set(page_topics) & set(topics))

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=p.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        res["agents"].append(
            {
                "name": p.name,
                "email": f"{p.name}@ysocial.it",
                "password": f"{p.name}",
                "age": 0,
                "type": user_type,
                "leaning": p.leaning,
                "interests": [page_topics, len(page_topics)],
                "oe": "",
                "co": "",
                "ex": "",
                "ag": "",
                "ne": "",
                "rec_sys": "",
                "frec_sys": "",
                "language": "english",
                "owner": exp.owner,
                "education_level": "",
                "round_actions": 3,
                "gender": "",
                "nationality": "",
                "toxicity": "none",
                "is_page": 1,
                "feed_url": p.feed,
                "activity_profile": activity_profile_name,
            }
        )

    print(f"Saving agents to {filename}")
    json.dump(res, open(filename, "w"), indent=4)

    # Handle optional network configuration
    if network_model or network_file:
        # get populations for client
        populations = Population.query.filter_by(id=client.population_id).all()
        # get agents for the populations
        agents = Agent_Population.query.filter(
            Agent_Population.population_id.in_([p.id for p in populations])
        ).all()
        # get agent ids for all agents in populations
        agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]

        from y_web.src.system.path_utils import get_writable_path

        BASE = get_writable_path()
        dbtypte = get_db_type()

        if dbtypte == "sqlite":
            exp_folder = exp.db_name.split(os.sep)[1]
        else:
            exp_folder = exp.db_name.removeprefix("experiments_")

        network_path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv"

        if network_file and network_file.filename:
            # Handle uploaded network file
            temp_path = network_path.replace("_network.csv", "_network_temp.csv")
            network_file.save(temp_path)

            try:
                with open(network_path, "w") as o:
                    error, error2 = False, False
                    with open(temp_path, "r") as f:
                        for l in f:
                            l = l.rstrip().split(",")
                            if len(l) < 2:
                                continue

                            agent_1 = Agent.query.filter_by(name=l[0]).all()
                            aids = [a.id for a in agent_1]

                            if agent_1 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error = len(test) == 0
                            else:
                                agent_1 = Page.query.filter_by(name=l[0]).all()
                                aids = [a.id for a in agent_1]

                                if agent_1 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error = len(test) == 0
                                if agent_1 is None:
                                    error = True

                            agent_2 = Agent.query.filter_by(name=l[1]).all()
                            aids = [a.id for a in agent_2]

                            if agent_2 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error2 = len(test) == 0
                            else:
                                agent_2 = Page.query.filter_by(name=l[1]).all()
                                aids = [a.id for a in agent_2]

                                if agent_2 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error2 = len(test) == 0

                                if agent_2 is None:
                                    error2 = True

                            if not error and not error2:
                                o.write(f"{l[0]},{l[1]}\n")
                            else:
                                flash(
                                    f"Agent {l[0]} or {l[1]} not found in network file.",
                                    "warning",
                                )

                os.remove(temp_path)
                client.network_type = "Custom Network"
                db.session.commit()
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(network_path):
                    os.remove(network_path)
                flash(
                    "Network file format error: provide a csv file containing two columns with agent names. No header required.",
                    "error",
                )

        elif network_model:
            # Handle synthetic network generation
            # Extract parameters with defaults
            m = int(network_m) if network_m else 2
            p = float(network_p) if network_p else 0.1
            k = (
                int(request.form.get("network_k"))
                if request.form.get("network_k")
                else 4
            )
            ws_p = (
                float(request.form.get("network_ws_p"))
                if request.form.get("network_ws_p")
                else 0.3
            )
            plc_m = (
                int(request.form.get("network_plc_m"))
                if request.form.get("network_plc_m")
                else 2
            )
            plc_p = (
                float(request.form.get("network_plc_p"))
                if request.form.get("network_plc_p")
                else 0.5
            )
            blocks = (
                int(request.form.get("network_blocks"))
                if request.form.get("network_blocks")
                else 3
            )
            p_in = (
                float(request.form.get("network_p_in"))
                if request.form.get("network_p_in")
                else 0.3
            )
            p_out = (
                float(request.form.get("network_p_out"))
                if request.form.get("network_p_out")
                else 0.05
            )
            tau1 = (
                float(request.form.get("network_tau1"))
                if request.form.get("network_tau1")
                else 2.5
            )
            tau2 = (
                float(request.form.get("network_tau2"))
                if request.form.get("network_tau2")
                else 1.5
            )
            mu = (
                float(request.form.get("network_mu"))
                if request.form.get("network_mu")
                else 0.1
            )
            avg_degree = (
                int(request.form.get("network_avg_degree"))
                if request.form.get("network_avg_degree")
                else 5
            )

            n = len(agent_ids)

            # Generate network based on selected model
            if network_model == "BA":
                g = nx.barabasi_albert_graph(n, m=m)
            elif network_model == "ER":
                g = nx.erdos_renyi_graph(n, p=p)
            elif network_model == "WS":
                g = nx.watts_strogatz_graph(n, k=k, p=ws_p)
            elif network_model == "PLC":
                g = nx.powerlaw_cluster_graph(n, m=plc_m, p=plc_p)
            elif network_model == "C":
                g = nx.complete_graph(n)
            elif network_model == "SBM":
                # Divide nodes into blocks
                block_sizes = [n // blocks] * blocks
                # Add remaining nodes to last block
                block_sizes[-1] += n % blocks
                # Create probability matrix
                probs = [
                    [p_in if i == j else p_out for j in range(blocks)]
                    for i in range(blocks)
                ]
                g = nx.stochastic_block_model(block_sizes, probs)
            elif network_model == "LFR":
                # LFR benchmark with community structure
                # Calculate min_community: at least 5 nodes, at most n/3 to allow multiple communities
                min_community = min(max(5, n // 10), n // 3)
                g = nx.LFR_benchmark_graph(
                    n=n,
                    tau1=tau1,
                    tau2=tau2,
                    mu=mu,
                    average_degree=avg_degree,
                    min_community=min_community,
                )
            else:
                g = None

            if g:
                # since the network is undirected and Y assume directed relations we need to write the edges in both directions
                with open(network_path, "w") as f:
                    for n in g.edges:
                        f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
                        f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
                    f.flush()

                client.network_type = network_model
                db.session.commit()

    from y_web.src.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)
    telemetry.log_event(
        data={
            "action": "create_client",
            "data": {
                "llm_agents_enabled": llm_agents_enabled,
                "days": days,
                "percentage_new_agents_iteration": percentage_new_agents_iteration,
                "percentage_removed_agents_iteration": percentage_removed_agents_iteration,
                "max_length_thread_reading": max_length_thread_reading,
                "reading_from_follower_ratio": reading_from_follower_ratio,
                "probability_of_daily_follow": probability_of_daily_follow,
                "attention_window": attention_window,
                "visibility_rounds": visibility_rounds,
                "actions": {
                    "post": post,
                    "share": share,
                    "image": image,
                    "comment": comment,
                    "read": read,
                    "news": news,
                    "search": search,
                    "vote": vote,
                    "share_link": share_link,
                    "share_image": share_image,
                },
                "llm": user_type,
                "probability_of_secondary_follow": probability_of_secondary_follow,
                "crecsys": crecsys,
                "frecsys": frecsys,
            },
        }
    )

    if bool(opinions_enabled):
        return redirect(
            url_for(
                "clientsr.opinion_configuration_standard",
                idexp=exp_id,
                client_id=client.id,
            )
        )

    # load experiment_details page
    from ..experiments import experiment_details

    return experiment_details(int(exp_id))


def _create_forum_client_internal():
    """Create a forum client with its dedicated configuration pipeline."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    exp_id = request.form.get("id_exp")
    population_id = request.form.get("population_id")

    exp = Exps.query.filter_by(idexp=exp_id).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if getattr(exp, "simulator_type", "Standard") == "HPC":
        flash(
            "Use the dedicated HPC client creation route for this experiment.", "error"
        )
        return redirect(url_for("clientsr.clients_hpc", idexp=exp_id))
    if exp.platform_type != "forum":
        flash(
            "Use the dedicated standard client creation route for this experiment.",
            "error",
        )
        return redirect(url_for("clientsr.clients_standard", idexp=exp_id))

    days = request.form.get("days")
    percentage_new_agents_iteration = request.form.get(
        "percentage_new_agents_iteration"
    )
    percentage_removed_agents_iteration = request.form.get(
        "percentage_removed_agents_iteration"
    )
    max_length_thread_reading = request.form.get("max_length_thread_reading")
    reading_from_follower_ratio = request.form.get("reading_from_follower_ratio")
    probability_of_daily_follow = request.form.get("probability_of_daily_follow")
    probability_of_secondary_follow = request.form.get(
        "probability_of_secondary_follow"
    )
    attention_window = request.form.get("attention_window")
    visibility_rounds = request.form.get("visibility_rounds")
    post = request.form.get("post", "0")
    share = request.form.get("share", "0")
    image = request.form.get("image", "0")
    comment = request.form.get("comment", "0")
    read = request.form.get("read", "0")
    news = request.form.get("news", "0")
    search = request.form.get("search", "0")
    vote = request.form.get("vote", "0")
    share_link = request.form.get("share_link", "0")
    share_image = request.form.get("share_image", "0")
    initial_agents = request.form.get("initial_agents")
    clock_mode = (request.form.get("clock_mode") or "simulated").strip().lower()
    clock_timezone = (request.form.get("clock_timezone") or "Europe/Rome").strip()
    clock_feed_refresh = (
        (request.form.get("clock_feed_refresh") or "hourly").strip().lower()
    )
    max_thread_context_chars = request.form.get("max_thread_context_chars", "3200")
    max_replies_per_round = request.form.get("max_replies_per_round", "2")
    reply_cooldown_rounds = request.form.get("reply_cooldown_rounds", "2")
    memory_enabled = request.form.get("memory_enabled") in {"on", "true", "1", "yes"}
    memory_pair_limit = request.form.get("memory_pair_limit", "5")
    memory_prompt_max_chars = request.form.get("memory_prompt_max_chars", "1600")
    memory_social_decay_lambda = request.form.get("memory_social_decay_lambda", "0.05")
    memory_social_corruption_rate = request.form.get(
        "memory_social_corruption_rate", "0.02"
    )
    memory_social_resummarize_every_events = request.form.get(
        "memory_social_resummarize_every_events", "4"
    )
    memory_thread_decay_lambda = request.form.get("memory_thread_decay_lambda", "0.03")
    memory_thread_corruption_rate = request.form.get(
        "memory_thread_corruption_rate", "0.01"
    )
    memory_thread_resummarize_every_events = request.form.get(
        "memory_thread_resummarize_every_events", "4"
    )
    memory_evidence_tail_max = request.form.get("memory_evidence_tail_max", "8")
    memory_digest_update_cadence_rounds = request.form.get(
        "memory_digest_update_cadence_rounds", "3"
    )
    memory_digest_events_limit = request.form.get("memory_digest_events_limit", "80")
    memory_cold_start_window = request.form.get("memory_cold_start_window", "5")
    memory_semantic_enabled = request.form.get("memory_semantic_enabled") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_search_k = request.form.get("memory_search_k", "8")
    memory_search_max_chars = request.form.get("memory_search_max_chars", "900")
    memory_search_time_window_rounds = request.form.get(
        "memory_search_time_window_rounds", "40"
    )
    memory_tier_a_max_chars = request.form.get("memory_tier_a_max_chars", "350")
    memory_tier_b_max_chars = request.form.get("memory_tier_b_max_chars", "900")
    memory_tier_c_max_chars = request.form.get("memory_tier_c_max_chars", "900")
    memory_total_max_chars = request.form.get("memory_total_max_chars", "2200")
    memory_tier_c_uncertainty_threshold = request.form.get(
        "memory_tier_c_uncertainty_threshold", "0.45"
    )
    memory_reflection_cadence_rounds = request.form.get(
        "memory_reflection_cadence_rounds", "3"
    )
    memory_reflection_min_events = request.form.get(
        "memory_reflection_min_events", "12"
    )
    memory_reflection_trigger_importance_sum = request.form.get(
        "memory_reflection_trigger_importance_sum", "3.5"
    )
    memory_reflection_max_items_per_run = request.form.get(
        "memory_reflection_max_items_per_run", "60"
    )
    memory_embedding_model = request.form.get(
        "memory_embedding_model", "snowflake-arctic-embed:110m"
    )
    memory_embedding_async = request.form.get("memory_embedding_async") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_importance_mode = request.form.get(
        "memory_importance_mode", "heuristic_then_batch_llm"
    )

    if not memory_semantic_enabled:
        memory_embedding_async = False

    llm_agents_enabled = (
        exp.llm_agents_enabled if (exp and hasattr(exp, "llm_agents_enabled")) else True
    )
    experiment_memory_enabled = _memory_enabled_for_client_creation(exp)
    if not experiment_memory_enabled:
        memory_enabled = False
        memory_semantic_enabled = False
        memory_embedding_async = False

    posted_opinion_flag = (
        str(request.form.get("experiment_opinion_dynamics_enabled", "")).strip().lower()
    )
    if posted_opinion_flag in {"true", "1", "yes", "on"}:
        opinions_enabled = True
    elif posted_opinion_flag in {"false", "0", "no", "off"}:
        opinions_enabled = False
    else:
        opinions_enabled = _opinion_dynamics_enabled_for_client_creation(exp)

    # Get LLM parameters from form, or use defaults if LLM agents are disabled
    if llm_agents_enabled:
        llm = request.form.get("llm")
        llm_api_key = request.form.get("llm_api_key")
        llm_max_tokens = request.form.get("llm_max_tokens")
        llm_temperature = request.form.get("llm_temperature")
        llm_v_agent = request.form.get("llm_v_agent")
        llm_v = request.form.get("llm_v")
        llm_v_api_key = request.form.get("llm_v_api_key")
        llm_v_max_tokens = request.form.get("llm_v_max_tokens")
        llm_v_temperature = request.form.get("llm_v_temperature")
        user_type = request.form.get("user_type")
    else:
        # Use default values when LLM agents are disabled
        llm = "http://127.0.0.1:11434/v1"
        llm_api_key = "NULL"
        llm_max_tokens = "-1"
        llm_temperature = "1.5"
        llm_v_agent = "minicpm-v"
        llm_v = "http://127.0.0.1:11434/v1"
        llm_v_api_key = "NULL"
        llm_v_max_tokens = "300"
        llm_v_temperature = "0.5"
        user_type = ""

    crecsys = request.form.get("recsys_type")
    frecsys = request.form.get("frecsys_type")

    # Get agent archetype enabled status
    enable_archetypes = request.form.get("enable_archetypes") == "on"

    # Get agent archetype values (optional, with defaults)
    try:
        archetype_validator = (
            float(request.form.get("archetype_validator", "52")) / 100.0
        )
        archetype_broadcaster = (
            float(request.form.get("archetype_broadcaster", "20")) / 100.0
        )
        archetype_explorer = float(request.form.get("archetype_explorer", "28")) / 100.0
        trans_val_val = float(request.form.get("trans_val_val", "85.3")) / 100.0
        trans_val_broad = float(request.form.get("trans_val_broad", "8.1")) / 100.0
        trans_val_expl = float(request.form.get("trans_val_expl", "6.6")) / 100.0
        trans_broad_broad = float(request.form.get("trans_broad_broad", "72.9")) / 100.0
        trans_broad_val = float(request.form.get("trans_broad_val", "19.5")) / 100.0
        trans_broad_expl = float(request.form.get("trans_broad_expl", "7.5")) / 100.0
        trans_expl_expl = float(request.form.get("trans_expl_expl", "49.0")) / 100.0
        trans_expl_val = float(request.form.get("trans_expl_val", "36.4")) / 100.0
        trans_expl_broad = float(request.form.get("trans_expl_broad", "14.6")) / 100.0
    except (ValueError, TypeError) as e:
        flash(f"Invalid archetype values: {str(e)}", "error")
        return redirect(request.referrer)

    # Validate simulation parameters
    errors = []
    # Validate numeric fields
    try:
        days = int(days)
        # days = -1 means infinite/run-until-stopped
        if days != -1 and days < 1:
            errors.append(
                "Days must be at least 1, or use -1 for infinite duration (run until stopped)"
            )
    except (ValueError, TypeError):
        errors.append("Days must be a valid integer")
    try:
        max_length_thread_reading = int(max_length_thread_reading)
    except (ValueError, TypeError):
        errors.append("Max Length Thread Reading must be a valid integer")
    try:
        max_thread_context_chars = int(max_thread_context_chars)
        if max_thread_context_chars < 200 or max_thread_context_chars > 4800:
            errors.append("Thread Context Max Chars must be between 200 and 4800")
    except (ValueError, TypeError):
        errors.append("Thread Context Max Chars must be a valid integer")
    try:
        attention_window = int(attention_window)
    except (ValueError, TypeError):
        errors.append("Attention Window must be a valid integer")
    try:
        visibility_rounds = int(visibility_rounds)
    except (ValueError, TypeError):
        errors.append("Visibility Rounds must be a valid integer")
    try:
        max_replies_per_round = int(max_replies_per_round)
        if max_replies_per_round < 0:
            errors.append("Max Replies per Round must be at least 0")
    except (ValueError, TypeError):
        errors.append("Max Replies per Round must be a valid integer")
    try:
        reply_cooldown_rounds = int(reply_cooldown_rounds)
        if reply_cooldown_rounds < 0:
            errors.append("Reply Cooldown must be at least 0")
    except (ValueError, TypeError):
        errors.append("Reply Cooldown must be a valid integer")
    try:
        memory_pair_limit = int(memory_pair_limit)
        memory_prompt_max_chars = int(memory_prompt_max_chars)
        memory_search_k = int(memory_search_k)
        memory_search_max_chars = int(memory_search_max_chars)
        memory_search_time_window_rounds = int(memory_search_time_window_rounds)
        memory_tier_a_max_chars = int(memory_tier_a_max_chars)
        memory_tier_b_max_chars = int(memory_tier_b_max_chars)
        memory_tier_c_max_chars = int(memory_tier_c_max_chars)
        memory_total_max_chars = int(memory_total_max_chars)
        memory_reflection_cadence_rounds = int(memory_reflection_cadence_rounds)
        memory_reflection_min_events = int(memory_reflection_min_events)
        memory_reflection_max_items_per_run = int(memory_reflection_max_items_per_run)
        memory_social_resummarize_every_events = int(
            memory_social_resummarize_every_events
        )
        memory_thread_resummarize_every_events = int(
            memory_thread_resummarize_every_events
        )
        memory_evidence_tail_max = int(memory_evidence_tail_max)
        memory_digest_update_cadence_rounds = int(memory_digest_update_cadence_rounds)
        memory_digest_events_limit = int(memory_digest_events_limit)
        memory_cold_start_window = int(memory_cold_start_window)
    except (ValueError, TypeError):
        errors.append("Memory settings must use valid numeric values")
    try:
        memory_social_decay_lambda = float(memory_social_decay_lambda)
        memory_social_corruption_rate = float(memory_social_corruption_rate)
        memory_thread_decay_lambda = float(memory_thread_decay_lambda)
        memory_thread_corruption_rate = float(memory_thread_corruption_rate)
        memory_tier_c_uncertainty_threshold = float(memory_tier_c_uncertainty_threshold)
        memory_reflection_trigger_importance_sum = float(
            memory_reflection_trigger_importance_sum
        )
    except (ValueError, TypeError):
        errors.append("Memory weights must use valid numeric values")

    if clock_mode not in {"simulated", "real_time"}:
        errors.append("Experiment Clock Mode must be either simulated or real_time")
    if clock_feed_refresh not in {"hourly"}:
        errors.append("Feed refresh must be hourly")

    # Validate probability fields (must be float in [0, 1])
    try:
        percentage_new_agents_iteration = float(percentage_new_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% New Agents (daily) must be a valid number")
        percentage_new_agents_iteration = None
    try:
        percentage_removed_agents_iteration = float(percentage_removed_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% Daily Churn must be a valid number")
        percentage_removed_agents_iteration = None
    try:
        reading_from_follower_ratio = float(reading_from_follower_ratio)
    except (ValueError, TypeError):
        errors.append("Timeline Follower Ratio must be a valid number")
        reading_from_follower_ratio = None
    try:
        probability_of_daily_follow = float(probability_of_daily_follow)
    except (ValueError, TypeError):
        errors.append("Probability Daily Follow must be a valid number")
        probability_of_daily_follow = None
    try:
        probability_of_secondary_follow = float(probability_of_secondary_follow)
    except (ValueError, TypeError):
        errors.append("Probability Secondary Follow must be a valid number")
        probability_of_secondary_follow = None

    action_probability_values = {
        "Post new content": post,
        "Comment a Post": comment,
        "Read a content": read,
        "Search a Hashtag": search,
        "Share Link": share_link,
        "Share Image": share_image,
    }
    parsed_action_values = {}
    for field_name, raw_value in action_probability_values.items():
        try:
            parsed_action_values[field_name] = float(raw_value)
        except (ValueError, TypeError):
            errors.append(f"{field_name} must be a valid number")
            parsed_action_values[field_name] = None

    try:
        news = float(news or 0.0)
    except (ValueError, TypeError):
        errors.append("News must be a valid number")
        news = 0.0

    post = parsed_action_values["Post new content"]
    comment = parsed_action_values["Comment a Post"]
    read = parsed_action_values["Read a content"]
    search = parsed_action_values["Search a Hashtag"]
    share_link = parsed_action_values["Share Link"]
    share_image = parsed_action_values["Share Image"]
    share = 0.0
    image = 0.0
    share_link = _forum_effective_link_share(news, share_link)
    news = share_link
    vote = 0.0

    # Check probability ranges for true probabilities.
    probabilities = {
        "% New Agents (daily)": percentage_new_agents_iteration,
        "% Daily Churn": percentage_removed_agents_iteration,
        "Timeline Follower Ratio": reading_from_follower_ratio,
        "Probability Daily Follow": probability_of_daily_follow,
        "Probability Secondary Follow": probability_of_secondary_follow,
    }
    for field_name, value in probabilities.items():
        if value is not None and not (0 <= value <= 1):
            errors.append(f"{field_name} must be between 0 and 1")

    # Forum action relevance fields use relative weights in [0, 10].
    action_scores = {
        "Post new content": post,
        "Comment a Post": comment,
        "Read a content": read,
        "Search a Hashtag": search,
        "Share Link": share_link,
        "Share Image": share_image,
    }
    for field_name, value in action_scores.items():
        if value is not None and not (0 <= value <= 10):
            errors.append(f"{field_name} must be between 0 and 10")

    if errors:
        for error in errors:
            flash(error)
        return redirect(request.referrer)

    # Fetch optional network configuration
    network_model = request.form.get("network_model")
    network_p = request.form.get("network_p")
    network_m = request.form.get("network_m")
    network_file = request.files.get("network_file")

    # Fetch optional hourly activity rates
    hourly_activity_custom = {}
    for hour in range(24):
        hourly_val = request.form.get(f"hourly_{hour}")
        if hourly_val and hourly_val.strip():
            try:
                hourly_activity_custom[str(hour)] = float(hourly_val)
            except ValueError:
                pass  # Ignore invalid values, use defaults

    # get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=exp_id).all()
    topics_ids = [t.topic_id for t in topics]
    # get the topics names from the Topic_list table
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topics = [t.name for t in topics_objs]

    # Get topic interest percentages from form
    topic_percentages = {}
    for topic_obj in topics_objs:
        percentage_key = f"topic_interest_{topic_obj.id}"
        percentage_value = request.form.get(percentage_key, "100")
        try:
            topic_percentages[topic_obj.name] = float(percentage_value)
        except (ValueError, TypeError):
            topic_percentages[topic_obj.name] = 100.0  # Default to 100% if invalid

    # if name already exists, return to the previous page
    if Client.query.filter_by(name=name).first():
        flash("Client name already exists.", "error")
        return redirect(request.referrer)

    exp = Exps.query.filter_by(idexp=exp_id).first()

    # get population
    population = Population.query.filter_by(id=population_id).first()

    if population is None:
        flash("Population not found.", "error")
        return redirect(request.referrer)

    pop_type = infer_population_username_type(population)
    if pop_type not in {None, "forum"}:
        flash(
            f"Population Username Type '{pop_type}' is incompatible with experiment platform 'forum'.",
            "error",
        )
        return redirect(request.referrer)

    initial_agents_int = None
    if initial_agents and initial_agents.strip():
        try:
            initial_agents_int = int(initial_agents)
            if initial_agents_int < 1:
                initial_agents_int = None
        except (ValueError, TypeError):
            initial_agents_int = None

    # check if the population is already assigned to the experiment
    # if not, add it
    pop_exp = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=exp_id
    ).first()
    if not pop_exp:
        pop_exp = Population_Experiment(id_population=population_id, id_exp=exp_id)
        db.session.add(pop_exp)
        db.session.commit()

    # create the Client object
    client = Client(
        name=name,
        descr=descr,
        id_exp=exp_id,
        population_id=population_id,
        days=days,
        percentage_new_agents_iteration=percentage_new_agents_iteration,
        percentage_removed_agents_iteration=percentage_removed_agents_iteration,
        max_length_thread_reading=max_length_thread_reading,
        reading_from_follower_ratio=reading_from_follower_ratio,
        probability_of_daily_follow=probability_of_daily_follow,
        attention_window=attention_window,
        visibility_rounds=visibility_rounds,
        post=post,
        share=share,
        image=image,
        comment=comment,
        read=read,
        news=news,
        search=search,
        vote=vote,
        share_link=share_link,
        llm=llm,
        llm_api_key=llm_api_key,
        llm_max_tokens=llm_max_tokens,
        llm_temperature=llm_temperature,
        llm_v_agent=llm_v_agent,
        llm_v=llm_v,
        llm_v_api_key=llm_v_api_key,
        llm_v_max_tokens=llm_v_max_tokens,
        llm_v_temperature=llm_v_temperature,
        probability_of_secondary_follow=probability_of_secondary_follow,
        crecsys=crecsys,
        frecsys=frecsys,
        status=0,
        archetype_validator=archetype_validator,
        archetype_broadcaster=archetype_broadcaster,
        archetype_explorer=archetype_explorer,
        trans_val_val=trans_val_val,
        trans_val_broad=trans_val_broad,
        trans_val_expl=trans_val_expl,
        trans_broad_broad=trans_broad_broad,
        trans_broad_val=trans_broad_val,
        trans_broad_expl=trans_broad_expl,
        trans_expl_expl=trans_expl_expl,
        trans_expl_val=trans_expl_val,
        trans_expl_broad=trans_expl_broad,
    )

    db.session.add(client)
    db.session.commit()

    # If experiment was completed, reset status to stopped since a new client was added
    if exp.exp_status == "completed":
        exp.exp_status = "stopped"
        db.session.commit()

    # Get LLM URL from environment (set by y_social.py)
    import os

    # get population activity profiles
    activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population_id)
        .all()
    )

    activity_profiles = [a.activity_profile for a in activity_profiles]

    # get all activity profiles from the db where id in activity_profiles
    activity_profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_([a for a in activity_profiles]))
        .all()
    )

    profiles = {ap.name: ap.hours for ap in activity_profiles}

    annotations = exp.annotations.split(",")
    emotion_annotation = "emotion" in annotations

    default_hourly_activity = {
        "0": 0.023,
        "1": 0.021,
        "2": 0.020,
        "3": 0.020,
        "4": 0.018,
        "5": 0.017,
        "6": 0.017,
        "7": 0.018,
        "8": 0.020,
        "9": 0.020,
        "10": 0.021,
        "11": 0.022,
        "12": 0.024,
        "13": 0.027,
        "14": 0.030,
        "15": 0.032,
        "16": 0.032,
        "17": 0.032,
        "18": 0.032,
        "19": 0.031,
        "20": 0.030,
        "21": 0.029,
        "22": 0.027,
        "23": 0.025,
    }

    hourly_activity = {
        str(h): (
            hourly_activity_custom.get(str(h), default_hourly_activity[str(h)])
            if hourly_activity_custom
            else default_hourly_activity[str(h)]
        )
        for h in range(24)
    }

    resolved_clock = {
        "mode": clock_mode,
        "timezone": clock_timezone or "Europe/Rome",
        "feed_refresh": clock_feed_refresh,
    }

    config = {
        "name": name,
        "servers": {
            "llm": llm,
            "llm_api_key": llm_api_key,
            "llm_max_tokens": int(llm_max_tokens),
            "llm_temperature": float(llm_temperature),
            "llm_v": llm_v,
            "llm_v_api_key": llm_v_api_key,
            "llm_v_max_tokens": int(llm_v_max_tokens),
            "llm_v_temperature": float(llm_v_temperature),
            "api": f"http://{exp.server}:{exp.port}/",
        },
        "simulation": {
            "name": name,
            "population": population.name,
            "client": "YClientWeb",
            "days": int(days),
            "slots": 24,
            "initial_agents": initial_agents_int,
            "clock_mode": resolved_clock["mode"],
            "clock_timezone": resolved_clock["timezone"],
            "feed_refresh": resolved_clock["feed_refresh"],
            "percentage_new_agents_iteration": float(percentage_new_agents_iteration),
            "percentage_removed_agents_iteration": float(
                percentage_removed_agents_iteration
            ),
            "activity_profiles": profiles,
            "hourly_activity": hourly_activity,
            "actions_likelihood": {
                "post": float(post),
                "image": 0.0,
                "news": float(share_link) if share_link is not None else 0,
                "comment": float(comment) if comment is not None else 0,
                "read": float(read) if read is not None else 0,
                "share": 0.0,
                "search": float(search) if search is not None else 0,
                "cast": 0.0,
                "share_link": float(share_link) if share_link is not None else 0,
                "share_image": float(share_image) if share_image is not None else 0,
            },
            "emotion_annotation": emotion_annotation,
            "opinion_dynamics": {
                "enabled": bool(opinions_enabled),
            },
            "agent_archetypes": {
                "enabled": enable_archetypes,
                "distribution": {
                    "validator": archetype_validator,
                    "broadcaster": archetype_broadcaster,
                    "explorer": archetype_explorer,
                },
                "transitions": {
                    "validator": {
                        "validator": trans_val_val,
                        "broadcaster": trans_val_broad,
                        "explorer": trans_val_expl,
                    },
                    "broadcaster": {
                        "validator": trans_broad_val,
                        "broadcaster": trans_broad_broad,
                        "explorer": trans_broad_expl,
                    },
                    "explorer": {
                        "validator": trans_expl_val,
                        "broadcaster": trans_expl_broad,
                        "explorer": trans_expl_expl,
                    },
                },
            },
        },
        "posts": {
            "visibility_rounds": int(visibility_rounds),
            "emotions": {
                "admiration": None,
                "amusement": None,
                "anger": None,
                "annoyance": None,
                "approval": None,
                "caring": None,
                "confusion": None,
                "curiosity": None,
                "desire": None,
                "disappointment": None,
                "disapproval": None,
                "disgust": None,
                "embarrassment": None,
                "excitement": None,
                "fear": None,
                "gratitude": None,
                "grief": None,
                "joy": None,
                "love": None,
                "nervousness": None,
                "optimism": None,
                "pride": None,
                "realization": None,
                "relief": None,
                "remorse": None,
                "sadness": None,
                "surprise": None,
                "trust": None,
            },
        },
        "agents": {
            "llm_v_agent": llm_v_agent or "qwen3-vl:8b",
            "reading_from_follower_ratio": float(reading_from_follower_ratio),
            "max_length_thread_reading": int(max_length_thread_reading),
            "max_thread_context_chars": int(max_thread_context_chars),
            "attention_window": int(attention_window),
            "probability_of_daily_follow": float(probability_of_daily_follow),
            "probability_of_secondary_follow": float(probability_of_secondary_follow),
            "age": {"min": 18, "max": 65},
            "political_leaning": [],
            "toxicity_levels": [],
            "languages": [],
            "llm_agents": [] if llm_agents_enabled else [None],
            "education_levels": [],
            "round_actions": {"min": 1, "max": 3},
            "n_interests": {"min": 1, "max": 5},
            "interests": [],
            "big_five": {
                "oe": ["inventive/curious", "consistent/cautious"],
                "co": ["extravagant/careless", "efficient/organized"],
                "ex": ["outgoing/energetic", "solitary/reserved"],
                "ag": ["critical/judgmental", "friendly/compassionate"],
                "ne": ["resilient/confident", "sensitive/nervous"],
            },
            "max_replies_per_round": int(max_replies_per_round),
            "reply_cooldown_rounds": int(reply_cooldown_rounds),
            "thread_browse_mode": "llm",
            "thread_browse_order": "tree_dfs",
            "thread_browse_max_nodes": 400,
            "thread_browse_chunk_size": 20,
            "thread_browse_top_k": 6,
            "thread_browse_max_llm_steps": 3,
            "thread_browse_snippet_chars": 220,
            "thread_browse_context_window": 30,
            "memory_enabled": bool(memory_enabled),
            "memory_pair_limit": int(memory_pair_limit),
            "memory_prompt_max_chars": int(memory_prompt_max_chars),
            "memory_social_decay_lambda": float(memory_social_decay_lambda),
            "memory_social_corruption_rate": float(memory_social_corruption_rate),
            "memory_social_resummarize_every_events": int(
                memory_social_resummarize_every_events
            ),
            "memory_thread_decay_lambda": float(memory_thread_decay_lambda),
            "memory_thread_corruption_rate": float(memory_thread_corruption_rate),
            "memory_thread_resummarize_every_events": int(
                memory_thread_resummarize_every_events
            ),
            "memory_evidence_tail_max": int(memory_evidence_tail_max),
            "memory_digest_update_cadence_rounds": int(
                memory_digest_update_cadence_rounds
            ),
            "memory_digest_events_limit": int(memory_digest_events_limit),
            "memory_cold_start_window": int(memory_cold_start_window),
            "memory_semantic_enabled": bool(memory_semantic_enabled),
            "memory_search_k": int(memory_search_k),
            "memory_search_max_chars": int(memory_search_max_chars),
            "memory_search_time_window_rounds": int(memory_search_time_window_rounds),
            "memory_tier_a_max_chars": int(memory_tier_a_max_chars),
            "memory_tier_b_max_chars": int(memory_tier_b_max_chars),
            "memory_tier_c_max_chars": int(memory_tier_c_max_chars),
            "memory_total_max_chars": int(memory_total_max_chars),
            "memory_tier_c_uncertainty_threshold": float(
                memory_tier_c_uncertainty_threshold
            ),
            "memory_reflection_cadence_rounds": int(memory_reflection_cadence_rounds),
            "memory_reflection_min_events": int(memory_reflection_min_events),
            "memory_reflection_trigger_importance_sum": float(
                memory_reflection_trigger_importance_sum
            ),
            "memory_reflection_max_items_per_run": int(
                memory_reflection_max_items_per_run
            ),
            "memory_embedding_model": str(memory_embedding_model).strip(),
            "memory_embedding_async": bool(memory_embedding_async),
            "memory_importance_mode": str(memory_importance_mode).strip(),
            "memory_prompt_mode": "subtle_forum",
            "memory_reply_context_max_chars": 280,
            "memory_vote_signal_only": True,
            "forum_post_structure_strict": True,
            "memory_cross_thread_callback_min_score": 0.8,
        },
    }

    if not _apply_population_attributes_to_client_config(config, population_id):
        flash(
            "The selected population has no usable agents or is missing age data. Rebuild or re-upload the population before creating a client.",
            "error",
        )
        return redirect(request.referrer)

    # check db type
    if "database_server.db" in exp.db_name:  # sqlite
        uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()
    experiment_folder = os.path.join(BASE_DIR, "y_web", "experiments", uid)
    experiment_config_path = os.path.join(experiment_folder, "config_server.json")
    resolved_clock = {
        "mode": clock_mode,
        "timezone": clock_timezone or "Europe/Rome",
        "feed_refresh": clock_feed_refresh,
    }

    try:
        experiment_config = {}
        if os.path.exists(experiment_config_path):
            with open(experiment_config_path, "r") as config_file:
                experiment_config = json.load(config_file)
        experiment_config["clock"] = {
            "mode": resolved_clock["mode"],
            "timezone": resolved_clock["timezone"],
            "feed_refresh": resolved_clock["feed_refresh"],
        }
        if (
            resolved_clock["mode"] == "real_time"
            and "anchor_date" not in experiment_config["clock"]
        ):
            experiment_config["clock"]["anchor_date"] = (
                __import__("datetime").date.today().isoformat()
            )
        with open(experiment_config_path, "w") as config_file:
            json.dump(experiment_config, config_file, indent=4)
    except Exception:
        pass

    with open(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
    ) as f:
        json.dump(config, f, indent=4)

    data_base_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
    # copy prompts.json into the experiment folder

    prompts_src = get_resource_path(os.path.join("data_schema", "prompts_forum.json"))
    shutil.copyfile(
        prompts_src,
        f"{data_base_path}prompts.json",
    )

    # Create agent population file
    writable_base = get_writable_path()

    if "database_server.db" in exp.db_name:
        # exp.db_name is like "experiments/uid/database_server.db"
        filename = os.path.join(
            writable_base,
            "y_web",
            exp.db_name.split("database_server.db")[0],
            f"{population.name.replace(' ', '')}.json",
        )
    else:
        # Legacy format
        filename = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp.db_name.replace("experiments_", ""),
            f"{population.name.replace(' ', '')}.json",
        )

    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    # get the agent details
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

    # Assign archetypes to agents based on distribution probabilities
    num_agents = len(agents)
    archetype_assignments = []

    if enable_archetypes and num_agents > 0:
        # Build list of active archetypes and their probabilities
        active_archetypes = []
        active_probabilities = []

        if archetype_validator > 0:
            active_archetypes.append("validator")
            active_probabilities.append(archetype_validator)

        if archetype_broadcaster > 0:
            active_archetypes.append("broadcaster")
            active_probabilities.append(archetype_broadcaster)

        if archetype_explorer > 0:
            active_archetypes.append("explorer")
            active_probabilities.append(archetype_explorer)

        # Normalize probabilities if they don't sum to 1
        if len(active_probabilities) > 0:
            total_prob = sum(active_probabilities)
            if total_prob > 0:
                active_probabilities = [p / total_prob for p in active_probabilities]
                # Assign archetypes to agents using numpy random choice
                archetype_assignments = np.random.choice(
                    active_archetypes, size=num_agents, p=active_probabilities
                ).tolist()
            else:
                # If all probabilities are 0, assign None
                archetype_assignments = [None] * num_agents
        else:
            # No active archetypes
            archetype_assignments = [None] * num_agents
    else:
        # Archetypes disabled, assign None to all agents
        archetype_assignments = [None] * num_agents

    res = {"agents": []}
    for idx, a in enumerate(agents):
        custom_prompt = Agent_Profile.query.filter_by(agent_id=a.id).first()

        if custom_prompt:
            custom_prompt = custom_prompt.profile

        # Allocate topics based on specified percentages
        interests = allocate_topics_by_percentage(topics, topic_percentages)

        ints = [interests, len(interests)]

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=a.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        res["agents"].append(
            {
                "name": a.name,
                "email": f"{a.name}@ysocial.it",
                "password": f"{a.name}",
                "age": a.age,
                "type": user_type,  # ,a.ag_type,
                "leaning": a.leaning,
                "interests": ints,
                "oe": a.oe,
                "co": a.co,
                "ex": a.ex,
                "ag": a.ag,
                "ne": a.ne,
                "rec_sys": crecsys,
                "frec_sys": frecsys,
                "language": a.language,
                "owner": exp.owner,
                "education_level": a.education_level,
                "round_actions": int(a.round_actions),
                "gender": a.gender,
                "nationality": a.nationality,
                "toxicity": a.toxicity,
                "is_page": 0,
                "prompts": custom_prompt if custom_prompt else None,
                "daily_activity_level": a.daily_activity_level,
                "profession": a.profession,
                "activity_profile": activity_profile_name,
                "archetype": archetype_assignments[idx],
                "opinions": (
                    {i: random.random() for i in ints[0]}
                    if bool(opinions_enabled)
                    else None
                ),  # @todo: check initial opinions
            }
        )

    # get the pages associated with the population
    pages = Page_Population.query.filter_by(population_id=population.id).all()
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

    for p in pages:
        # get pages topics
        page_topics = (
            db.session.query(Exp_Topic, Topic_List)
            .join(Topic_List)
            .filter(Exp_Topic.exp_id == exp_id, Exp_Topic.topic_id == Topic_List.id)
            .all()
        )
        page_topics = [t[1].name for t in page_topics]
        page_topics = list(set(page_topics) & set(topics))

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=p.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        res["agents"].append(
            {
                "name": p.name,
                "email": f"{p.name}@ysocial.it",
                "password": f"{p.name}",
                "age": 0,
                "type": user_type,
                "leaning": p.leaning,
                "interests": [page_topics, len(page_topics)],
                "oe": "",
                "co": "",
                "ex": "",
                "ag": "",
                "ne": "",
                "rec_sys": "",
                "frec_sys": "",
                "language": "english",
                "owner": exp.owner,
                "education_level": "",
                "round_actions": 3,
                "gender": "",
                "nationality": "",
                "toxicity": "none",
                "is_page": 1,
                "feed_url": p.feed,
                "activity_profile": activity_profile_name,
            }
        )

    print(f"Saving agents to {filename}")
    json.dump(res, open(filename, "w"), indent=4)

    # Handle optional network configuration
    if network_model or network_file:
        # get populations for client
        populations = Population.query.filter_by(id=client.population_id).all()
        # get agents for the populations
        agents = Agent_Population.query.filter(
            Agent_Population.population_id.in_([p.id for p in populations])
        ).all()
        # get agent ids for all agents in populations
        agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]

        from y_web.src.system.path_utils import get_writable_path

        BASE = get_writable_path()
        dbtypte = get_db_type()

        if dbtypte == "sqlite":
            exp_folder = exp.db_name.split(os.sep)[1]
        else:
            exp_folder = exp.db_name.removeprefix("experiments_")

        network_path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv"

        if network_file and network_file.filename:
            # Handle uploaded network file
            temp_path = network_path.replace("_network.csv", "_network_temp.csv")
            network_file.save(temp_path)

            try:
                with open(network_path, "w") as o:
                    error, error2 = False, False
                    with open(temp_path, "r") as f:
                        for l in f:
                            l = l.rstrip().split(",")
                            if len(l) < 2:
                                continue

                            agent_1 = Agent.query.filter_by(name=l[0]).all()
                            aids = [a.id for a in agent_1]

                            if agent_1 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error = len(test) == 0
                            else:
                                agent_1 = Page.query.filter_by(name=l[0]).all()
                                aids = [a.id for a in agent_1]

                                if agent_1 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error = len(test) == 0
                                if agent_1 is None:
                                    error = True

                            agent_2 = Agent.query.filter_by(name=l[1]).all()
                            aids = [a.id for a in agent_2]

                            if agent_2 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error2 = len(test) == 0
                            else:
                                agent_2 = Page.query.filter_by(name=l[1]).all()
                                aids = [a.id for a in agent_2]

                                if agent_2 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error2 = len(test) == 0

                                if agent_2 is None:
                                    error2 = True

                            if not error and not error2:
                                o.write(f"{l[0]},{l[1]}\n")
                            else:
                                flash(
                                    f"Agent {l[0]} or {l[1]} not found in network file.",
                                    "warning",
                                )

                os.remove(temp_path)
                client.network_type = "Custom Network"
                db.session.commit()
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(network_path):
                    os.remove(network_path)
                flash(
                    "Network file format error: provide a csv file containing two columns with agent names. No header required.",
                    "error",
                )

        elif network_model:
            # Handle synthetic network generation
            # Extract parameters with defaults
            m = int(network_m) if network_m else 2
            p = float(network_p) if network_p else 0.1
            k = (
                int(request.form.get("network_k"))
                if request.form.get("network_k")
                else 4
            )
            ws_p = (
                float(request.form.get("network_ws_p"))
                if request.form.get("network_ws_p")
                else 0.3
            )
            plc_m = (
                int(request.form.get("network_plc_m"))
                if request.form.get("network_plc_m")
                else 2
            )
            plc_p = (
                float(request.form.get("network_plc_p"))
                if request.form.get("network_plc_p")
                else 0.5
            )
            blocks = (
                int(request.form.get("network_blocks"))
                if request.form.get("network_blocks")
                else 3
            )
            p_in = (
                float(request.form.get("network_p_in"))
                if request.form.get("network_p_in")
                else 0.3
            )
            p_out = (
                float(request.form.get("network_p_out"))
                if request.form.get("network_p_out")
                else 0.05
            )
            tau1 = (
                float(request.form.get("network_tau1"))
                if request.form.get("network_tau1")
                else 2.5
            )
            tau2 = (
                float(request.form.get("network_tau2"))
                if request.form.get("network_tau2")
                else 1.5
            )
            mu = (
                float(request.form.get("network_mu"))
                if request.form.get("network_mu")
                else 0.1
            )
            avg_degree = (
                int(request.form.get("network_avg_degree"))
                if request.form.get("network_avg_degree")
                else 5
            )

            n = len(agent_ids)

            # Generate network based on selected model
            if network_model == "BA":
                g = nx.barabasi_albert_graph(n, m=m)
            elif network_model == "ER":
                g = nx.erdos_renyi_graph(n, p=p)
            elif network_model == "WS":
                g = nx.watts_strogatz_graph(n, k=k, p=ws_p)
            elif network_model == "PLC":
                g = nx.powerlaw_cluster_graph(n, m=plc_m, p=plc_p)
            elif network_model == "C":
                g = nx.complete_graph(n)
            elif network_model == "SBM":
                # Divide nodes into blocks
                block_sizes = [n // blocks] * blocks
                # Add remaining nodes to last block
                block_sizes[-1] += n % blocks
                # Create probability matrix
                probs = [
                    [p_in if i == j else p_out for j in range(blocks)]
                    for i in range(blocks)
                ]
                g = nx.stochastic_block_model(block_sizes, probs)
            elif network_model == "LFR":
                # LFR benchmark with community structure
                # Calculate min_community: at least 5 nodes, at most n/3 to allow multiple communities
                min_community = min(max(5, n // 10), n // 3)
                g = nx.LFR_benchmark_graph(
                    n=n,
                    tau1=tau1,
                    tau2=tau2,
                    mu=mu,
                    average_degree=avg_degree,
                    min_community=min_community,
                )
            else:
                g = None

            if g:
                # since the network is undirected and Y assume directed relations we need to write the edges in both directions
                with open(network_path, "w") as f:
                    for n in g.edges:
                        f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
                        f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
                    f.flush()

                client.network_type = network_model
                db.session.commit()

    from y_web.src.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)
    telemetry.log_event(
        data={
            "action": "create_client",
            "data": {
                "llm_agents_enabled": llm_agents_enabled,
                "days": days,
                "percentage_new_agents_iteration": percentage_new_agents_iteration,
                "percentage_removed_agents_iteration": percentage_removed_agents_iteration,
                "max_length_thread_reading": max_length_thread_reading,
                "reading_from_follower_ratio": reading_from_follower_ratio,
                "probability_of_daily_follow": probability_of_daily_follow,
                "attention_window": attention_window,
                "visibility_rounds": visibility_rounds,
                "actions": {
                    "post": post,
                    "share": share,
                    "image": image,
                    "comment": comment,
                    "read": read,
                    "news": share_link,
                    "search": search,
                    "vote": vote,
                    "share_link": share_link,
                },
                "llm": user_type,
                "probability_of_secondary_follow": probability_of_secondary_follow,
                "crecsys": crecsys,
                "frecsys": frecsys,
            },
        }
    )

    if bool(opinions_enabled):
        return redirect(
            url_for(
                "clientsr.opinion_configuration_forum",
                idexp=exp_id,
                client_id=client.id,
            )
        )

    # load experiment_details page
    from ..experiments import experiment_details

    return experiment_details(int(exp_id))


@clientsr.route("/admin/create_standard_client", methods=["POST"])
@login_required
def create_standard_client():
    """Create a standard microblogging client."""
    return _create_standard_client_internal()


@clientsr.route("/admin/create_forum_client", methods=["POST"])
@login_required
def create_forum_client():
    """Create a forum client."""
    return _create_forum_client_internal()


@clientsr.route("/admin/create_hpc_client", methods=["POST"])
@login_required
def create_hpc_client_route():
    """Create an HPC client."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    exp_id = request.form.get("id_exp")
    population_id = request.form.get("population_id")
    exp = Exps.query.filter_by(idexp=exp_id).first()

    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if getattr(exp, "simulator_type", "Standard") != "HPC":
        flash(
            "Use the dedicated standard or forum client creation route for this experiment.",
            "error",
        )
        if exp.platform_type == "forum":
            return redirect(url_for("clientsr.clients_forum", idexp=exp_id))
        return redirect(url_for("clientsr.clients_standard", idexp=exp_id))

    return create_hpc_client(exp, name, descr, population_id, request.form)


@clientsr.route("/admin/create_client", methods=["POST"])
@login_required
def create_client():
    """Backward-compatible dispatcher for client creation routes."""
    check_privileges(current_user.username)

    exp_id = request.form.get("id_exp")
    exp = Exps.query.filter_by(idexp=exp_id).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    if getattr(exp, "simulator_type", "Standard") == "HPC":
        return create_hpc_client_route()
    if exp.platform_type == "forum":
        return create_forum_client()
    return create_standard_client()


@clientsr.route("/admin/delete_client/<int:uid>")
@login_required
def delete_client(uid):
    """Delete client."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    exp_id = client.id_exp
    pop_id = client.population_id

    Client_Execution.query.filter_by(client_id=uid).delete()
    db.session.commit()

    # delete association of population and experiment if no other client is using it
    pop_exp = Population_Experiment.query.filter_by(
        id_population=client.population_id, id_exp=exp_id
    ).first()
    if pop_exp:
        other_clients = Client.query.filter_by(
            id_exp=exp_id, population_id=client.population_id
        ).all()
        if len(other_clients) == 0:
            db.session.delete(pop_exp)
            db.session.commit()

    db.session.delete(client)
    db.session.commit()

    from y_web.src.system.path_utils import get_writable_path

    # remove the db file on the client
    BASE_PATH = get_writable_path()
    path = f"{BASE_PATH}{os.sep}external{os.sep}YClient{os.sep}experiments{os.sep}{client.name}.db"
    if os.path.exists(path):
        os.remove(path)
    else:
        print(f"File {path} does not exist.")

    # remove agent population
    Population_Experiment.query.filter_by(id_population=pop_id).delete()
    db.session.commit()

    from ..experiments import experiment_details

    return experiment_details(exp_id)


@clientsr.route("/admin/delete_adhoc_client/<int:idexp>/<path:client_key>")
@login_required
def delete_adhoc_client_route(idexp, client_key):
    """Delete a file-backed ad hoc client and its sidecar files."""
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=idexp).first()
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    try:
        delete_adhoc_client(exp, client_key)
        flash("Ad hoc client deleted.", "success")
    except FileNotFoundError:
        flash("Ad hoc client configuration not found.", "error")
    except Exception as exc:
        flash(f"Could not delete ad hoc client: {exc}", "error")

    from ..experiments import experiment_details

    return experiment_details(idexp)


def _get_experiment_mode(experiment):
    """Return the route/template mode for the given experiment."""
    if getattr(experiment, "simulator_type", "Standard") == "HPC":
        return "hpc"
    if getattr(experiment, "platform_type", "microblogging") == "forum":
        return "forum"
    return "standard"


def _get_experiment_folder_name(experiment):
    """Return the experiment folder name used under y_web/experiments."""
    dbtype = get_db_type()
    if dbtype == "sqlite":
        return experiment.db_name.split(os.sep)[1]
    return experiment.db_name.removeprefix("experiments_")


def _read_json_if_exists(path):
    """Load a JSON file if it exists, otherwise return None."""
    if not os.path.exists(path):
        return None
    with open(path, "r") as handle:
        return json.load(handle)


def _opinion_dynamics_enabled_for_client_creation(experiment):
    """Resolve whether opinion dynamics are active for client creation flows."""
    if experiment is None:
        return False

    annotations = {
        item.strip()
        for item in (experiment.annotations or "").split(",")
        if item and item.strip()
    }
    default_enabled = "opinions" in annotations

    try:
        from y_web.src.system.path_utils import get_writable_path

        config_name = (
            "server_config.json"
            if getattr(experiment, "simulator_type", "Standard") == "HPC"
            else "config_server.json"
        )
        config_path = os.path.join(
            get_writable_path(),
            "y_web",
            "experiments",
            _get_experiment_folder_name(experiment),
            config_name,
        )
        config = _read_json_if_exists(config_path)
        if isinstance(config, dict):
            return bool(
                config.get(
                    "opinion_dynamics_enabled",
                    config.get("opinions_enabled", default_enabled),
                )
            )
    except Exception:
        pass

    return default_enabled


def _memory_enabled_for_client_creation(experiment):
    """Resolve whether experiment-level memory is enabled for client creation flows."""
    if experiment is None:
        return False

    supported = bool(bool(_experiment_uses_llm_agents(experiment)))
    if not supported:
        return False

    try:
        from y_web.src.system.path_utils import get_writable_path

        config_name = (
            "server_config.json"
            if getattr(experiment, "simulator_type", "Standard") == "HPC"
            else "config_server.json"
        )
        config_path = os.path.join(
            get_writable_path(),
            "y_web",
            "experiments",
            _get_experiment_folder_name(experiment),
            config_name,
        )
        config = _read_json_if_exists(config_path)
        if isinstance(config, dict):
            memory_cfg = config.get("memory")
            if isinstance(memory_cfg, dict):
                return bool(memory_cfg.get("enabled"))
    except Exception:
        pass

    return False


def _get_client_population_pages(client):
    """Fetch pages associated with the client's population."""
    return (
        db.session.query(Page, Page_Population)
        .join(Page_Population)
        .filter(Page_Population.population_id == client.population_id)
        .all()
    )


def _extract_llm_names_from_population_payload(agents_payload):
    """Collect unique non-page LLM names from a population payload."""
    llms = []
    if agents_payload is not None:
        for agent in agents_payload.get("agents", []):
            if not agent.get("is_page", 0):
                agent_type = agent.get("type")
                if agent_type:
                    llms.append(agent_type)
    return ",".join(list(set(llms)))


def _build_hourly_activity_chart_series(activity):
    """Convert hourly activity dict to plotting arrays."""
    idx = []
    data = []
    for hour in range(24):
        idx.append(str(hour))
        data.append(activity.get(str(hour), 0))
    return idx, data
