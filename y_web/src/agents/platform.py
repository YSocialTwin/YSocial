"""Helpers for population platform typing and compatibility."""

from sqlalchemy import inspect, text

from y_web import db
from y_web.src.models import Exps, Population_Experiment

VALID_POPULATION_TYPES = {"microblogging", "forum", "photo_sharing"}


def normalize_population_username_type(raw_value, default="microblogging"):
    """Normalize user-provided population platform values."""
    value = (raw_value or "").strip().lower()
    if value in VALID_POPULATION_TYPES:
        return value
    return default


def ensure_population_username_type_column():
    """Ensure the admin population table has the username_type column."""
    try:
        engine = db.engines["db_admin"]
    except Exception:
        engine = db.get_engine(bind="db_admin")
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("population")}
    if "username_type" in columns:
        return

    ddl = (
        "ALTER TABLE population "
        "ADD COLUMN username_type VARCHAR(50) DEFAULT 'microblogging'"
    )
    with engine.begin() as connection:
        connection.execute(text(ddl))
        connection.execute(
            text(
                "UPDATE population "
                "SET username_type = 'microblogging' "
                "WHERE username_type IS NULL OR TRIM(username_type) = ''"
            )
        )


def infer_population_username_type(population):
    """Infer a population platform type when explicit metadata is missing."""
    explicit = normalize_population_username_type(
        getattr(population, "username_type", None), default=""
    )
    if explicit in VALID_POPULATION_TYPES:
        return explicit

    associations = Population_Experiment.query.filter_by(
        id_population=population.id
    ).all()
    if not associations:
        return None

    experiment_ids = [assoc.id_exp for assoc in associations]
    experiment_types = {
        normalize_population_username_type(exp.platform_type, default="")
        for exp in Exps.query.filter(Exps.idexp.in_(experiment_ids)).all()
    }
    experiment_types.discard("")
    if len(experiment_types) == 1:
        return next(iter(experiment_types))

    return None


def population_matches_platform(population, platform_type):
    """Return whether a population can be used with the requested platform."""
    inferred = infer_population_username_type(population)
    return inferred in {None, normalize_population_username_type(platform_type)}
