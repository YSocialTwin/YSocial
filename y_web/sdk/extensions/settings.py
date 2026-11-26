"""The frontend settings of an experiment, as the administration pages compute them."""

from ._forward import forward

load_recsys_options = forward(
    "y_web.routes.admin.sub.experiments._frontend_settings",
    "_load_recsys_options",
    name="load_recsys_options",
    doc="The recommender systems offered for an experiment; same arguments as the core function.",
)
capabilities_for = forward(
    "y_web.routes.admin.sub.experiments._frontend_settings",
    "capabilities_for",
    name="capabilities_for",
    doc="The frontend capabilities a platform offers; same arguments as the core function.",
)
excluded_capabilities_for = forward(
    "y_web.routes.admin.sub.experiments._frontend_settings",
    "excluded_capabilities_for",
    name="excluded_capabilities_for",
    doc="The frontend capabilities a platform leaves out; same arguments as the core function.",
)

__all__ = ["capabilities_for", "excluded_capabilities_for", "load_recsys_options"]
