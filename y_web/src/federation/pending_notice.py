"""Cross-posts waiting for a person whose platform is stopped (P7): the notice shown while the World Simulation runs.

A person enrolled in a World Simulation can be on a member whose server is stopped while the coordinator keeps running (the
other platforms go on). What others cross-posted to that platform is delivered at the first barrier after the restart; until
then ``GET /v1/pending`` of the coordinator tells what is waiting (read-only: nothing is acknowledged). The helper shows
exactly what the endpoint returns: with ``crosspost.mode = coordinator_rule`` a cross-post that has not been materialised yet
is not in the endpoint's answer, so it is not shown either.

No request is made, and nothing is read, unless the experiment is a member of a World Simulation whose coordinator runs, the
person is enrolled there with an account on this member, and the member's server is stopped (NFR-01). Every error means "no
notice": a page never fails because of this.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional

from y_web import db
from y_web.src.federation.human_outbox import enrolment_of
from y_web.src.federation.quotes import platform_label

CACHE_SECONDS = 5.0
MAX_SHOWN = 20
COORDINATOR_UP = ("running", "paused")

_cache: dict = {}


def _client(fed, member):
    from ysocial_federation.client import CoordinatorClient

    folder = Path(fed.folder)
    return CoordinatorClient.from_files(folder / "federation_coordinator.json", folder / "federation.token", member, retry_budget=1.0)


def _line(item: dict) -> dict:
    """``{text, attribution, source}`` of one pending cross-post (attribution only when it quotes someone)."""
    quoted = item.get("quoted") or None
    attribution = ""
    if isinstance(quoted, dict) and quoted.get("author_name"):
        attribution = f"↪ {quoted['author_name']} @ {platform_label(quoted.get('member'))}"
        if quoted.get("text_excerpt"):
            attribution += f": «{quoted['text_excerpt']}»"
    return {"text": str(item.get("text_excerpt") or ""), "attribution": attribution, "source": platform_label(item.get("source_member"))}


def pending_for(exp_id, user_id, *, client_factory: Optional[Callable] = None, clock: Callable[[], float] = time.monotonic) -> List[dict]:
    """The cross-posts waiting for the person on this (stopped) member; ``[]`` in every other case, and on every error."""
    try:
        enrolment = enrolment_of(exp_id, user_id)
        if enrolment is None:
            return []
        fed, member, human = enrolment
        if fed.status not in COORDINATOR_UP:
            return []
        from y_web.src.federation.humans import members_state
        from y_web.src.models import Exps

        exp = db.session.get(Exps, int(exp_id))
        info = members_state(human).get(member) or {}
        if exp is None or exp.server_pid or not info.get("account_id") or info.get("created") is False:
            return []
        key = (fed.id, member, str(info["account_id"]))
        now = clock()
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < CACHE_SECONDS:
            return hit[1]
        client = (client_factory or _client)(fed, member)
        lines = [_line(i) for i in client.pending(info["account_id"])[:MAX_SHOWN]]
        _cache[key] = (now, lines)
        return lines
    except Exception:  # noqa: BLE001 - a page never fails because of the federation
        return []
