"""Populations that join a World Simulation after it was created or while it runs (INV-18).

When a population is attached to an experiment that is a member of a World Simulation (a new client, a client with a different
population), its agents become identities of that member: a link per agent (by username, INV-17) and, when the coordinator
is running, a ``POST /v1/expected`` so that they are active as soon as their accounts are bound, with every action intact.
An agent of that population who is already in the World Simulation through another member keeps its global id (the Agent id):
it simply gains an account here. The coordinator also makes the new agents discoverable on the provisionable members (INV-19).

Everything here is best effort and never raises: adding a client must work whatever the state of the federation.
"""

from __future__ import annotations

import logging

from y_web import db
from y_web.src.federation import service

log = logging.getLogger(__name__)

RUNNING = ("starting", "running", "paused")


def _federations_of(exp_id) -> list:
    from y_web.src.models.admin import Federation, FederationMember

    return (
        db.session.query(Federation, FederationMember)
        .join(FederationMember, FederationMember.federation_pk == Federation.id)
        .filter(FederationMember.exp_id == int(exp_id))
        .all()
    )


def _coordinator_client(fed, member):
    from pathlib import Path

    from ysocial_federation.client import CoordinatorClient

    folder = Path(fed.folder)
    return CoordinatorClient.from_files(
        folder / "federation_coordinator.json",
        folder / "federation.token",
        member,
        retry_budget=1.0,
    )


def population_added(exp_id, population_id) -> list:
    """Call after a population was attached to an experiment. Returns ``[(federation id, [usernames declared])]``."""
    from y_web.src.models.admin import FederationIdentityLink

    done = []
    try:
        pairs = _federations_of(exp_id)
        if not pairs:
            return done
        agents = service._population_agents([int(population_id)])
        for fed, row in pairs:
            known = {
                l.global_agent_id
                for l in db.session.query(FederationIdentityLink)
                .filter_by(federation_pk=fed.id, member=row.member)
                .all()
            }
            fresh = [a for a in agents if str(a.id) not in known]
            if not fresh:
                continue
            service._check_usernames(
                _exp_for_message(row), _same_member_agents(fed, row) + fresh
            )
            for agent in fresh:
                db.session.add(
                    FederationIdentityLink(
                        federation_pk=fed.id,
                        global_agent_id=str(agent.id),
                        member=row.member,
                        local_account_id="",
                        username=service.username_of(agent),
                    )
                )
            db.session.flush()
            if (
                fed.status in RUNNING
            ):  # declared before the links are kept: if the coordinator cannot be reached nothing is recorded
                identities = [
                    {
                        "global_agent_id": str(a.id),
                        "username": service.username_of(a),
                        "name": service.username_of(a),
                    }
                    for a in fresh
                ]
                _coordinator_client(fed, row.member).declare_expected(identities)
            db.session.commit()
            service.write_federation_files(
                fed
            )  # federation.json stays the truth for a restart
            db.session.commit()
            done.append((fed.id, [service.username_of(a) for a in fresh]))
    except Exception as exc:  # noqa: BLE001 - never break the creation of a client
        db.session.rollback()
        log.warning(
            "federation: population %s of experiment %s not declared: %s",
            population_id,
            exp_id,
            exc,
        )
    return done


def _exp_for_message(row):
    from y_web.src.models.admin import Exps

    return db.session.get(Exps, row.exp_id)


def _same_member_agents(fed, row) -> list:
    from y_web.src.models.admin import Agent, FederationIdentityLink

    ids = [
        int(l.global_agent_id)
        for l in db.session.query(FederationIdentityLink)
        .filter_by(federation_pk=fed.id, member=row.member)
        .all()
        if l.global_agent_id.isdigit()
    ]
    return db.session.query(Agent).filter(Agent.id.in_(ids)).all() if ids else []
