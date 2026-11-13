"""Federation features a platform takes part in: the outbox of humans, new populations and account confirmation."""

from __future__ import annotations

from y_web.src.federation import human_outbox  # noqa: F401


def confirm_account(fed, user_id, member) -> "bool":
    """A pending account now exists: the person joined. True when the record changed."""
    from y_web.src.federation.humans import confirm_account as target

    return target(fed, user_id, member)


def population_added(exp_id, population_id) -> "list":
    """Call after a population was attached to an experiment. Returns ``[(federation id, [usernames declared])]``."""
    from y_web.src.federation.dynamic import population_added as target

    return target(exp_id, population_id)


__all__ = [
    "confirm_account",
    "human_outbox",
    "population_added",
]
