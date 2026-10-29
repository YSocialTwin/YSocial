"""Dating populations: validation, storage and summary (plan S2, IR-D-05).

A dating population is not made of YSocial ``Agent`` rows (a profile has a location, the genders sought,
photos and latent variables that YSocial's agent table does not have). It is a JSON document that satisfies
the population schema of YDating, stored in a file; the ``population`` table of the admin database keeps one
row for it (name, description, size, ``username_type`` ``dating``) so that populations are listed, assigned
to experiments and deleted like the others. The module has no Flask and no database access except where a
function says so.
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


def population_dir(base_dir: str) -> str:
    """Folder of the stored dating populations inside the writable area."""
    return os.path.join(base_dir, "y_web", "dating_populations")


def population_path(base_dir: str, population_id: int) -> str:
    return os.path.join(population_dir(base_dir), f"{int(population_id)}.json")


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
    return name[:50]


def store(base_dir: str, population_id: int, data: Dict[str, Any]) -> str:
    os.makedirs(population_dir(base_dir), exist_ok=True)
    path = population_path(base_dir, population_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp, path)
    return path


def load(base_dir: str, population_id: int) -> Optional[Dict[str, Any]]:
    try:
        with open(population_path(base_dir, population_id), "r", encoding="utf-8") as h:
            return json.load(h)
    except (OSError, ValueError):
        return None


def remove(base_dir: str, population_id: int) -> None:
    try:
        os.remove(population_path(base_dir, population_id))
    except OSError:
        pass


def generate(
    n_agents: int,
    seed: Optional[int] = None,
    language: Optional[str] = None,
    repo_dir: Optional[str] = None,
    tmp_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a synthetic population with the generator of YDating (``scripts/generate_population.py``).

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
        cfg_path = None
        if language:
            cfg_path = os.path.join(work, "generator.json")
            with open(cfg_path, "w", encoding="utf-8") as handle:
                json.dump({"language": str(language)}, handle)
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


def population_row_values(data: Dict[str, Any]) -> Tuple[int, int, int]:
    """(size, youngest, oldest) for the ``population`` table row."""
    s = summarize(data)
    return s["size"], s["age_min"] or 0, s["age_max"] or 0


def is_dating_population(population) -> bool:
    return getattr(population, "username_type", None) == DATING_PLATFORM
