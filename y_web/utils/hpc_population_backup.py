"""
Backward-compatibility shim for y_web.utils.hpc_population_backup.

The canonical location is now y_web.src.hpc.population_backup.
All existing ``from y_web.utils.hpc_population_backup import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.hpc.population_backup instead.
"""
import warnings

warnings.warn(
    "y_web.utils.hpc_population_backup is deprecated; use y_web.src.hpc.population_backup instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.hpc.population_backup import *  # noqa: F401,F403
from y_web.src.hpc.population_backup import (  # noqa: F401
    _backup_file_path,
    _experiment_dir,
    _experiment_uid,
    _population_json_candidates,
)
