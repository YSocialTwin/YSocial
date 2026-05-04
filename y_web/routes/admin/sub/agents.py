"""
Agent management routes.

Administrative routes for creating, editing, and managing individual AI agents
including their profiles, demographics, personality traits, and behavioral
settings.
"""

import json
import os
import random
import re
from pathlib import Path
from typing import Optional

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import current_user, login_required

from y_web import db
from y_web.src.agents.custom_features import (
    delete_agent_custom_features,
    encode_opinion_feature,
    opinion_group_by_name,
    replace_agent_custom_features,
    summarize_agent_custom_features,
)
from y_web.src.agents.platform import normalize_population_username_type
from y_web.src.content.cover_images import available_cover_image_urls
from y_web.src.external_runtime.registry import EXTERNAL_DIR, runtime_spec
from y_web.src.llm.ollama_manager import get_ollama_models
from y_web.src.llm.vllm_manager import get_llm_models
from y_web.src.models import (
    ActivityProfile,
    Agent,
    Agent_Ext,
    Agent_Population,
    Agent_Profile,
    Content_Recsys,
    Education,
    Follow_Recsys,
    ForumImageFeedResource,
    ForumRssFeedResource,
    Languages,
    Leanings,
    Nationalities,
    OpinionGroup,
    Page,
    Page_Population,
    Population,
    Profession,
    Topic_List,
    Toxicity_Levels,
)
from y_web.src.system.miscellanea import (
    check_privileges,
    llm_backend_status,
    ollama_status,
)

agents = Blueprint("agents", __name__)

HELLO_WORLD_DAILY_BUDGET_FEATURE = "daily_budget"


PLUGIN_REGISTRY_RELATIVE_PATHS = (
    Path("meta") / "registry.json",
    Path("plugins_exposed") / "agent_types.json",
    Path("plugin_exposed") / "agent_types.json",
)


def _runtime_installed(repo_key: str) -> bool:
    try:
        return runtime_spec(repo_key).path.exists()
    except Exception:
        return False


def _page_resources_available() -> bool:
    return any(
        _runtime_installed(repo_key)
        for repo_key in (
            "microblogging_client",
            "microblogging_server",
            "hpc_simulator",
        )
    )


def _deployment_group_key(tags: list[str]) -> str:
    normalized = set(tags or [])
    if {"microblogging", "forum"}.issubset(normalized):
        return "all"
    if normalized == {"microblogging"}:
        return "microblogging"
    if normalized == {"forum"}:
        return "forum"
    return "all"


def _group_agent_resource_cards(cards: list[dict]) -> list[dict]:
    definitions = [
        {
            "key": "all",
            "label": "All Experiments",
            "description": "Agent types that can be deployed in both microblogging and forum simulations.",
        },
        {
            "key": "microblogging",
            "label": "Microblogging Only",
            "description": "Agent types that currently target microblogging experiments only.",
        },
        {
            "key": "forum",
            "label": "Forum Only",
            "description": "Agent types that currently target forum experiments only.",
        },
    ]

    grouped = []
    for definition in definitions:
        section_cards = [
            card
            for card in cards
            if _deployment_group_key(card.get("deployment_tags", []))
            == definition["key"]
        ]
        if not section_cards:
            continue
        grouped.append(
            {
                "key": definition["key"],
                "label": definition["label"],
                "description": definition["description"],
                "cards": section_cards,
            }
        )
    return grouped


def _manifest_paths():
    manifests = []
    for repo_dir in sorted(EXTERNAL_DIR.iterdir()) if EXTERNAL_DIR.exists() else []:
        if not repo_dir.is_dir():
            continue
        for relative_path in PLUGIN_REGISTRY_RELATIVE_PATHS:
            manifest_path = repo_dir / relative_path
            if manifest_path.exists():
                manifests.append((repo_dir.name, manifest_path))
                break
    return manifests


def _custom_agent_slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    tokens = [token for token in cleaned.split() if token and token != "agent"]
    if not tokens:
        return "custom"
    if len(tokens) == 1:
        return tokens[0]
    return tokens[0][0] + "".join(tokens[1:])


def _plugin_agent_specs() -> list[dict]:
    specs = []
    for repo_name, manifest_path in _manifest_paths():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        for entry in payload.get("agent_types", []):
            agent_type = str(entry.get("agent_type") or "").strip()
            if not agent_type:
                continue
            display_name = str(entry.get("display_name") or agent_type)
            slug = _custom_agent_slug(display_name)
            accepted_slugs = {slug, agent_type}
            # Compatibility for existing Hello World records created before generalization.
            if slug == "hworld":
                accepted_slugs.add("hword")

            specs.append(
                {
                    "slug": slug,
                    "accepted_slugs": sorted(accepted_slugs),
                    "agent_type": agent_type,
                    "display_name": display_name,
                    "description": str(
                        entry.get("description") or "Plugin-defined agent type."
                    ),
                    "parameters": entry.get("parameters", []) or [],
                    "parameter_sections": entry.get("parameter_sections", []) or [],
                    "repo_name": repo_name,
                    "manifest_path": str(manifest_path),
                }
            )
    return specs


def _parameter_default_value(parameter: dict):
    return parameter.get("default")


def _custom_agent_parameter_sections(spec: dict) -> list[dict]:
    section_defs = spec.get("parameter_sections") or []
    section_lookup = {str(section.get("key")): section for section in section_defs}
    ordered_keys = [
        str(section.get("key")) for section in section_defs if section.get("key")
    ]
    buckets = {}

    for parameter in spec.get("parameters", []):
        section_key = str(parameter.get("section") or "general")
        if section_key not in buckets:
            section_meta = section_lookup.get(section_key, {})
            buckets[section_key] = {
                "key": section_key,
                "label": str(
                    section_meta.get("label") or section_key.replace("_", " ").title()
                ),
                "description": str(section_meta.get("description") or "").strip(),
                "parameters": [],
            }
            if section_key not in ordered_keys:
                ordered_keys.append(section_key)
        enriched = dict(parameter)
        enriched["default"] = _parameter_default_value(parameter)
        buckets[section_key]["parameters"].append(enriched)

    return [buckets[key] for key in ordered_keys if key in buckets]


def _find_custom_agent_spec(agent_slug: Optional[str]):
    if not agent_slug:
        return None
    for spec in _plugin_agent_specs():
        if agent_slug in spec["accepted_slugs"]:
            return spec
    return None


def _discover_plugin_agent_types() -> list[dict]:
    plugin_cards = []
    for spec in _plugin_agent_specs():
        parameters = spec["parameters"]
        required_parameters = [
            str(parameter.get("name"))
            for parameter in parameters
            if parameter.get("required")
        ]
        optional_parameters = [
            str(parameter.get("name"))
            for parameter in parameters
            if not parameter.get("required")
        ]

        plugin_cards.append(
            {
                "title": spec["display_name"],
                "subtitle": f"Plugin agent type · {spec['repo_name']}",
                "icon": "package",
                "accent": "#7c3aed",
                "surface": "linear-gradient(135deg, #faf5ff 0%, #f5f3ff 55%, #ffffff 100%)",
                "border": "#ddd6fe",
                "description": spec["description"],
                "highlights": [
                    f"Type id: {spec['agent_type']}",
                    f"{len(required_parameters)} required parameters",
                    (
                        "Optional parameters: " + ", ".join(optional_parameters[:3])
                        if optional_parameters
                        else "No optional parameters declared"
                    ),
                ],
                "meta": {
                    "manifest_path": spec["manifest_path"],
                    "required_parameters": required_parameters,
                    "optional_parameters": optional_parameters,
                    "repo_name": spec["repo_name"],
                    "slug": spec["slug"],
                },
                "cta_label": f"Open {spec['display_name'].replace(' Agent', '')} Builder",
                "cta_href": f"/admin/custom_agent/{spec['slug']}",
                "secondary_label": "Configure this plugin agent from a manifest-driven custom agent page.",
                "deployment_tags": ["microblogging", "forum"],
                "is_plugin": True,
            }
        )

    return plugin_cards


def _agent_builder_context(**overrides):
    available_profile_pics = []
    available_cover_images = []
    try:
        users_img_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            ),
            "static",
            "assets",
            "img",
            "users",
        )
        available_profile_pics = sorted(
            [
                filename
                for filename in os.listdir(users_img_dir)
                if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
        )
    except Exception:
        available_profile_pics = []

    try:
        available_cover_images = [
            os.path.basename(path) for path in available_cover_image_urls()
        ]
    except Exception:
        available_cover_images = []

    context = {
        "populations": Population.query.filter(Population.pop_type.is_(None)).all(),
        "models": get_llm_models(),
        "llm_backend": llm_backend_status(),
        "professions": Profession.query.all(),
        "nationalities": Nationalities.query.all(),
        "education_levels": Education.query.all(),
        "leanings": Leanings.query.all(),
        "languages": Languages.query.all(),
        "interest_topics": Topic_List.query.order_by(Topic_List.name.asc()).all(),
        "opinion_groups": OpinionGroup.query.order_by(
            OpinionGroup.lower_bound.asc()
        ).all(),
        "toxicity_levels": Toxicity_Levels.query.all(),
        "activity_profiles": ActivityProfile.query.all(),
        "page_kind": "standard",
        "table_title": "Available Agents",
        "create_title": "Create Agent",
        "form_action": "/admin/create_agent",
        "submit_label": "Create",
        "loading_message": "Creating agent...",
        "delete_orphaned_visible": True,
        "list_endpoint": "/admin/agents_data",
        "details_url_prefix": "/admin/agent_details/",
        "delete_url_prefix": "/admin/delete_agent/",
        "builder_intro_title": "Quick Reference Guide",
        "builder_intro_lines": [
            {
                "title": "Synthetic Agents",
                "body": "Virtual entities that represent social media users in simulations. They can be configured with different demographic information, interests, and personality traits.",
            },
            {
                "title": "Profiles vs. Advanced Roleplay",
                "body": "The agent profile is a set of predefined characteristics that can be used to specify its behavior (through LLM pre-prompts). The advanced roleplay allows to specify a custom pre-prompt that overrides the other configuration variables.",
            },
        ],
        "hello_populations": [],
        "available_profile_pics": available_profile_pics,
        "available_cover_images": available_cover_images,
    }
    context.update(overrides)
    return context


def _render_standard_agent_builder():
    return render_template("admin/agents.html", **_agent_builder_context())


def _custom_population_rows(slug: str, accepted_slugs: list[str]) -> list[dict]:
    populations = (
        Population.query.filter(Population.pop_type.in_(accepted_slugs))
        .order_by(Population.name.asc())
        .all()
    )
    rows = []
    for population in populations:
        rows.append(
            {
                "id": population.id,
                "name": population.name,
                "descr": population.descr,
                "agent_count": Agent_Population.query.filter_by(
                    population_id=population.id
                ).count(),
            }
        )
    return rows


def _custom_agent_rows(spec: dict) -> list[dict]:
    query = Agent.query.filter(Agent.ag_type.in_(spec["accepted_slugs"])).order_by(
        Agent.id.desc()
    )
    agents_res = query.all()
    ext_map = _agent_ext_map([agent.id for agent in agents_res])
    rows = []
    for agent in agents_res:
        activity_profile_name = None
        if agent.activity_profile:
            profile = ActivityProfile.query.get(agent.activity_profile)
            activity_profile_name = profile.name if profile else None
        row = {
            "id": agent.id,
            "name": agent.name,
            "activity_profile": activity_profile_name or "Not assigned",
        }
        for parameter in spec["parameters"]:
            param_name = str(parameter.get("name") or "")
            if param_name in {"name", "activity_profile"}:
                continue
            value = ext_map.get(agent.id, {}).get(param_name, "")
            parameter_type = str(parameter.get("type") or "")
            if (
                parameter_type.startswith("array")
                or parameter_type.startswith("enum_multi[")
            ) and value:
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        value = ", ".join(str(item) for item in parsed)
                except Exception:
                    pass
            row[param_name] = value
        rows.append(row)
    return rows


def _custom_agent_grid_columns(spec: dict) -> list[dict]:
    columns = [
        {"id": "name", "name": "Name"},
        {"id": "activity_profile", "name": "Activity Profile"},
    ]
    for parameter in spec["parameters"]:
        param_name = str(parameter.get("name") or "")
        if param_name in {"name", "activity_profile"}:
            continue
        columns.append(
            {
                "id": param_name,
                "name": param_name.replace("_", " ").title(),
            }
        )
    return columns


def _render_custom_agent_builder(spec: dict):
    return render_template(
        "admin/custom_agent.html",
        custom_spec=spec,
        custom_parameter_sections=_custom_agent_parameter_sections(spec),
        _custom_agent_form_value=_custom_agent_form_value,
        custom_populations=_custom_population_rows(
            spec["slug"], spec["accepted_slugs"]
        ),
        custom_agents=_custom_agent_rows(spec),
        custom_agent_columns=_custom_agent_grid_columns(spec),
        populations=Population.query.filter(
            Population.pop_type.in_(spec["accepted_slugs"])
        )
        .order_by(Population.name.asc())
        .all(),
        activity_profiles=ActivityProfile.query.all(),
    )


def _population_matches_agent_type(agent_type, pop_type):
    if agent_type in (None, ""):
        return pop_type in (None, "")
    spec = _find_custom_agent_spec(agent_type)
    if spec:
        return pop_type in spec["accepted_slugs"]
    return pop_type in (None, "")


def _resolve_custom_population_assignment(spec: dict):
    population = request.form.get("population")
    new_population_name = (request.form.get("new_population_name") or "").strip()
    new_population_descr = (request.form.get("new_population_descr") or "").strip()
    if population == "__new__":
        if not new_population_name:
            flash(f"A new {spec['display_name']} population name is required.", "error")
            return None
        existing = Population.query.filter_by(name=new_population_name).first()
        if existing:
            flash(
                f"Population name '{new_population_name}' already exists. Please choose a different name.",
                "error",
            )
            return None
        pop = Population(
            name=new_population_name,
            descr=new_population_descr,
            username_type="microblogging",
            pop_type=spec["slug"],
            size=0,
        )
        db.session.add(pop)
        db.session.commit()
        return pop

    if not population or population == "none":
        flash(
            f"{spec['display_name']} agents must be assigned to at least one matching custom population.",
            "error",
        )
        return None

    pop = Population.query.filter_by(id=population).first()
    if pop is None or pop.pop_type not in spec["accepted_slugs"]:
        flash(
            f"{spec['display_name']} agents can only be assigned to matching custom populations.",
            "error",
        )
        return None
    return pop


def _agent_listing_query(ag_type_filter):
    if ag_type_filter is None:
        return Agent.query.filter(Agent.ag_type.is_(None))
    return Agent.query.filter(Agent.ag_type == ag_type_filter)


def _agent_ext_map(agent_ids):
    if not agent_ids:
        return {}
    entries = Agent_Ext.query.filter(Agent_Ext.agent_id.in_(agent_ids)).all()
    ext_map = {}
    for entry in entries:
        ext_map.setdefault(entry.agent_id, {})[entry.feature_name] = entry.feature_value
    return ext_map


def _upsert_agent_ext(agent_id, feature_name, feature_value):
    entry = Agent_Ext.query.filter_by(
        agent_id=agent_id, feature_name=feature_name
    ).first()
    if entry is None:
        entry = Agent_Ext(
            agent_id=agent_id,
            feature_name=feature_name,
            feature_value=str(feature_value),
        )
        db.session.add(entry)
    else:
        entry.feature_value = str(feature_value)


def _normalize_custom_agent_parameter_value(parameter: dict, raw_value):
    param_type = str(parameter.get("type") or "").strip().lower()
    if param_type.startswith("enum_multi[") and param_type.endswith("]"):
        allowed = [
            option.strip()
            for option in param_type[len("enum_multi[") : -1].split(",")
            if option.strip()
        ]
        if isinstance(raw_value, (list, tuple)):
            items = raw_value
        else:
            items = [raw_value]
        normalized = []
        for item in items:
            value = str(item or "").strip()
            if not value:
                continue
            if value not in allowed:
                raise ValueError(
                    f"Unsupported value '{value}' for {parameter.get('name')}"
                )
            if value not in normalized:
                normalized.append(value)
        return json.dumps(normalized)

    value = str(raw_value).strip()
    if param_type.startswith("array"):
        return json.dumps([item.strip() for item in value.split(",") if item.strip()])
    if param_type in {"number", "float"}:
        normalized = value.replace(",", ".")
        return str(float(normalized))
    if param_type == "integer":
        normalized = value.replace(",", ".")
        return str(int(float(normalized)))
    return value


def _custom_agent_form_value(parameter: dict):
    param_name = str(parameter.get("name") or "")
    param_type = str(parameter.get("type") or "").strip().lower()
    if param_type.startswith("enum_multi[") and param_type.endswith("]"):
        raw_values = [
            str(value).strip()
            for value in request.form.getlist(param_name)
            if str(value).strip()
        ]
        if raw_values:
            return raw_values
        default = parameter.get("default")
        if isinstance(default, list):
            return [str(value).strip() for value in default if str(value).strip()]
        if default is None:
            return []
        return [str(default).strip()]

    raw_value = request.form.get(param_name)
    if raw_value not in (None, ""):
        return raw_value
    default = parameter.get("default")
    if default is None:
        return ""
    return str(default)


def _delete_agent_ext(agent_id):
    for ext_entry in Agent_Ext.query.filter_by(agent_id=agent_id).all():
        db.session.delete(ext_entry)


def _parse_structured_agent_features_from_form() -> list[dict]:
    opinion_groups = opinion_group_by_name()
    entries: list[dict] = []

    interest_keys = request.form.getlist("interest_feature_key[]")
    opinion_group_names = request.form.getlist("interest_feature_opinion_group[]")
    stubborn_flags = request.form.getlist("interest_feature_stubborn[]")

    for idx, raw_interest in enumerate(interest_keys):
        interest_name = str(raw_interest or "").strip()
        if not interest_name:
            continue
        entries.append({"feature_type": "interest", "key": interest_name, "value": ""})
        group_name = (
            str(opinion_group_names[idx]).strip()
            if idx < len(opinion_group_names)
            else ""
        )
        if group_name:
            opinion_group = opinion_groups.get(group_name)
            if opinion_group is None:
                raise ValueError(f"Unknown opinion group '{group_name}'.")
            stubborn = idx < len(stubborn_flags) and str(stubborn_flags[idx]) == "1"
            entries.append(
                {
                    "feature_type": "opinion",
                    "key": interest_name,
                    "value": encode_opinion_feature(
                        group_name=group_name,
                        opinion_value=(
                            (
                                float(opinion_group.lower_bound)
                                + float(opinion_group.upper_bound)
                            )
                            / 2.0
                        ),
                        stubborn=stubborn,
                    ),
                }
            )

    custom_keys = request.form.getlist("custom_feature_key[]")
    custom_values = request.form.getlist("custom_feature_value[]")
    for idx, raw_key in enumerate(custom_keys):
        key = str(raw_key or "").strip()
        if not key:
            continue
        value = str(custom_values[idx]).strip() if idx < len(custom_values) else ""
        entries.append(
            {
                "feature_type": "custom",
                "key": key,
                "value": value,
            }
        )

    return entries


def _ensure_interest_topics_exist(feature_entries: list[dict]) -> None:
    seen: set[str] = set()
    for entry in feature_entries:
        if entry.get("feature_type") != "interest":
            continue
        topic_name = str(entry.get("key") or "").strip()
        if not topic_name:
            continue
        normalized = topic_name.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        existing_topic = (
            db.session.query(Topic_List)
            .filter(db.func.lower(Topic_List.name) == normalized)
            .first()
        )
        if existing_topic is None:
            db.session.add(Topic_List(name=topic_name))


def _agent_listing_response(ag_type_filter, *, hello_mode=False):
    query = _agent_listing_query(ag_type_filter)

    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Agent.name.like(f"%{search}%")))
    total = query.count()

    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            allowed_columns = ["name", "activity_profile"]
            if hello_mode:
                allowed_columns.append("daily_budget")
            else:
                allowed_columns.extend(["profession", "age", "daily_activity_level"])
            if name not in allowed_columns:
                name = "name"
            if name == "daily_budget":
                name = "daily_activity_level"
            if name == "activity_profile":
                col = ActivityProfile.name
                if direction == "-":
                    col = col.desc()
                order.append(col)
            else:
                col = getattr(Agent, name)
                if direction == "-":
                    col = col.desc()
                order.append(col)
        if order:
            if any("activity_profile" in str(o) for o in order):
                query = query.outerjoin(
                    ActivityProfile, Agent.activity_profile == ActivityProfile.id
                )
            query = query.order_by(*order)

    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        query = query.offset(start).limit(length)

    agents_res = query.all()
    ext_map = _agent_ext_map([agent.id for agent in agents_res]) if hello_mode else {}

    data = []
    for agent in agents_res:
        activity_profile_data = None
        if agent.activity_profile:
            profile = ActivityProfile.query.get(agent.activity_profile)
            if profile:
                activity_profile_data = {"name": profile.name, "hours": profile.hours}

        row = {
            "id": agent.id,
            "name": agent.name,
            "activity_profile": activity_profile_data,
        }
        if hello_mode:
            row["daily_budget"] = ext_map.get(agent.id, {}).get(
                HELLO_WORLD_DAILY_BUDGET_FEATURE, agent.daily_activity_level
            )
        else:
            row.update(
                {
                    "age": agent.age,
                    "profession": agent.profession,
                    "daily_activity_level": agent.daily_activity_level,
                }
            )
        data.append(row)

    return {"data": data, "total": total}


def _agent_builder_for_type(agent_type):
    if agent_type not in (None, ""):
        spec = _find_custom_agent_spec(agent_type)
        if spec:
            return _render_custom_agent_builder(spec)
    return _render_standard_agent_builder()


@agents.route("/admin/agents_dashboard")
@login_required
def agents_dashboard():
    """Display the agent resource hub used to access agent construction pages."""
    check_privileges(current_user.username)

    synthetic_agent_count = Agent.query.count()
    page_count = Page.query.count()
    forum_rss_feed_count = ForumRssFeedResource.query.count()
    forum_image_feed_count = ForumImageFeedResource.query.count()
    population_count = Population.query.count()
    activity_profile_count = ActivityProfile.query.count()
    populations_with_agents = (
        db.session.query(Agent_Population.population_id).distinct().count()
    )
    populations_with_pages = (
        db.session.query(Page_Population.population_id).distinct().count()
    )
    media_page_count = Page.query.filter_by(page_type="media").count()
    plugin_agent_cards = _discover_plugin_agent_types()
    agent_resource_cards = [
        {
            "title": "Synthetic Agents",
            "subtitle": "Built-in resource",
            "icon": "cpu",
            "accent": "#0f766e",
            "surface": "linear-gradient(135deg, #ecfeff 0%, #f0fdfa 55%, #ffffff 100%)",
            "border": "#99f6e4",
            "description": "Design individual user personas with demographics, political leaning, personality traits, activity profiles, and role-play directives.",
            "highlights": [
                f"{synthetic_agent_count} agents currently defined",
                f"{populations_with_agents} populations already contain custom agents",
                f"{activity_profile_count} reusable activity profiles available",
            ],
            "cta_label": "Open Agent Builder",
            "cta_href": "/admin/agents",
            "secondary_label": "Manage existing agents, remove orphaned entries, and create fully custom profiles.",
            "meta": {},
            "deployment_tags": ["microblogging", "forum"],
            "is_plugin": False,
        }
    ]

    if _page_resources_available():
        agent_resource_cards.append(
            {
                "title": "News Pages",
                "subtitle": "Built-in resource",
                "icon": "file-text",
                "accent": "#1d4ed8",
                "surface": "linear-gradient(135deg, #eff6ff 0%, #eef2ff 55%, #ffffff 100%)",
                "border": "#bfdbfe",
                "description": "Create institutional and media pages that publish content, expose RSS feeds, and shape the information environment seen by agents.",
                "highlights": [
                    f"{page_count} pages currently defined",
                    f"{media_page_count} media pages with news-oriented behavior",
                    f"{populations_with_pages} populations already include pages",
                ],
                "cta_label": "Open Page Builder",
                "cta_href": "/admin/pages",
                "secondary_label": "Configure page identity, leaning, feed sources, and upload page collections in bulk.",
                "meta": {},
                "deployment_tags": ["microblogging"],
                "is_plugin": False,
            }
        )

    agent_resource_cards.extend(
        [
            {
                "title": "Forum RSS Feeds",
                "subtitle": "Built-in resource",
                "icon": "rss",
                "accent": "#c2410c",
                "surface": "linear-gradient(135deg, #fff7ed 0%, #fffbeb 55%, #ffffff 100%)",
                "border": "#fdba74",
                "description": "Validate and register reusable RSS sources for forum simulations. Once saved, the same feed can be assigned across multiple experiments.",
                "highlights": [
                    f"{forum_rss_feed_count} reusable RSS feeds available",
                    "Validation happens once in the dashboard workspace",
                    "Forum experiments assign from the shared registry",
                ],
                "cta_label": "Manage RSS Resources",
                "cta_href": "/admin/forum_rss_resources",
                "secondary_label": "Create feed entries centrally, then reuse them across forum simulations without revalidating the same source each time.",
                "meta": {},
                "deployment_tags": ["forum"],
                "is_plugin": False,
            },
            {
                "title": "Forum Image Feeds",
                "subtitle": "Built-in resource",
                "icon": "image",
                "accent": "#7c3aed",
                "surface": "linear-gradient(135deg, #f5f3ff 0%, #faf5ff 55%, #ffffff 100%)",
                "border": "#c4b5fd",
                "description": "Register reusable subreddit-based image feeds for forum experiments, including interest tags used during image ingestion.",
                "highlights": [
                    f"{forum_image_feed_count} reusable image feeds available",
                    "Subreddit validation is done before assignment",
                    "The same subreddit definition can be reused safely",
                ],
                "cta_label": "Manage Image Resources",
                "cta_href": "/admin/forum_image_resources",
                "secondary_label": "Maintain the canonical image-feed catalog here and assign only the feeds needed by each forum simulation.",
                "meta": {},
                "deployment_tags": ["forum"],
                "is_plugin": False,
            },
        ]
    )

    agent_resource_cards.extend(plugin_agent_cards)
    agent_resource_groups = _group_agent_resource_cards(agent_resource_cards)

    return render_template(
        "admin/agents_dashboard.html",
        agent_resource_groups=agent_resource_groups,
        agent_resources_summary={
            "total_agents": synthetic_agent_count,
            "total_pages": page_count,
            "forum_rss_feeds": forum_rss_feed_count,
            "forum_image_feeds": forum_image_feed_count,
            "total_populations": population_count,
            "activity_profiles": activity_profile_count,
            "plugin_agent_types": len(plugin_agent_cards),
            "page_resources_available": _page_resources_available(),
            "resource_cards": len(agent_resource_cards),
        },
    )


@agents.route("/admin/agents")
@login_required
def agent_data():
    """
    Display agent management page.

    Returns:
        Rendered agent data template with available models
    """
    check_privileges(current_user.username)

    return _render_standard_agent_builder()


@agents.route("/admin/custom_agent")
@agents.route("/admin/custom_agent/<agent_slug>")
@login_required
def custom_agent_data(agent_slug=None):
    """Display plugin-defined custom agent management page."""
    check_privileges(current_user.username)
    spec = _find_custom_agent_spec(agent_slug or request.args.get("slug"))
    if spec is None:
        flash("Custom agent type not found.", "error")
        return redirect("/admin/agents_dashboard")
    return _render_custom_agent_builder(spec)


@agents.route("/admin/hello_agent")
@login_required
def hello_agent_data():
    """Compatibility redirect for the previous Hello World route."""
    spec = _find_custom_agent_spec("hello_world")
    if spec is None:
        flash("Hello World agent plugin is not currently installed.", "error")
        return redirect("/admin/agents_dashboard")
    return redirect(f"/admin/custom_agent/{spec['slug']}")


@agents.route("/admin/agents_data")
@login_required
def agents_data():
    """Display agents data page."""
    return _agent_listing_response(None)


@agents.route("/admin/hello_agents_data")
@login_required
def hello_agents_data():
    """Display Hello World agents data page."""
    spec = _find_custom_agent_spec("hello_world")
    if spec is None:
        return {"data": [], "total": 0}
    return _agent_listing_response(spec["slug"], hello_mode=True)


@agents.route("/admin/create_agent", methods=["POST"])
@login_required
def create_agent():
    """
    Create a new AI agent from form data.

    Returns:
        Redirect to agent data page
    """
    check_privileges(current_user.username)

    user_type = (request.form.get("user_type") or "").strip() or None
    population = request.form.get("population")
    name = request.form.get("name")
    age = request.form.get("age")
    gender = request.form.get("gender")
    language = request.form.get("language")
    nationality = request.form.get("nationality")
    education_level = request.form.get("education_level")
    leaning = request.form.get("leaning")
    oe = request.form.get("oe")
    co = request.form.get("co")
    ex = request.form.get("ex")
    ag = request.form.get("ag")
    ne = request.form.get("ne")
    toxicity = request.form.get("toxicity")
    alt_profile = request.form.get("alt_profile")
    profile_pic = request.form.get("profile_pic")
    cover_image = request.form.get("cover_image")
    daily_activity_level = request.form.get("daily_user_activity")
    profession = request.form.get("profession")
    activity_profile_id = request.form.get("activity_profile") or None
    try:
        structured_features = _parse_structured_agent_features_from_form()
        _ensure_interest_topics_exist(structured_features)
    except ValueError as exc:
        flash(str(exc), "error")
        return _agent_builder_for_type(user_type)

    # Validate that agent name is unique
    existing_agent = Agent.query.filter_by(name=name).first()
    if existing_agent:
        flash(f"Agent name '{name}' already exists. Please choose a different name.")
        return _agent_builder_for_type(user_type)

    if population not in (None, "", "none"):
        assigned_population = Population.query.filter_by(id=population).first()
        if assigned_population is None or not _population_matches_agent_type(
            user_type, assigned_population.pop_type
        ):
            flash(
                "Standard agents can only be assigned to standard populations.", "error"
            )
            return _agent_builder_for_type(user_type)

    agent = Agent(
        name=name,
        age=age,
        ag_type=user_type,
        leaning=leaning,
        ag=ag,
        co=co,
        oe=oe,
        ne=ne,
        ex=ex,
        language=language,
        education_level=education_level,
        round_actions=random.randint(1, 3),
        toxicity=toxicity,
        nationality=nationality,
        gender=gender,
        profile_pic=profile_pic,
        cover_image=cover_image,
        daily_activity_level=int(daily_activity_level),
        profession=profession,
        activity_profile=int(activity_profile_id) if activity_profile_id else None,
    )

    db.session.add(agent)
    db.session.flush()
    db.session.commit()
    replace_agent_custom_features(agent.id, structured_features)
    db.session.commit()

    if population != "none":
        ap = Agent_Population(agent_id=agent.id, population_id=population)
        db.session.add(ap)
        db.session.commit()

    if alt_profile != "":
        agent_profile = Agent_Profile(agent_id=agent.id, profile=alt_profile)
        db.session.add(agent_profile)
        db.session.commit()

    return _agent_builder_for_type(user_type)


@agents.route("/admin/create_custom_agent/<agent_slug>", methods=["POST"])
@login_required
def create_custom_agent(agent_slug):
    """Create a plugin-defined custom agent."""
    check_privileges(current_user.username)
    spec = _find_custom_agent_spec(agent_slug)
    if spec is None:
        flash("Custom agent type not found.", "error")
        return redirect("/admin/agents_dashboard")

    name = (request.form.get("name") or "").strip()
    activity_profile_id = request.form.get("activity_profile") or None
    assigned_population = _resolve_custom_population_assignment(spec)
    if assigned_population is None:
        return _render_custom_agent_builder(spec)

    existing_agent = Agent.query.filter_by(name=name).first()
    if existing_agent:
        flash(f"Agent name '{name}' already exists. Please choose a different name.")
        return _render_custom_agent_builder(spec)

    agent = Agent(
        name=name,
        ag_type=spec["slug"],
        round_actions=1,
        activity_profile=int(activity_profile_id) if activity_profile_id else None,
    )
    db.session.add(agent)
    db.session.commit()

    for parameter in spec["parameters"]:
        param_name = str(parameter.get("name") or "")
        if param_name in {"name", "activity_profile"}:
            continue
        parameter_type = str(parameter.get("type") or "").strip().lower()
        if parameter_type.startswith("enum_multi[") and parameter_type.endswith("]"):
            raw_value = request.form.getlist(param_name)
            if not raw_value and isinstance(parameter.get("default"), list):
                raw_value = parameter.get("default")
        else:
            raw_value = request.form.get(param_name)
            if raw_value in (None, "") and parameter.get("default") not in (None, ""):
                raw_value = str(parameter.get("default"))
        if raw_value in (None, "", []):
            continue
        try:
            value = _normalize_custom_agent_parameter_value(parameter, raw_value)
        except ValueError:
            flash(
                f"Field '{param_name.replace('_', ' ')}' contains an invalid value.",
                "error",
            )
            db.session.delete(agent)
            db.session.commit()
            return _render_custom_agent_builder(spec)
        _upsert_agent_ext(agent.id, param_name, value)
    db.session.commit()

    ap = Agent_Population(agent_id=agent.id, population_id=assigned_population.id)
    db.session.add(ap)
    db.session.commit()

    return _render_custom_agent_builder(spec)


@agents.route("/admin/create_hello_agent", methods=["POST"])
@login_required
def create_hello_agent():
    """Compatibility wrapper for the previous Hello World creation route."""
    spec = _find_custom_agent_spec("hello_world")
    if spec is None:
        flash("Hello World agent plugin is not currently installed.", "error")
        return redirect("/admin/agents_dashboard")
    return create_custom_agent(spec["slug"])


@agents.route("/admin/agent_details/<int:uid>")
@login_required
def agent_details(uid):
    """Handle agent details operation."""
    check_privileges(current_user.username)
    # get agent details
    agent = Agent.query.filter_by(id=uid).first()

    # get agent populations along with population names and ids
    agent_populations = (
        db.session.query(Agent_Population, Population)
        .join(Population)
        .filter(Agent_Population.agent_id == uid)
        .all()
    )

    # get agent profiles
    agent_profiles = Agent_Profile.query.filter_by(agent_id=uid).first()

    pops = [(p[1].name, p[1].id) for p in agent_populations]

    # get compatible populations only
    if agent.ag_type not in (None, ""):
        custom_spec = _find_custom_agent_spec(agent.ag_type)
        if custom_spec:
            populations = (
                Population.query.filter(
                    Population.pop_type.in_(custom_spec["accepted_slugs"])
                )
                .order_by(Population.name.asc())
                .all()
            )
        else:
            populations = []
    else:
        custom_spec = None
        populations = (
            Population.query.filter(Population.pop_type.is_(None))
            .order_by(Population.name.asc())
            .all()
        )

    # Get agent's activity profile
    activity_profile = None
    if agent.activity_profile:
        activity_profile = ActivityProfile.query.filter_by(
            id=agent.activity_profile
        ).first()

    llm_backend = llm_backend_status()
    ext_features = {
        ext.feature_name: ext.feature_value
        for ext in Agent_Ext.query.filter_by(agent_id=uid).all()
    }
    structured_features = summarize_agent_custom_features(uid)
    back_href = (
        f"/admin/custom_agent/{custom_spec['slug']}" if custom_spec else "/admin/agents"
    )
    back_label = f"{custom_spec['display_name']}s" if custom_spec else "Agents"

    return render_template(
        "admin/agent_details.html",
        agent=agent,
        agent_populations=pops,
        profile=agent_profiles,
        populations=populations,
        activity_profile=activity_profile,
        llm_backend=llm_backend,
        agent_ext_features=ext_features,
        agent_structured_features=structured_features,
        agent_back_href=back_href,
        agent_back_label=back_label,
    )


@agents.route("/admin/add_to_population", methods=["POST"])
@login_required
def add_to_population():
    """
    Add an agent to a population from form data.

    Returns:
        Redirect to agent details page
    """
    check_privileges(current_user.username)

    agent_id = request.form.get("agent_id")
    population_id = request.form.get("population_id")
    agent = Agent.query.filter_by(id=agent_id).first()
    target_population = Population.query.filter_by(id=population_id).first()

    if agent is None or target_population is None:
        flash("Invalid agent or population selection.", "error")
        return agent_details(agent_id)

    if not _population_matches_agent_type(agent.ag_type, target_population.pop_type):
        custom_spec = _find_custom_agent_spec(agent.ag_type) if agent.ag_type else None
        if custom_spec:
            flash(
                f"{custom_spec['display_name']} agents can only be assigned to matching custom populations.",
                "error",
            )
        else:
            flash(
                "Standard agents can only be assigned to standard populations.", "error"
            )
        return agent_details(agent_id)

    # check if the agent is already in the population
    ap = Agent_Population.query.filter_by(
        agent_id=agent_id, population_id=population_id
    ).first()
    if ap:
        return agent_details(agent_id)

    ap = Agent_Population(agent_id=agent_id, population_id=population_id)

    db.session.add(ap)
    db.session.commit()

    return agent_details(agent_id)


@agents.route("/admin/delete_agent/<int:uid>")
@login_required
def delete_agent(uid):
    """Delete agent."""
    check_privileges(current_user.username)

    agent = Agent.query.filter_by(id=uid).first()
    if agent is None:
        flash("Agent not found.", "error")
        return redirect("/admin/agents")

    agent_type = agent.ag_type if agent else None

    agent_population = Agent_Population.query.filter_by(agent_id=uid).all()
    if agent_population and agent_type in (None, ""):
        flash("Agent is assigned to a population. Cannot delete.")
        return _agent_builder_for_type(agent_type)

    db.session.delete(agent)

    # delete agent_population entries
    for ap in agent_population:
        db.session.delete(ap)

    # delete agent_profile entries
    agent_profile = Agent_Profile.query.filter_by(agent_id=uid).all()
    for ap in agent_profile:
        db.session.delete(ap)

    _delete_agent_ext(uid)
    delete_agent_custom_features(uid)
    db.session.commit()

    return _agent_builder_for_type(agent_type)


@agents.route("/admin/delete_orphaned_agents", methods=["POST"])
@login_required
def delete_orphaned_agents():
    """Delete all agents that do not belong to any population."""
    check_privileges(current_user.username)

    # Find all agents that don't have any population assignment
    # Using a subquery to find agents not in Agent_Population
    orphaned_agents = (
        Agent.query.outerjoin(Agent_Population, Agent.id == Agent_Population.agent_id)
        .filter(Agent_Population.id == None)
        .all()
    )

    deleted_count = 0
    for agent in orphaned_agents:
        # Delete associated agent profiles first
        agent_profiles = Agent_Profile.query.filter_by(agent_id=agent.id).all()
        for profile in agent_profiles:
            db.session.delete(profile)

        _delete_agent_ext(agent.id)
        delete_agent_custom_features(agent.id)

        # Delete the agent
        db.session.delete(agent)
        deleted_count += 1

    db.session.commit()

    flash(f"Successfully deleted {deleted_count} orphaned agent(s).")
    return agent_data()
