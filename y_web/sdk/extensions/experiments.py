"""Experiments: their database, their folder, their lifecycle."""

from y_web.sdk.social import (
    ensure_experiment_user,
    experiment_db_bind,
    get_experiment_engine_uri,
    open_experiment_session,
)

from ._forward import forward

get_current_experiment_id = forward(
    "y_web.src.experiment.context",
    "get_current_experiment_id",
    name="get_current_experiment_id",
    doc="Id of the experiment the current request works on; same arguments as the core function.",
)
copy_experiment = forward(
    "y_web.routes.admin.sub.experiments._crud",
    "_create_single_experiment_copy",
    name="copy_experiment",
    doc="Create a copy of an experiment; same arguments as the core function.",
)
create_experiment = forward(
    "y_web.routes.admin.sub.experiments._crud",
    "create_experiment",
    name="create_experiment",
    doc="Create an experiment from the administration form; same arguments as the core function.",
)
delete_simulation = forward(
    "y_web.routes.admin.sub.experiments._crud",
    "_delete_simulation_internal",
    name="delete_simulation",
    doc="Delete an experiment and its files; same arguments as the core function.",
)
build_experiment_zip = forward(
    "y_web.routes.admin.sub.experiments._notifications",
    "_build_single_experiment_zip",
    name="build_experiment_zip",
    doc="Build the zip archive of an experiment; same arguments as the core function.",
)
migrate_moderation_schema = forward(
    "y_web.migrations.add_moderation_schema",
    "migrate_sqlite_server",
    name="migrate_moderation_schema",
    doc="Add the moderation tables to the SQLite database of an experiment; same arguments as the core function.",
)

__all__ = [
    "build_experiment_zip",
    "copy_experiment",
    "create_experiment",
    "delete_simulation",
    "ensure_experiment_user",
    "experiment_db_bind",
    "get_current_experiment_id",
    "get_experiment_engine_uri",
    "migrate_moderation_schema",
    "open_experiment_session",
]
