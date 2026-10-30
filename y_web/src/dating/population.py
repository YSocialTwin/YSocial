"""Dating populations: validation, storage and summary (plan S2, IR-D-05).

A dating population is stored like any other: a ``population`` row (``username_type`` ``dating``) and standard
``agents`` rows, with the dating-only fields (location, genders sought, photos, latent variables ...) in the
custom features of the agents (``y_web.src.dating.agent_fields``, decision D-10). The document that satisfies
the population schema of YDating is rebuilt from those tables (``load_document``) when the runtime needs its
input file and for export; uploads and generated populations are validated against the schema and then stored
as agents. No file keeps the population. The functions without a database import are pure.
"""

import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from y_web.src.dating import DATING_PLATFORM

POPULATION_SCHEMA_FILE = os.path.join("schemas", "population", "population.json")
GENERATOR_SCRIPT = os.path.join("scripts", "generate_population.py")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
GENERATE_TIMEOUT_SECONDS = 120
MAX_GENERATED_AGENTS = 20000


class DatingPopulationError(ValueError):
    """A population document or generator parameter is not valid (``problems`` carry the reasons)."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def _repo_dir(repo_dir: Optional[str] = None) -> str:
    if repo_dir:
        return repo_dir
    from y_web.src.system.path_utils import get_external_repo_dir

    return get_external_repo_dir("YDating")


def _location(error) -> str:
    return "/".join(str(p) for p in error.absolute_path) or "<root>"


def validate_population(data: Any, repo_dir: Optional[str] = None) -> List[str]:
    """Problems of a population document, each prefixed with the path of the offending value (empty = valid).

    The schema is the one of YDating, read from the runtime's folder: there is a single definition. The
    cross-checks of ``YDating.population.load_population`` (unique usernames, age window, interests in the
    catalogue) are repeated here so that a document refused by the run is refused at upload.
    """
    import jsonschema

    schema_path = os.path.join(_repo_dir(repo_dir), POPULATION_SCHEMA_FILE)
    try:
        with open(schema_path, "r", encoding="utf-8") as handle:
            schema = json.load(handle)
    except OSError as exc:
        return [f"<schema>: cannot read the YDating population schema ({exc})"]
    validator = jsonschema.Draft7Validator(schema)
    problems = sorted(
        f"{_location(e)}: {e.message}" for e in validator.iter_errors(data)
    )
    if problems:
        return problems[:50]

    seen = set()
    catalogue = set(data.get("interests") or [])
    for index, agent in enumerate(data["agents"]):
        where = f"agents/{index}"
        username = agent["username"]
        if username in seen:
            problems.append(f"{where}/username: duplicate username {username!r}")
        seen.add(username)
        profile = agent.get("profile") or {}
        if profile.get("age_min", 18) > profile.get("age_max", 99):
            problems.append(f"{where}/profile: age_min is greater than age_max")
        if catalogue and not set(agent.get("interests") or []) <= catalogue:
            problems.append(f"{where}/interests: an interest is not in the catalogue")
    if len(data["agents"]) < 2:
        problems.append("agents: a population needs at least two agents")
    return problems[:50]


def validate_agent_document(agent: Any, repo_dir: Optional[str] = None) -> List[str]:
    """Problems of one agent document against the ``agent`` definition of the YDating population schema."""
    import jsonschema

    schema_path = os.path.join(_repo_dir(repo_dir), POPULATION_SCHEMA_FILE)
    try:
        with open(schema_path, "r", encoding="utf-8") as handle:
            schema = json.load(handle)
    except OSError as exc:
        return [f"<schema>: cannot read the YDating population schema ({exc})"]
    validator = jsonschema.Draft7Validator(
        {"$ref": "#/definitions/agent", "definitions": schema["definitions"]}
    )
    return sorted(f"{_location(e)}: {e.message}" for e in validator.iter_errors(agent))[
        :50
    ]


def summarize(data: Dict[str, Any]) -> Dict[str, Any]:
    """Counts the admin pages show (public attributes only; latent variables are not summarized)."""
    agents = data.get("agents") or []

    def count(values):
        out: Dict[str, int] = {}
        for value in values:
            out[value] = out.get(value, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    ages = [a["age"] for a in agents]
    profiles = [a.get("profile") or {} for a in agents]
    return {
        "size": len(agents),
        "age_min": min(ages) if ages else None,
        "age_max": max(ages) if ages else None,
        "genders": count(a["gender"] for a in agents),
        "intents": count(p.get("intent", "unsure") for p in profiles),
        "cities": count(p.get("city") or "" for p in profiles if p.get("city")),
        "languages": count(a.get("language", "en") for a in agents),
        "interests": count(i for a in agents for i in a.get("interests") or []),
        "with_photos": sum(1 for a in agents if a.get("photos")),
        "with_bio": sum(1 for p in profiles if p.get("bio")),
    }


def profile_card(agent: Dict[str, Any]) -> Dict[str, Any]:
    """What another user sees of an agent: the public card. Latent variables are never part of it."""
    profile = agent.get("profile") or {}
    return {
        "username": agent["username"],
        "age": agent["age"],
        "gender": agent["gender"],
        "city": profile.get("city", ""),
        "intent": profile.get("intent", "unsure"),
        "bio": profile.get("bio", ""),
        "prompt_answers": dict(profile.get("prompt_answers") or {}),
        "interests": list(agent.get("interests") or []),
        "photos": [p.get("caption", "") for p in agent.get("photos") or []],
    }


def read_upload(raw: bytes) -> Any:
    """Parse an uploaded document; a file that is not JSON is reported as a problem, not an exception."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise DatingPopulationError(["<file>: larger than 50 MB"])
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DatingPopulationError([f"<file>: not a JSON document ({exc})"]) from None


def clean_name(value: Optional[str]) -> str:
    name = re.sub(r"\s+", " ", (value or "").strip())
    name = "".join(ch for ch in name if ch not in '/\\:*?"<>|')
    return name[:50].strip()


# -- storage in the standard agent tables (decision D-10) -----------------------------------------------
def _schema(repo_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        with open(
            os.path.join(_repo_dir(repo_dir), POPULATION_SCHEMA_FILE),
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _prepare_fields(repo_dir: Optional[str] = None) -> Dict[str, str]:
    """Column limits of ``agents`` and the JSON types of the dating fields (both read, not copied)."""
    from y_web.src.dating import agent_fields
    from y_web.src.models import Agent

    agent_fields.set_limits(
        {
            c.name: c.type.length
            for c in Agent.__table__.columns
            if getattr(c.type, "length", None)
        }
    )
    return agent_fields.field_types(_schema(repo_dir))


def store_agents(population_id: int, data: Dict[str, Any]) -> int:
    """Create the ``agents`` rows of a validated population document and link them to ``population_id``.

    One standard agent per document agent, its interests as ``interest`` features and the dating-only fields as
    ``custom`` features (``dating.*``). Returns the number of agents.
    """
    from sqlalchemy import insert

    from y_web import db
    from y_web.src.dating import agent_fields
    from y_web.src.models import Agent, Agent_Custom_Feature, Agent_Population

    _prepare_fields()
    agents, extras = [], []
    for doc in data["agents"]:
        columns, interests, custom = agent_fields.agent_to_rows(doc)
        agents.append(Agent(**columns))
        extras.append((interests, custom))
    db.session.add_all(agents)
    db.session.flush()
    db.session.execute(
        insert(Agent_Population),
        [{"agent_id": a.id, "population_id": population_id} for a in agents],
    )
    rows = []
    for agent, (interests, custom) in zip(agents, extras):
        for interest in interests:
            rows.append(
                {
                    "agent_id": agent.id,
                    "feature_type": "interest",
                    "key": interest,
                    "value": None,
                }
            )
        for item in custom:
            rows.append(
                {
                    "agent_id": agent.id,
                    "feature_type": "custom",
                    "key": item["key"],
                    "value": item["value"],
                }
            )
    if rows:
        db.session.execute(insert(Agent_Custom_Feature), rows)
    db.session.commit()
    return len(agents)


def _linked_agents(population_id: int):
    from sqlalchemy import select

    from y_web import db
    from y_web.src.models import Agent, Agent_Population

    return (
        db.session.execute(
            select(Agent)
            .join(Agent_Population, Agent_Population.agent_id == Agent.id)
            .where(Agent_Population.population_id == population_id)
            .order_by(Agent.id)
        )
        .scalars()
        .all()
    )


def load_document(
    population_id: int, repo_dir: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """The population document rebuilt from the agent tables (``None`` when the population has no agents).

    Used wherever the runtime needs its input file (client creation), for the details page and for the export.
    The interest catalogue is the union of the agents' interests in order of first appearance.
    """
    from sqlalchemy import select

    from y_web import db
    from y_web.src.dating import agent_fields
    from y_web.src.models import Agent_Custom_Feature

    types = _prepare_fields(repo_dir)
    agents = _linked_agents(population_id)
    if not agents:
        return None
    interests: Dict[int, List[str]] = {a.id: [] for a in agents}
    custom: Dict[int, Dict[str, Optional[str]]] = {a.id: {} for a in agents}
    ids = list(interests)
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        for row in db.session.scalars(
            select(Agent_Custom_Feature)
            .where(Agent_Custom_Feature.agent_id.in_(chunk))
            .order_by(Agent_Custom_Feature.id)
        ):
            if row.feature_type == "interest":
                if row.key not in interests[row.agent_id]:
                    interests[row.agent_id].append(row.key)
            elif row.feature_type == "custom":
                custom[row.agent_id][row.key] = row.value
    columns_of = list(agent_fields.COLUMN_FIELDS.values()) + list(
        agent_fields.PERSONALITY
    )
    docs, catalogue = [], []
    for agent in agents:
        columns = {c: getattr(agent, c) for c in columns_of}
        doc = agent_fields.rows_to_agent(
            columns, interests[agent.id], custom[agent.id], types
        )
        docs.append(doc)
        for interest in doc.get("interests", []):
            if interest not in catalogue:
                catalogue.append(interest)
    return {"interests": catalogue, "agents": docs}


def remove_agents(population_id: int) -> int:
    """Delete the agents of a dating population that belong to no other population, with their features."""
    from sqlalchemy import delete, func, select

    from y_web import db
    from y_web.src.models import (
        Agent,
        Agent_Custom_Feature,
        Agent_Ext,
        Agent_Population,
        Agent_Profile,
    )

    own = []
    for agent in _linked_agents(population_id):
        others = db.session.scalar(
            select(func.count())
            .select_from(Agent_Population)
            .where(
                Agent_Population.agent_id == agent.id,
                Agent_Population.population_id != population_id,
            )
        )
        if not others:
            own.append(agent.id)
    for start in range(0, len(own), 500):
        chunk = own[start : start + 500]
        for model in (Agent_Custom_Feature, Agent_Ext, Agent_Profile):
            db.session.execute(delete(model).where(model.agent_id.in_(chunk)))
        db.session.execute(
            delete(Agent_Population).where(Agent_Population.agent_id.in_(chunk))
        )
        db.session.execute(delete(Agent).where(Agent.id.in_(chunk)))
    db.session.commit()
    return len(own)


def generate(
    n_agents: int,
    seed: Optional[int] = None,
    language: Optional[str] = None,
    repo_dir: Optional[str] = None,
    tmp_dir: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a synthetic population with the generator of YDating (``scripts/generate_population.py``).

    ``config`` holds the other generator parameters (``schemas/population/generator.json``; see
    ``config_from_form``); ``n_agents``, ``seed`` and ``language`` take precedence.

    Run as a child process, so that the runtime's dependencies never need to be importable by YWeb. The output
    is validated like an upload.
    """
    import tempfile

    try:
        n_agents = int(n_agents)
    except (TypeError, ValueError):
        raise DatingPopulationError(["n_agents: must be an integer"]) from None
    if not 2 <= n_agents <= MAX_GENERATED_AGENTS:
        raise DatingPopulationError(
            [f"n_agents: must be between 2 and {MAX_GENERATED_AGENTS}"]
        )
    repo = _repo_dir(repo_dir)
    script = os.path.join(repo, GENERATOR_SCRIPT)
    if not os.path.isfile(script):
        raise DatingPopulationError(["<generator>: YDating is not present"])
    with tempfile.TemporaryDirectory(dir=tmp_dir) as work:
        out = os.path.join(work, "population.json")
        cmd = [sys.executable, script, "-n", str(n_agents), "-o", out]
        if seed not in (None, ""):
            try:
                cmd += ["--seed", str(int(seed))]
            except (TypeError, ValueError):
                raise DatingPopulationError(["seed: must be an integer"]) from None
        params = dict(config or {})
        for own in ("n_agents", "seed"):
            params.pop(own, None)
        if language:
            params["language"] = str(language)
        if params:
            cfg_path = os.path.join(work, "generator.json")
            with open(cfg_path, "w", encoding="utf-8") as handle:
                json.dump(params, handle)
            cmd += ["--config", cfg_path]
        try:
            proc = subprocess.run(
                cmd,
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=GENERATE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DatingPopulationError(
                [f"<generator>: could not be run ({exc})"]
            ) from None
        if proc.returncode != 0 or not os.path.isfile(out):
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise DatingPopulationError(
                [f"<generator>: failed ({detail[-1] if detail else proc.returncode})"]
            )
        with open(out, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    problems = validate_population(data, repo)
    if problems:
        raise DatingPopulationError(problems)
    return data


# ------------------------------------------------------------------ generator form

# appearance attributes drawn from label weights (same names as the population schema)
APPEARANCE_LABELS = (
    "hair_color",
    "hair_length",
    "hair_style",
    "eye_color",
    "skin_tone",
    "build",
    "facial_hair",
    "distinctive_features",
    "mood",
    "photo_style",
)
PERSONALITY_TRAITS = ("oe", "co", "ex", "ag", "ne")
AFFECTIVE_TRAITS = (
    "sensitivity",
    "reward_sensitivity",
    "resilience",
    "visibility_need",
)
LATENT_VARIABLES = ("attractiveness", "selectivity", "responsiveness")
WEIGHT_FIELDS = (  # form field -> generator key
    ("genders", "genders"),
    ("intents", "intents"),
    ("nationalities", "nationalities"),
    ("education_levels", "education_levels"),
    ("leanings", "leanings"),
    ("professions", "professions"),
    ("match_recsys", "match_recsys"),
)


def parse_weights(text: Any, field: str, separator: str = ",") -> Dict[str, float]:
    """``"a=2, b=1"`` -> ``{"a": 2.0, "b": 1.0}``; a label without ``=`` weighs 1 (empty text gives ``{}``)."""
    out: Dict[str, float] = {}
    for part in str(text or "").replace("\n", separator).split(separator):
        part = part.strip()
        if not part:
            continue
        label, _eq, raw = part.rpartition("=") if "=" in part else (part, "", "1")
        label = label.strip()
        try:
            weight = float(raw)
        except ValueError:
            raise DatingPopulationError(
                [f"{field}: {part!r} is not label=weight"]
            ) from None
        if not label or weight < 0 or weight != weight or weight == float("inf"):
            raise DatingPopulationError(
                [f"{field}: {part!r} is not label=weight with weight >= 0"]
            )
        out[label] = weight
    if out and not any(out.values()):
        raise DatingPopulationError(
            [f"{field}: at least one weight must be greater than zero"]
        )
    return out


def _number(raw: Any, field: str, kind=float, low=None, high=None):
    text = str(raw if raw is not None else "").strip()
    if text == "":
        return None
    try:
        value = kind(text)
    except ValueError:
        raise DatingPopulationError([f"{field}: must be a number"]) from None
    if (low is not None and value < low) or (high is not None and value > high):
        raise DatingPopulationError([f"{field}: must be between {low} and {high}"])
    return value


def _pair(form, field: str, kind=float, low=None, high=None):
    """The range ``[<field>_min, <field>_max]`` of a form (both empty = not given; one empty = error)."""
    lo = _number(form.get(f"{field}_min"), f"{field}_min", kind, low, high)
    hi = _number(form.get(f"{field}_max"), f"{field}_max", kind, low, high)
    if lo is None and hi is None:
        return None
    if lo is None or hi is None:
        raise DatingPopulationError([f"{field}: give both the minimum and the maximum"])
    if lo > hi:
        raise DatingPopulationError(
            [f"{field}: the minimum is greater than the maximum"]
        )
    return [lo, hi]


def _seeking(text: Any) -> Dict[str, Dict[str, float]]:
    """Lines ``gender: set=weight, set=weight`` where a set lists genders joined by ``+``."""
    out: Dict[str, Dict[str, float]] = {}
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        gender, colon, rest = line.partition(":")
        if not colon or not gender.strip():
            raise DatingPopulationError(
                [f"seeking: {line!r} is not 'gender: set=weight, ...'"]
            )
        weights = parse_weights(rest, f"seeking/{gender.strip()}")
        out[gender.strip()] = {k.replace("+", ","): v for k, v in weights.items()}
    return out


def _cities(text: Any) -> List[Dict[str, Any]]:
    """Lines ``name, latitude, longitude[, weight[, nationality]]``."""
    out = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) not in (3, 4, 5) or not parts[0]:
            raise DatingPopulationError(
                [
                    f"cities: {line.strip()!r} is not 'name, lat, lon[, weight[, nationality]]'"
                ]
            )
        try:
            city = {"name": parts[0], "lat": float(parts[1]), "lon": float(parts[2])}
            if len(parts) >= 4 and parts[3]:
                city["weight"] = float(parts[3])
            if len(parts) == 5 and parts[4]:
                city["nationality"] = parts[4]
        except ValueError:
            raise DatingPopulationError(
                [f"cities: {line.strip()!r} has a value that is not a number"]
            ) from None
        out.append(city)
    return out


def config_from_form(form) -> Dict[str, Any]:
    """The generator parameters (``schemas/population/generator.json``) described by the admin form.

    Every field that is empty is left out so that the generator's documented default applies; ``n_agents``,
    ``seed`` and ``language`` are read by the caller. Raises ``DatingPopulationError`` for a malformed value; the
    final validation against the generator schema is made by the generator itself.
    """
    cfg: Dict[str, Any] = {}
    age = {
        key: v
        for key, v in (
            ("mean", _number(form.get("age_mean"), "age_mean", float)),
            ("std", _number(form.get("age_std"), "age_std", float, 0)),
            ("min", _number(form.get("age_min"), "age_min", int, 18, 120)),
            ("max", _number(form.get("age_max"), "age_max", int, 18, 120)),
        )
        if v is not None
    }
    if age:
        cfg["age"] = age
    for field, key in WEIGHT_FIELDS:
        weights = parse_weights(form.get(field), field)
        if weights:
            cfg[key] = weights
    seeking = _seeking(form.get("seeking"))
    if seeking:
        cfg["seeking"] = seeking
    latent = {}
    for name in LATENT_VARIABLES:
        a = _number(form.get(f"latent_{name}_a"), f"latent_{name}_a", float, 0.0001)
        b = _number(form.get(f"latent_{name}_b"), f"latent_{name}_b", float, 0.0001)
        if (a is None) != (b is None):
            raise DatingPopulationError([f"latent/{name}: give both a and b"])
        if a is not None:
            latent[name] = [a, b]
    if latent:
        cfg["latent"] = latent
    affective = {}
    for trait in AFFECTIVE_TRAITS:
        pair = _pair(form, f"affective_{trait}", float, 0)
        if pair:
            affective[trait] = pair
    if affective:
        cfg["affective_traits"] = affective
    cities = _cities(form.get("cities"))
    if cities:
        cfg["cities"] = cities
    radius = _number(form.get("city_radius_km"), "city_radius_km", float, 0)
    if radius is not None:
        cfg["city_radius_km"] = radius
    for field, kind, low in (
        ("max_distance_km", float, 0),
        ("age_window", int, 0),
        ("interests_per_agent", int, 1),
        ("photos_per_agent", int, 0),
        ("daily_activity_level", int, 1),
    ):
        pair = _pair(form, field, kind, low)
        if pair:
            cfg[field] = pair
    interests = [
        i.strip()
        for i in str(form.get("interests") or "").replace("\n", ",").split(",")
        if i.strip()
    ]
    if interests:
        cfg["interests"] = list(dict.fromkeys(interests))
    personality = {}
    for trait in PERSONALITY_TRAITS:
        weights = parse_weights(
            form.get(f"personality_{trait}"), f"personality_{trait}"
        )
        if weights:
            personality[trait] = weights
    if personality:
        cfg["personality"] = personality
    appearance: Dict[str, Any] = {}
    for key in APPEARANCE_LABELS:
        weights = parse_weights(form.get(f"appearance_{key}"), f"appearance_{key}")
        if weights:
            appearance[key] = weights
    height = _pair(form, "appearance_height_cm", int, 100, 250)
    if height:
        appearance["height_cm"] = height
    glasses = _number(
        form.get("appearance_glasses"), "appearance_glasses", float, 0, 100
    )
    if glasses is not None:
        appearance["glasses"] = glasses / 100.0
    if appearance:
        cfg["appearance"] = appearance
    return cfg


def runtime_available(user=None) -> bool:
    """Whether the YDating runtime is installed (and visible to this admin): the Dating forms are offered only then."""
    try:
        from y_web.src.external_runtime import runtime_installed_and_visible

        return bool(runtime_installed_and_visible(DATING_PLATFORM, user))
    except Exception:
        return False


def population_row_values(data: Dict[str, Any]) -> Tuple[int, int, int]:
    """(size, youngest, oldest) for the ``population`` table row."""
    s = summarize(data)
    return s["size"], s["age_min"] or 0, s["age_max"] or 0


def is_dating_population(population) -> bool:
    return getattr(population, "username_type", None) == DATING_PLATFORM
