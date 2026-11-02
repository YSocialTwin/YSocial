"""Federation hooks of the YWeb client loop (World Simulation).

YWeb does not run `YClient.run_simulation`: `process_runner.run_simulation` and `agent_sampler.process_agent` drive the
slots of the microblogging and forum clients. The federation hooks that `run_simulation` of the client packages applies
(adopt_provisioned, filter_pool, scale_actions) are applied here, with the same functions of `y_client.federation`.

Everything is a no-op, with no request and no random draw, when the client package has no `y_client.federation`, when
the federation is not enabled in this process (`federation.install` was not called or the section is off), or when a
hook fails: the lists and numbers returned are then the ones received. The client module is imported when needed, never
the SDK."""

import sys

DEFAULT_ACTIVITY_PROFILE = "Always On"


def federation_module():
    """`y_client.federation` of the client package in use when the federation is on in this process, else None."""
    try:
        from y_client import federation
    except Exception:  # noqa: BLE001 - this client package has no federation
        return None
    try:
        return federation if federation.enabled() else None
    except Exception:  # noqa: BLE001
        return None


def _warn(what, exc):
    print(f"Warning: federation {what} failed: {exc}", file=sys.stderr)


def adopt_provisioned(cl):
    """Adopt the accounts the federation created for new agents (INV-19); returns the agents added to `cl.agents`.

    The module only does something with `federation.adopt` in the client configuration. The adopted agents get the
    attributes the sampler needs when the client did not set them."""
    fed = federation_module()
    if fed is None or not hasattr(cl, "adopt_federated_account"):
        return []
    before = {id(a) for a in cl.agents.agents}
    try:
        fed.adopt_provisioned(cl)
    except Exception as exc:  # noqa: BLE001 - offered again at the next slot
        _warn("adoption", exc)
    added = [a for a in cl.agents.agents if id(a) not in before]
    for a in added:
        if getattr(a, "activity_profile", None) is None:
            a.activity_profile = DEFAULT_ACTIVITY_PROFILE
        if getattr(a, "daily_activity_level", None) is None:
            a.daily_activity_level = 1
    return added


def filter_pool(agents):
    """The agents that may act in this slot: the same list object unless the federation hides accounts
    (not active or inactive members). Also reads the attention multipliers of the day."""
    fed = federation_module()
    if fed is None:
        return agents
    try:
        return fed.filter_pool(agents)
    except Exception as exc:  # noqa: BLE001
        _warn("pool filter", exc)
        return agents


def scaled_round_actions(agent, n):
    """`n` actions of the agent in the slot after the attention multiplier of the federation (F4.3); `n` itself without it."""
    fed = federation_module()
    if fed is None:
        return n
    try:
        return int(fed.scale_actions(n, getattr(agent, "user_id", None)))
    except Exception as exc:  # noqa: BLE001
        _warn("attention", exc)
        return n


def prepare_slot(cl, common_agents, hour_to_users, hour, rebuild):
    """Slot preparation of the loop: adopt the new accounts, then hide the agents that must not act.

    `rebuild(agents)` rebuilds the hour -> agents map when somebody was adopted. Returns
    `(common_agents, hour_to_users, pool)` where `pool` is what the sampler draws from; without the federation
    the inputs come back unchanged and `pool is hour_to_users[hour]`."""
    if adopt_provisioned(cl):
        common_agents = [p for p in cl.agents.agents if not getattr(p, "is_page", 0)]
        hour_to_users = rebuild(common_agents)
    return common_agents, hour_to_users, filter_pool(hour_to_users[hour])
