"""Advanced server settings and recommender choice of dating experiments (plan S3, IR-D-07, IR-D-10).

Generated from ``schemas/config/server_config.json`` and ``schemas/recsys/*.json`` of YDating. Once a run has
started, the settings that shape it are locked by hash: a change would make the database depend on two
configurations, so it is refused (a run that has to change is cloned or reset instead).
"""

import copy
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from y_web.src.dating import schema_forms as sf

SCHEMA = os.path.join("config", "server_config.json")
LOCK_FILE = "run_lock.json"
COMMON_RECSYS = "common"

# keys YWeb sets itself, and why they are not on the generic form
INTERNAL: Dict[str, str] = {
    "server_name": "fixed by YWeb: names the logs and the actor",
    "namespace": "fixed by YWeb",
    "address": "the Ray cluster is local in v1",
    "port": "the Ray cluster is local in v1",
    "database.type": "SQLite only in v1",
    "database.sqlite.filename": "fixed by YWeb: the experiment database",
    "database.postgresql.host": "SQLite only in v1",
    "database.postgresql.port": "SQLite only in v1",
    "database.postgresql.database": "SQLite only in v1",
    "database.postgresql.username": "SQLite only in v1",
    "database.postgresql.password": "SQLite only in v1",
    "ray.temp_dir": "managed by YWeb",
    "matching.default_model": "the recommender section of the page",
    "matching.common": "the recommender section of the page",
    "matching.models": "the recommender section of the page",
    "annotations.sentiment": "the annotation switches of the experiment configuration",
    "annotations.toxicity": "the annotation switches of the experiment configuration",
    "annotations.emotions": "the annotation switches of the experiment configuration",
    "stress_reward.enabled": "the stress/reward switch of the experiment configuration",
    "stress_reward.system": "the stress/reward settings page",
    "platform_type": "host metadata of YSocial",
    "experiment_name": "host metadata of YSocial",
    "database_uri": "host metadata of YSocial",
    "data_path": "host metadata of YSocial",
    "is_remote": "host metadata of YSocial",
    "experiment_configuration_confirmed": "host metadata of YSocial",
    "toxicity_annotation": "host metadata of YSocial",
    "sentiment_annotation": "host metadata of YSocial",
    "emotion_annotation": "host metadata of YSocial",
    "opinion_dynamics_enabled": "host metadata of YSocial",
    "stress_reward_enabled": "host metadata of YSocial",
    "memory": "host metadata of YSocial (the Memory switch)",
}

# top-level keys that do not shape the run: they may change after it started
UNLOCKED = {
    "logging",
    "platform_type",
    "experiment_name",
    "database_uri",
    "data_path",
    "is_remote",
    "experiment_configuration_confirmed",
    "toxicity_annotation",
    "sentiment_annotation",
    "emotion_annotation",
    "opinion_dynamics_enabled",
    "stress_reward_enabled",
    "timeout_seconds",
}


class ServerSettingsError(ValueError):
    """The submitted settings are not valid or are locked (``problems`` carry the reasons)."""

    def __init__(self, problems: List[str], locked: bool = False):
        self.problems = list(problems)
        self.locked = locked
        super().__init__("; ".join(self.problems))


def schema(repo_dir: str) -> Dict[str, Any]:
    return sf.load_schema(repo_dir, SCHEMA)


def form_fields(repo_dir: str) -> List[sf.Field]:
    return sf.fields(schema(repo_dir), INTERNAL)


# ----------------------------------------------------------------------------------- recommenders
def recsys_models(repo_dir: str) -> List[str]:
    """The registered recommenders: one schema per model in ``schemas/recsys`` (``common`` is not one)."""
    folder = os.path.join(repo_dir, "schemas", "recsys")
    try:
        names = sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".json"))
    except OSError:
        return []
    return [n for n in names if n != COMMON_RECSYS]


def recsys_schema(repo_dir: str, model: str) -> Dict[str, Any]:
    return sf.load_schema(repo_dir, os.path.join("recsys", f"{model}.json"))


def recsys_fields(repo_dir: str, model: str) -> List[sf.Field]:
    return sf.fields(recsys_schema(repo_dir, model), prefix=f"matching.models.{model}.")


def common_fields(repo_dir: str) -> List[sf.Field]:
    return sf.fields(
        sf.load_schema(repo_dir, os.path.join("recsys", "common.json")),
        prefix="matching.common.",
    )


def recsys_form_text(repo_dir: str, config: Dict[str, Any]) -> Dict[str, str]:
    """Text of the recommender controls from a stored server configuration (defaults where absent)."""
    out: Dict[str, str] = {}
    matching = config.get("matching") or {}
    pairs = [
        (f, (matching.get("common") or {}), f.path[len("matching.common.") :])
        for f in common_fields(repo_dir)
    ]
    for model in recsys_models(repo_dir):
        params = (matching.get("models") or {}).get(model) or {}
        prefix = f"matching.models.{model}."
        pairs += [
            (f, params, f.path[len(prefix) :]) for f in recsys_fields(repo_dir, model)
        ]
    for f, source, key in pairs:
        out[f.path] = sf.to_form_text(sf.get_path(source, key, f.default), f)
    return out


def apply_recsys(
    repo_dir: str, config: Dict[str, Any], form: Any, label_of=lambda s: s
) -> Dict[str, Any]:
    """Set ``matching.default_model``, ``matching.common`` and ``matching.models`` from the form (mutated, returned).

    The model must be a registered one; the common parameters and the parameters of every model that was
    changed (and of the chosen one) are validated against their schemas.
    """
    problems: List[str] = []
    models = recsys_models(repo_dir)
    chosen = str(form.get("matching_default_model") or "").strip()
    matching = copy.deepcopy(config.get("matching") or {})
    if not chosen:
        chosen = matching.get("default_model") or ""
    if chosen not in models:
        raise ServerSettingsError(
            [f"matching.default_model: must be one of {', '.join(models)}"]
        )
    all_fields = common_fields(repo_dir) + [
        f for m in models for f in recsys_fields(repo_dir, m)
    ]
    try:
        values = sf.parse_form(form, all_fields, label_of)
    except sf.SettingsError as exc:
        raise ServerSettingsError(exc.problems) from None
    submitted = values.get("matching") or {}
    common_schema = sf.load_schema(repo_dir, os.path.join("recsys", "common.json"))
    common = sf.merge(matching.get("common") or {}, submitted.get("common") or {})
    problems += [
        "matching.common/" + p for p in sf.schema_problems(common_schema, common)
    ]
    kept: Dict[str, Any] = {}
    for model in models:
        sch = recsys_schema(repo_dir, model)
        current = (matching.get("models") or {}).get(model) or {}
        params = sf.merge(current, (submitted.get("models") or {}).get(model) or {})
        problems += [
            f"matching.models.{model}/" + p for p in sf.schema_problems(sch, params)
        ]
        if params and (model == chosen or params != sf.defaults(sch)):
            kept[model] = params
        elif model == chosen:
            kept[model] = params
    if problems:
        raise ServerSettingsError(problems)
    matching["default_model"] = chosen
    matching["common"] = common
    matching["models"] = kept
    config["matching"] = matching
    return config


# ---------------------------------------------------------------------------------- generic settings
def apply_form(
    repo_dir: str, config: Dict[str, Any], form: Any, label_of=lambda s: s
) -> Dict[str, Any]:
    """Apply the generic advanced settings and the recommender section; validate the result (mutated, returned)."""
    sch = schema(repo_dir)
    try:
        values = sf.parse_form(form, sf.fields(sch, INTERNAL), label_of)
    except sf.SettingsError as exc:
        raise ServerSettingsError(exc.problems) from None
    merged = sf.merge(config, values)
    apply_recsys(repo_dir, merged, form, label_of)
    problems = sf.schema_problems(sch, merged)
    if problems:
        raise ServerSettingsError(problems)
    config.clear()
    config.update(merged)
    return config


# -------------------------------------------------------------------------------------- run lock
def runtime_part(config: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a server configuration that shapes a run (host metadata and logging left out)."""
    return {k: v for k, v in config.items() if k not in UNLOCKED}


def config_hash(config: Dict[str, Any]) -> str:
    blob = json.dumps(
        runtime_part(config), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def lock_path(exp_dir: str) -> str:
    return os.path.join(exp_dir, LOCK_FILE)


def read_lock(exp_dir: str) -> Optional[Dict[str, Any]]:
    try:
        with open(lock_path(exp_dir), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_lock(exp_dir: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Record the configuration a run starts with (written by the first start, never overwritten)."""
    existing = read_lock(exp_dir)
    if existing:
        return existing
    lock = {"hash": config_hash(config), "locked_at": int(time.time())}
    tmp = lock_path(exp_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(lock, handle, indent=2)
    os.replace(tmp, lock_path(exp_dir))
    return lock


def clear_lock(exp_dir: str) -> None:
    try:
        os.remove(lock_path(exp_dir))
    except OSError:
        pass


def run_started(exp_dir: str) -> bool:
    """A run exists when the lock is written or the runtime created its database."""
    return read_lock(exp_dir) is not None or os.path.isfile(
        os.path.join(exp_dir, "database_server.db")
    )


def check_change_allowed(exp_dir: str, new_config: Dict[str, Any]) -> Tuple[bool, str]:
    """(allowed, reason). With a run started, only the settings outside the run's hash may change."""
    lock = read_lock(exp_dir)
    if lock is None:
        if os.path.isfile(os.path.join(exp_dir, "database_server.db")):
            return False, "a run has already created the database of this experiment"
        return True, ""
    if config_hash(new_config) != lock.get("hash"):
        return (
            False,
            "the experiment has started: the settings that shape the run are locked",
        )
    return True, ""
