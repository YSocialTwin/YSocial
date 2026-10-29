"""Participant mode of the IM frontend (plan 6.8): who may take part, CSRF, and the action allowlist.

The account of a participant is derived from the session and the experiment; no request parameter names
it. Writes go through the human gateway (``gateway_client``); this module only decides what is allowed.
"""

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Optional

from y_web.src.im.gateway_process import human_config, human_enabled
from y_web.src.im.human_identity import (
    display_name,
    experiment_uid,
    human_account_id,
    human_key,
)

PARTICIPANT_ROLES = ("user", "student")
CSRF_SESSION_KEY = "im_csrf"
CSRF_HEADER = "X-CSRF-Token"
NOTICE_SESSION_PREFIX = "im_notice_ok_"
MAX_CLIENT_ACTION_ID = 64

#: action -> frontend setting that must be on (plan 7.2); ``interactions_enabled`` governs all of them
ACTION_SETTING = {
    "post": "interaction_post",
    "reply": "interaction_comment",
    "forward": "interaction_share",
    "react": "interaction_like",
}
ACTION_TYPES = frozenset(
    {
        "post",
        "reply",
        "forward",
        "react",
        "edit",
        "delete",
        "join",
        "leave",
        "read",
        "create_forum_topic",
        "delete_forum_topic",
        "create_chat",
        "rename_chat",
        "ban",
        "restrict",
    }
)


@dataclass(frozen=True)
class Participant:
    user_id: int
    username: str
    key: str
    account_id: str
    exp_folder: str
    edits: bool = (
        False  # the run allows editing and deleting own messages (``telegram.edits.enabled``)
    )
    create_chats: bool = (
        True  # ``human.chat_creation.enabled``: the person may start channels, groups and chats
    )
    private_groups: bool = True  # ... invite-only groups
    direct_chats: bool = True  # ... one-to-one chats


def experiment_folder(exp) -> str:
    from y_web.src.system.path_utils import get_writable_path

    return os.path.join(
        get_writable_path(), "y_web", "experiments", experiment_uid(exp)
    )


def participation_on(exp, ui) -> bool:
    """Human participation is on for the experiment and the researcher offers the mode."""
    return bool(ui.get("im_participant_mode_enabled", True)) and human_enabled(
        experiment_folder(exp)
    )


def _edits_enabled(folder: str) -> bool:
    import json

    try:
        with open(os.path.join(folder, "server_config.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        return bool(((cfg.get("telegram") or {}).get("edits") or {}).get("enabled"))
    except (OSError, ValueError, AttributeError):
        return False


def _chat_creation_options(folder: str) -> dict:
    """What the run lets a person create (``human.chat_creation``; everything is on when the block is missing)."""
    import json

    try:
        with open(os.path.join(folder, "server_config.json"), encoding="utf-8") as fh:
            block = ((json.load(fh).get("human") or {}).get("chat_creation")) or {}
    except (OSError, ValueError, AttributeError):
        block = {}
    return {
        "create_chats": bool(block.get("enabled", True))
        and int(block.get("max_owned_chats", 5)) > 0,
        "private_groups": bool(block.get("allow_private_groups", True)),
        "direct_chats": bool(block.get("allow_direct", True)),
    }


def participant_for(exp, user, ui, assigned: bool) -> Optional[Participant]:
    """The participant behind ``user`` for this experiment, or ``None`` (observer only)."""
    if (
        user is None
        or getattr(user, "role", None) not in PARTICIPANT_ROLES
        or not assigned
    ):
        return None
    if not participation_on(exp, ui):
        return None
    uid = experiment_uid(exp)
    return Participant(
        int(user.id),
        str(user.username),
        human_key(uid, user.id),
        human_account_id(uid, user.id),
        experiment_folder(exp),
        _edits_enabled(experiment_folder(exp)),
        **_chat_creation_options(experiment_folder(exp)),
    )


def max_humans(exp) -> int:
    return int(human_config(experiment_folder(exp)).get("max_humans", 50))


def pseudonym(user, exp_folder: Optional[str] = None) -> str:
    """The username a participant gets in the run: their own, or ``participant-<id>`` when the experiment sets
    ``human.pseudonymise_usernames`` in its ``server_config.json``."""
    on = bool(
        exp_folder and human_config(exp_folder).get("pseudonymise_usernames", False)
    )
    return display_name(user, pseudonymise=on)


# -- CSRF (the app has no global protection; these routes carry their own) -----------------------
def csrf_token(session) -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def csrf_ok(session, presented: Optional[str]) -> bool:
    expected = session.get(CSRF_SESSION_KEY)
    return bool(expected and presented) and hmac.compare_digest(
        str(expected).encode(), str(presented).encode()
    )


def namespaced_action_id(account_id: str, client_action_id: str) -> Optional[str]:
    """The id the server stores: tied to the account so one person cannot collide with another."""
    cid = str(client_action_id or "")
    if not cid or len(cid) > MAX_CLIENT_ACTION_ID:
        return None
    return "w-" + hashlib.sha256(f"{account_id}:{cid}".encode()).hexdigest()[:40]


def exposure_request_id(account_id: str, round_id, chat_id: str) -> str:
    """The request id under which a page records what it showed: one per participant, round and chat.

    The server records a message once per request id, so a refresh of the same chat in the same round counts
    once, while a message that arrives later, or the same chat in a later round, counts again.
    """
    return (
        "yweb-"
        + hashlib.sha256(f"{account_id}|{round_id}|{chat_id}".encode()).hexdigest()[:40]
    )


def action_allowed(ui, action_type: str) -> Optional[str]:
    """``None`` when the action may be attempted, else the reason it is switched off."""
    if action_type not in ACTION_TYPES:
        return "unknown_action"
    if not ui.get("interactions_enabled", True):
        return "interactions_disabled"
    setting = ACTION_SETTING.get(action_type)
    if setting and not ui.get(setting, True):
        return f"{setting}_disabled"
    return None
