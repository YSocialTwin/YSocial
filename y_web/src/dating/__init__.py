"""YDating (Tinder-like dating Twin) integration in YSocial.

A dating experiment runs on the HPC/Ray path with its own database. YWeb must never apply the YSocial
experiment schema to it: ``rounds`` and ``user_mgmt`` exist in both with different columns (plan, IR-D-04).
"""

DATING_PLATFORM = "dating"
# table YDating creates in every run database and YSocial does not have; its presence identifies a dating database
DATING_MARKER_TABLE = "dating_profile"


def is_dating_platform(platform_type) -> bool:
    return platform_type == DATING_PLATFORM


def is_dating_experiment(experiment) -> bool:
    return is_dating_platform(getattr(experiment, "platform_type", None))
