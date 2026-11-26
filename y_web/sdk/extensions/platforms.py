"""The platforms the application knows (the registry) and their two variants."""

from y_web.platforms import registry
from y_web.sdk import HPC, STANDARD
from y_web.sdk.social import content_recsys_info

__all__ = ["HPC", "STANDARD", "content_recsys_info", "registry"]
