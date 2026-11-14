"""Helpers for population platform typing and compatibility."""

from sqlalchemy import inspect, select, text

from y_web import db
from y_web.platforms import registry
from y_web.src.models import Exps, Population_Experiment


class _PopulationTypes:
    """The platform types a population can be tagged with: the keys of the installed platforms."""

    def __contains__(self, value):
        return value in registry.keys()

    def __iter__(self):
        return iter(registry.keys())

    def __len__(self):
        return len(registry.keys())


VALID_POPULATION_TYPES = _PopulationTypes()


def normalize_population_username_type(raw_value, default=None):
    """Normalize user-provided population platform values."""
    value = (raw_value or "").strip().lower()
    if value in VALID_POPULATION_TYPES:
        return value
    return registry.default_key() if default is None else default


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

    default = registry.default_key()
    ddl = (
        "ALTER TABLE population "
        f"ADD COLUMN username_type VARCHAR(50) DEFAULT '{default}'"
    )
    with engine.begin() as connection:
        connection.execute(text(ddl))
        connection.execute(
            text(
                "UPDATE population "
                "SET username_type = :default "
                "WHERE username_type IS NULL OR TRIM(username_type) = ''"
            ),
            {"default": default},
        )


def infer_population_username_type(population):
    """Infer a population platform type when explicit metadata is missing."""
    explicit = normalize_population_username_type(
        getattr(population, "username_type", None), default=""
    )
    if explicit in VALID_POPULATION_TYPES:
        return explicit

    associations = db.session.scalars(
        select(Population_Experiment).filter_by(id_population=population.id)
    ).all()
    if not associations:
        return None

    experiment_ids = [assoc.id_exp for assoc in associations]
    experiment_types = {
        normalize_population_username_type(exp.platform_type, default="")
        for exp in db.session.scalars(
            select(Exps).filter(Exps.idexp.in_(experiment_ids))
        ).all()
    }
    experiment_types.discard("")
    if len(experiment_types) == 1:
        return next(iter(experiment_types))

    return None


def population_matches_platform(population, platform_type):
    """Whether a population can be used with the requested platform: always.

    A population is not tied to a platform. The fields that only one platform reads (of some platforms) are
    custom fields of its agents: generated with the population when the person asked for them, completed with the
    generator defaults when the population is first deployed on a platform that needs them
    (``population_platform_fields`` tells which it has).
    """
    return True


def population_platform_fields(population):
    """The platforms whose dedicated custom fields the agents of ``population`` carry, as a sorted list."""
    found = set()
    explicit = normalize_population_username_type(
        getattr(population, "username_type", None), default=""
    )
    explicit_provider = registry.get(explicit) if explicit else None
    if explicit_provider is not None and explicit_provider.has_population_fields:
        found.add(explicit)
    try:
        for provider in registry.providers():
            if provider.carries_population_fields(population):
                found.add(provider.key)
    except Exception:
        pass
    return sorted(found)
