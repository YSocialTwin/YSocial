"""The agent-side features every platform shares: the standard population code, the Appearance section, pictures."""

from __future__ import annotations

from y_web.src.agents import appearance_form, population, profile_pictures  # noqa: F401


def delete_pictures_of(agent_ids: "Iterable[int]") -> "int":
    """Delete the pictures of agents that are removed with a bulk statement (the ORM listener does not see those)."""
    from y_web.src.agents.profile_pictures import delete_pictures_of as target

    return target(agent_ids)


def picture_of_username(username: "Any") -> "str":
    """Url of the generated picture of the agent called ``username`` ('' when it has none)."""
    from y_web.src.agents.profile_pictures import picture_of_username as target

    return target(username)


def random_cover_image_url() -> str:
    from y_web.src.content.cover_images import random_cover_image_url as target

    return target()


def summarize_agent_custom_features_bulk(
    agent_ids: "Iterable[int]",
) -> "dict[int, dict]":
    from y_web.src.agents.custom_features import (
        summarize_agent_custom_features_bulk as target,
    )

    return target(agent_ids)


__all__ = [
    "appearance_form",
    "delete_pictures_of",
    "picture_of_username",
    "population",
    "profile_pictures",
    "random_cover_image_url",
    "summarize_agent_custom_features_bulk",
]
