"""YInstantMessaging (IM) integration helpers.

IM runs on the HPC/Ray path with its own database (``run_info`` marks it). YWeb must never apply the
YSocial experiment schema to an IM database (plan, DEC-04).
"""

IM_PLATFORM = "instant_messaging"
# table IM creates in every run database; its presence identifies an IM database
IM_MARKER_TABLE = "run_info"


def is_im_platform(platform_type) -> bool:
    return platform_type == IM_PLATFORM


def is_im_experiment(experiment) -> bool:
    return is_im_platform(getattr(experiment, "platform_type", None))
