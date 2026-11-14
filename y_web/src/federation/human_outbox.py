"""Cross-posts of the people enrolled in a World Simulation (F8, H5): destinations, text and delivery.

A person who publishes on one platform may also post on the other platforms where they are enrolled (D2). The words are
the person's own, shaped for each destination with a plain rule, never a model (D5): ``rule_text``, the same rule the
agents' clients use without an LLM (``YClient/y_client/federation.py``, limits included; YWeb does not import the
runtimes). The request goes to the runtime through its gateway (``crosspost_to`` of the action, the same field an agent
sends), so the runtime marks the post for export and the coordinator forwards it only where the person has an account.
Nothing here runs for a person who is not enrolled: every other action keeps its direct path (NFR-01).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests

from y_web import db
from y_web.src.federation import service, traits
from y_web.src.federation.humans import members_state

MAX_TARGETS = 8


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    return (cut.rsplit(" ", 1)[0] if " " in cut[-30:] else cut).rstrip(",;:- ")


def rule_text(dest_platform: str, text) -> str:
    """The person's words for the destination: the same words, shaped and cut for the platform (some get a title line)."""
    titled = traits.title_line(dest_platform)
    text = str(text or "").strip() if titled else " ".join(str(text or "").split())
    if titled and "\n" not in text:
        title = _cut(re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0], 80)
        return f"{title}\n{text}"[: traits.text_limit(dest_platform)]
    return _cut(text, traits.text_limit(dest_platform))


@dataclass
class HumanContext:
    """Where a person is enrolled, seen from one member experiment."""

    federation: object
    member: str
    platform_type: str
    human_id: str
    user_id: int
    account_id: str
    accounts: Dict[str, str] = field(
        default_factory=dict
    )  # every enrolled member -> local account id
    destinations: Dict[str, str] = field(
        default_factory=dict
    )  # the OTHER enrolled members -> platform type


def context_for(exp_id, user_id) -> Optional[HumanContext]:
    """The enrolment of ``user_id`` (``Admin_users.id``) seen from experiment ``exp_id``; ``None`` when the experiment is
    not a member of a World Simulation, the person is not enrolled on it, or the account does not exist yet.
    """
    from y_web.src.models.admin import Federation, FederationHuman, FederationMember

    if user_id is None:
        return None
    row = db.session.query(FederationMember).filter_by(exp_id=int(exp_id)).first()
    if row is None:
        return None
    fed = db.session.get(Federation, row.federation_pk)
    human = (
        db.session.query(FederationHuman)
        .filter_by(
            federation_pk=row.federation_pk, user_id=int(user_id), status="active"
        )
        .first()
        if fed is not None
        else None
    )
    if human is None:
        return None
    state = members_state(human)
    own = state.get(row.member)
    if not own or not own.get("created", True):
        return None
    platforms = {
        m.member: m.platform_type
        for m in db.session.query(FederationMember).filter_by(
            federation_pk=row.federation_pk
        )
    }
    destinations = {
        m: platforms[m]
        for m, info in sorted(state.items())
        if m != row.member and m in platforms and info.get("created", True)
    }
    return HumanContext(
        fed,
        row.member,
        row.platform_type,
        human.human_id,
        int(user_id),
        str(own["account_id"]),
        {m: str(i["account_id"]) for m, i in state.items()},
        destinations,
    )


def destinations_for(exp_id, user_id) -> List[dict]:
    """``[{member, platform_type, label}]`` the composer offers (empty for a person who is not enrolled); ``label`` is the name
    of the experiment of the member (the platform type is only its icon)."""
    from y_web.src.federation.names import label_of, names_of

    ctx = context_for(exp_id, user_id)
    names = names_of(ctx.federation.id) if ctx else {}
    return [
        {"member": m, "platform_type": p, "label": label_of(names, m)}
        for m, p in (ctx.destinations.items() if ctx else [])
    ]


def request_overrides() -> Dict[str, str]:
    """The texts the person edited per destination (``crosspost_texts``: ``{member: text}``, a JSON object or its string), read
    from the current request (query, form or JSON body); ``{}`` outside a request or when the field is absent or malformed.
    Only text is taken from here: which members receive the post is always decided by ``crosspost_to`` below.
    """
    try:
        from flask import has_request_context, request

        if not has_request_context():
            return {}
        raw = request.values.get("crosspost_texts")
        if raw is None:
            body = request.get_json(silent=True)
            raw = body.get("crosspost_texts") if isinstance(body, dict) else None
        if isinstance(raw, (str, bytes)):
            raw = json.loads(raw)
        return (
            {str(k): v for k, v in raw.items() if isinstance(v, str)}
            if isinstance(raw, dict)
            else {}
        )
    except (
        Exception
    ):  # noqa: BLE001 - a malformed field means "no edits": the rule text
        return {}


def edited_text(dest_platform: str, text) -> str:
    """The person's edited text for a destination, cut to the platform limit; an empty text is ``""`` (rule text applies)."""
    text = str(text or "").strip()
    if not text:
        return ""
    if traits.title_line(dest_platform):
        return rule_text(
            dest_platform, text
        )  # a title line is added when the person wrote a single line
    return _cut(" ".join(text.split()), traits.text_limit(dest_platform))


def suggested_texts(ctx: HumanContext, text, members=None) -> Dict[str, str]:
    """``{member: rule_text}`` for the enrolled destinations (all, or the ``members`` given): what the composer prefills."""
    wanted = [
        m
        for m in (members if members is not None else ctx.destinations)
        if m in ctx.destinations
    ]
    return {m: rule_text(ctx.destinations[m], text) for m in sorted(set(wanted))}


def suggestions_for(exp_id, user_id, text, members=None) -> dict:
    """``{member: {text, limit}}`` the composer prefills (empty when the person is not enrolled): the rule text and the limit
    of each destination, single-sourced here so the page never repeats the rule."""
    ctx = context_for(exp_id, user_id)
    if ctx is None:
        return {}
    return {
        m: {"text": t, "limit": traits.text_limit(ctx.destinations[m])}
        for m, t in suggested_texts(ctx, text, members).items()
    }


def crosspost_to(
    ctx: HumanContext, requested, text, overrides: Optional[Dict[str, str]] = None
) -> List[dict]:
    """``[{member, text}]``: the requested members that are enrolled destinations, in a stable order, each with its text.

    The text is the rule text unless the person edited it for that destination (``overrides``, by default the
    ``crosspost_texts`` of the request): an edited text is cut to the limit of the destination platform, an empty one falls
    back to the rule text, and an edit for a member that is not an enrolled, requested destination is ignored.
    """
    wanted = sorted({str(m) for m in requested or [] if str(m) in ctx.destinations})[
        :MAX_TARGETS
    ]
    edits = request_overrides() if overrides is None else overrides
    out = []
    for m in wanted:
        platform = ctx.destinations[m]
        out.append(
            {
                "member": m,
                "text": edited_text(platform, edits.get(m))
                or rule_text(platform, text),
            }
        )
    return out


def requested_members(values) -> List[str]:
    """The ``crosspost`` values of a request (repeated parameter, or one comma separated string)."""
    out: List[str] = []
    for v in values or []:
        out += [p.strip() for p in str(v).split(",") if p.strip()]
    return out


# -- delivery -------------------------------------------------------------------------------------------
def _runtime_gateway(exp, platform_type, session=None, offline=None):
    from y_web.src.federation.human_gateways import RuntimeGateway, is_hpc

    folder = service.experiment_dir(exp)
    return RuntimeGateway(
        platform_type,
        folder,
        server_config=service.server_config_path(exp),
        database=folder / "database_server.db",
        session=session,
        offline=offline,
        hpc=is_hpc(exp),
    )


def _ok(status, payload) -> bool:
    return status in (200, 201) and (payload or {}).get("ok", True) is not False


def publish_through_gateway(
    exp, ctx: HumanContext, action: dict, *, username: str, session=None, offline=None
):
    """One action of the person on a platform through the gateway of its runtime."""
    spec = traits.human_gateway(ctx.platform_type, getattr(exp, "simulator_type", None))
    key = (spec.key_template if spec else "u{user_id}").format(user_id=ctx.user_id)
    gateway = _runtime_gateway(exp, ctx.platform_type, session, offline)
    status, payload = gateway.actions(ctx.account_id, username, key, [action])
    return _ok(status, payload), status, payload


def build_action(exp, platform_type, text, targets, *, post_id=None, community=None):
    """The action of a post (or share of ``post_id``) of the person with ``crosspost_to`` ``targets``, as the gateway of
    the platform takes it; ``None`` when the platform takes no action from the composer.
    """
    spec = traits.human_gateway(platform_type, getattr(exp, "simulator_type", None))
    if spec is None or spec.build_action is None:
        return None
    return spec.build_action(text, targets, post_id=post_id, community=community)


def community_of(exp, platform_type, slug, session=None) -> Optional[str]:
    """The community the person chose in the composer, as the platform's server names it, or ``None``."""
    spec = traits.human_gateway(platform_type, getattr(exp, "simulator_type", None))
    if spec is None or spec.community_of is None:
        return None
    return spec.community_of(exp, slug, session)


def try_deliver(
    exp_id, user, requested, text, build, *, only=None, session=None, offline=None
):
    """Publish through the gateway when the person is enrolled and picked at least one enrolled destination.

    ``build(targets)`` makes the action of the platform. Returns ``None`` when the normal path applies (not enrolled, or
    nothing picked: the route does what it always did), ``True`` when the gateway accepted the action and ``False`` when it
    did not (the route must not write the post a second time)."""
    ctx = context_for(exp_id, getattr(user, "id", None))
    if ctx is None or not requested or (only and ctx.platform_type != only):
        return None
    targets = crosspost_to(ctx, requested, text)
    if not targets:
        return None
    from y_web.src.models import Exps

    exp = db.session.get(Exps, int(exp_id))
    try:
        ok, _status, _payload = publish_through_gateway(
            exp,
            ctx,
            build(targets),
            username=str(user.username),
            session=session,
            offline=offline,
        )
    except (
        Exception
    ):  # noqa: BLE001 - a gateway that cannot be reached is a refusal, never a second write
        return False
    return ok


def targets_for_request(exp_id, user, requested, text) -> list:
    """``crosspost_to`` of an action sent through an existing gateway client of a platform; ``[]`` when the
    person is not enrolled or picked nothing. A client-sent ``crosspost_to`` is never trusted: only this is.
    """
    ctx = context_for(exp_id, getattr(user, "id", None))
    return crosspost_to(ctx, requested, text) if ctx is not None and requested else []


def enrolment_of(exp_id, user_id):
    """``(federation, member, human)`` when the person is enrolled (active) on this member, created or still pending
    (a platform whose account exists only after the person joined); ``None`` otherwise.
    """
    from y_web.src.models.admin import Federation, FederationHuman, FederationMember

    if user_id is None:
        return None
    row = db.session.query(FederationMember).filter_by(exp_id=int(exp_id)).first()
    if row is None:
        return None
    human = (
        db.session.query(FederationHuman)
        .filter_by(
            federation_pk=row.federation_pk, user_id=int(user_id), status="active"
        )
        .first()
    )
    if human is None or row.member not in members_state(human):
        return None
    return db.session.get(Federation, row.federation_pk), row.member, human
