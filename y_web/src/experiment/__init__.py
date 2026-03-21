"""
y_web.src.experiment — experiment-management package.

Re-exports every public symbol from the six domain sub-modules so that
``from y_web.src.experiment import some_function`` works for all functions.

Sub-modules
-----------
context         — database binding, setup/teardown per request
access          — visibility and permission helpers
clock           — clock configuration and timezone utilities
helpers         — experiment directory/UID helpers, SimulationClock
schema          — SQLite/PostgreSQL schema migration helpers
schedule_monitor — background thread for automatic group advancement
"""

# context
from y_web.src.experiment.context import (  # noqa: F401
    get_active_experiments,
    get_current_experiment_bind,
    get_current_experiment_id,
    get_db_bind_key_for_exp,
    initialize_active_experiment_databases,
    register_experiment_database,
    setup_experiment_context,
    teardown_experiment_context,
)

# access
from y_web.src.experiment.access import (  # noqa: F401
    get_shared_group_names,
    get_visible_experiment_query,
    user_can_manage_experiment,
    user_can_view_experiment,
)

# clock
from y_web.src.experiment.clock import (  # noqa: F401
    DEFAULT_CLOCK_FEED_REFRESH,
    DEFAULT_CLOCK_MODE,
    DEFAULT_CLOCK_TIMEZONE,
    VALID_CLOCK_MODES,
    VALID_FEED_REFRESH,
    apply_clock_to_client_simulation,
    current_local_time,
    default_clock_config,
    ensure_experiment_clock,
    parse_anchor_date,
    seconds_until_next_hour,
    validate_clock_mode,
    validate_feed_refresh,
    validate_timezone,
    wall_clock_slot,
)

# helpers
from y_web.src.experiment.helpers import (  # noqa: F401
    SimulationClock,
    active_simulation_clock,
    fetch_simulation_clock,
    get_experiment_dir,
    get_experiment_uid_from_db_name,
)

# schema
from y_web.src.experiment.schema import (  # noqa: F401
    ensure_experiment_schema_for_uri,
    ensure_postgresql_experiment_schema,
    ensure_sqlite_experiment_schema,
)

# schedule_monitor
from y_web.src.experiment.schedule_monitor import (  # noqa: F401
    POLL_INTERVAL_SECONDS,
    ExperimentScheduleMonitor,
    get_monitor,
    init_experiment_schedule_monitor,
    stop_experiment_schedule_monitor,
)
