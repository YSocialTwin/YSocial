"""Names of the platforms in the frontends of a World Simulation.

A person looking at a platform page sees *which experiment* a cross-post comes from or goes to (``Exps.exp_name``, e.g. "XW",
"FW"), never the platform type ("microblogging", "forum"): the type stays only as the icon. Several experiments of the same
type can belong to one World Simulation, so everything is keyed by the member (its name in the World Simulation), and the
name of its experiment is the label. Read-only; every error means "no names" and the caller falls back to the member name."""

from __future__ import annotations

from typing import Dict, Optional

from y_web import db


def names_of(federation_pk) -> Dict[str, str]:
    """``{member: experiment name}`` of the members of one World Simulation (one query)."""
    from y_web.src.models.admin import Exps, FederationMember

    rows = (db.session.query(FederationMember.member, Exps.exp_name)
            .join(Exps, Exps.idexp == FederationMember.exp_id).filter(FederationMember.federation_pk == federation_pk).all())
    return {m: n for m, n in rows if n}


def world_names(exp_id) -> Dict[str, str]:
    """``{member: experiment name}`` of the World Simulation that experiment ``exp_id`` belongs to; ``{}`` outside one.

    Computed once per request. A page never fails because of this."""
    try:
        from flask import g, has_request_context

        if exp_id in (None, ""):
            return {}
        cache = g.setdefault("_ws_names", {}) if has_request_context() else None
        key = int(exp_id)
        if cache is not None and key in cache:
            return cache[key]
        from y_web.src.models.admin import FederationMember

        own = db.session.query(FederationMember).filter_by(exp_id=key).first()
        value = names_of(own.federation_pk) if own is not None else {}
        if cache is not None:
            cache[key] = value
        return value
    except Exception:  # noqa: BLE001
        return {}


def label_of(names: Optional[Dict[str, str]], member) -> str:
    """The experiment name of ``member`` (the member's own name, prettified, when it is not known)."""
    member = str(member or "")
    return (names or {}).get(member) or member.replace("_", " ").capitalize()
