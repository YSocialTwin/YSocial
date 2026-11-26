"""Agents and the ad hoc clients that drive them."""

from ._forward import forward

decode_opinion_feature = forward(
    "y_web.src.agents.custom_features",
    "decode_opinion_feature",
    name="decode_opinion_feature",
    doc="Decode the opinion feature of an agent; same arguments as the core function.",
)
list_adhoc_clients = forward(
    "y_web.src.simulation.adhoc_client",
    "list_adhoc_clients",
    name="list_adhoc_clients",
    doc="State of the ad hoc clients of an experiment; same arguments as the core function.",
)

__all__ = ["decode_opinion_feature", "list_adhoc_clients"]
