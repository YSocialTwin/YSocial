"""The agent-side features every platform shares: the standard population code, the Appearance section, pictures."""

from __future__ import annotations

from y_web.src.agents import appearance_form, population, profile_pictures  # noqa: F401


def delete_pictures_of(agent_ids: "Iterable[int]") -> "int":
    """Delete the pictures of agents that are removed with a bulk statement (the ORM listener does not see those)."""
    from y_web.src.agents.profile_pictures import delete_pictures_of as target

    return target(agent_ids)


__all__ = [
    "appearance_form",
    "delete_pictures_of",
    "population",
    "profile_pictures",
]
