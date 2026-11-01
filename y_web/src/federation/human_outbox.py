"""Cross-posts of the people enrolled in a World Simulation (F8, H5): destinations, text and delivery.

A person who publishes on one platform may also post on the other platforms where they are enrolled (D2). The words are
the person's own, shaped for each destination with a plain rule, never a model (D5): ``rule_text``, the same rule the
agents' clients use without an LLM (``YClient/y_client/federation.py``, limits included; YWeb does not import the
runtimes). The request goes to the runtime through its gateway (``crosspost_to`` of the action, the same field an agent
sends), so the runtime marks the post for export and the coordinator forwards it only where the person has an account.
Nothing here runs for a person who is not enrolled: every other action keeps its direct path (NFR-01).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from y_web import db
from y_web.src.federation import service
from y_web.src.federation.humans import members_state

# Longest text each destination accepts (characters); keep in step with YClient/y_client/federation.py
LIMITS = {"microblogging": 280, "forum": 2000, "photo_sharing": 300, "instant_messaging": 400, "dating": 200}
MAX_TARGETS = 8


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    return (cut.rsplit(" ", 1)[0] if " " in cut[-30:] else cut).rstrip(",;:- ")


def rule_text(dest_platform: str, text) -> str:
    """The person's words for the destination: the same words, shaped and cut for the platform (a forum gets a title)."""
    text = " ".join(str(text or "").split()) if dest_platform != "forum" else str(text or "").strip()
    if dest_platform == "forum" and "\n" not in text:
        title = _cut(re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0], 80)
        return f"{title}\n{text}"[: LIMITS["forum"]]
    return _cut(text, LIMITS.get(dest_platform, 280))


@dataclass
class HumanContext:
    """Where a person is enrolled, seen from one member experiment."""

    federation: object
    member: str
    platform_type: str
    human_id: str
    user_id: int
    account_id: str
    accounts: Dict[str, str] = field(default_factory=dict)  # every enrolled member -> local account id
    destinations: Dict[str, str] = field(default_factory=dict)  # the OTHER enrolled members -> platform type


def context_for(exp_id, user_id) -> Optional[HumanContext]:
    """The enrolment of ``user_id`` (``Admin_users.id``) seen from experiment ``exp_id``; ``None`` when the experiment is
    not a member of a World Simulation, the person is not enrolled on it, or the account does not exist yet."""
    from y_web.src.models.admin import Federation, FederationHuman, FederationMember

    if user_id is None:
        return None
    row = db.session.query(FederationMember).filter_by(exp_id=int(exp_id)).first()
    if row is None:
        return None
    fed = db.session.get(Federation, row.federation_pk)
    human = (
        db.session.query(FederationHuman).filter_by(federation_pk=row.federation_pk, user_id=int(user_id), status="active").first()
        if fed is not None
        else None
    )
    if human is None:
        return None
    state = members_state(human)
    own = state.get(row.member)
    if not own or not own.get("created", True):
        return None
    platforms = {m.member: m.platform_type for m in db.session.query(FederationMember).filter_by(federation_pk=row.federation_pk)}
    destinations = {m: platforms[m] for m, info in sorted(state.items()) if m != row.member and m in platforms and info.get("created", True)}
    return HumanContext(fed, row.member, row.platform_type, human.human_id, int(user_id), str(own["account_id"]),
                        {m: str(i["account_id"]) for m, i in state.items()}, destinations)


def destinations_for(exp_id, user_id) -> List[dict]:
    """``[{member, platform_type}]`` the composer offers (empty for a person who is not enrolled)."""
    ctx = context_for(exp_id, user_id)
    return [{"member": m, "platform_type": p} for m, p in (ctx.destinations.items() if ctx else [])]


def crosspost_to(ctx: HumanContext, requested, text) -> List[dict]:
    """``[{member, text}]``: the requested members that are enrolled destinations, in a stable order, each with its text."""
    wanted = sorted({str(m) for m in requested or [] if str(m) in ctx.destinations})[:MAX_TARGETS]
    return [{"member": m, "text": rule_text(ctx.destinations[m], text)} for m in wanted]


def requested_members(values) -> List[str]:
    """The ``crosspost`` values of a request (repeated parameter, or one comma separated string)."""
    out: List[str] = []
    for v in values or []:
        out += [p.strip() for p in str(v).split(",") if p.strip()]
    return out


# -- delivery -------------------------------------------------------------------------------------------
def _runtime_gateway(exp, platform_type, session=None, offline=None):
    from y_web.src.federation.human_gateways import RuntimeGateway

    folder = service.experiment_dir(exp)
    return RuntimeGateway(platform_type, folder, server_config=service.server_config_path(exp), database=folder / "database_server.db",
                          session=session, offline=offline)


def _ok(status, payload) -> bool:
    return status in (200, 201) and (payload or {}).get("ok", True) is not False


def publish_micro_like(exp, ctx: HumanContext, action: dict, *, username: str, session=None, offline=None):
    """One action of the person on microblogging, forum or photo sharing through the runtime gateway."""
    key = str(ctx.user_id) if ctx.platform_type == "photo_sharing" else f"u{ctx.user_id}"
    gateway = _runtime_gateway(exp, ctx.platform_type, session, offline)
    status, payload = gateway.actions(ctx.account_id, username, key, [action])
    return _ok(status, payload), status, payload


def micro_post(text: str, targets: list) -> dict:
    return {"type": "post", "text": text, "crosspost_to": targets}


def micro_share(post_id, text: str, targets: list) -> dict:
    return {"type": "share", "post_id": post_id, "text": text, "crosspost_to": targets}


def forum_post(text: str, targets: list) -> dict:
    return {"action": "post", "text": text, "crosspost_to": targets}


def photo_post(caption: str, targets: list, *, image_base64: str = "", extension: str = "", image_url: str = "") -> dict:
    action = {"type": "post_photo", "caption": caption, "crosspost_to": targets}
    if image_url:
        action["image_url"] = image_url
    else:
        action.update(image_base64=image_base64, extension=extension)
    return action


def photo_share(photo_id, caption: str, targets: list) -> dict:
    return {"type": "share", "photo_id": photo_id, "caption": caption, "crosspost_to": targets}


def im_action(kind: str, targets: list, **fields) -> dict:
    """An instant messaging action (``post`` or ``forward``) with ``crosspost_to``; the rest as the IM gateway takes it."""
    action = {"type": kind, **fields}
    if targets:
        action["crosspost_to"] = targets[:MAX_TARGETS]
    return action


def try_deliver(exp_id, user, requested, text, build, *, only=None, session=None, offline=None):
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
        ok, _status, _payload = publish_micro_like(exp, ctx, build(targets), username=str(user.username), session=session, offline=offline)
    except Exception:  # noqa: BLE001 - a gateway that cannot be reached is a refusal, never a second write
        return False
    return ok


def targets_for_request(exp_id, user, requested, text) -> list:
    """``crosspost_to`` of an action sent through an existing gateway client (instant messaging, dating); ``[]`` when the
    person is not enrolled or picked nothing. A client-sent ``crosspost_to`` is never trusted: only this is."""
    ctx = context_for(exp_id, getattr(user, "id", None))
    return crosspost_to(ctx, requested, text) if ctx is not None and requested else []


def enrolment_of(exp_id, user_id):
    """``(federation, member, human)`` when the person is enrolled (active) on this member, created or still pending
    (dating: the account exists only after the person joined); ``None`` otherwise."""
    from y_web.src.models.admin import Federation, FederationHuman, FederationMember

    if user_id is None:
        return None
    row = db.session.query(FederationMember).filter_by(exp_id=int(exp_id)).first()
    if row is None:
        return None
    human = db.session.query(FederationHuman).filter_by(federation_pk=row.federation_pk, user_id=int(user_id), status="active").first()
    if human is None or row.member not in members_state(human):
        return None
    return db.session.get(Federation, row.federation_pk), row.member, human
