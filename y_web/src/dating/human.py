"""Participant mode of the dating frontend (IR-D-22, IR-D-27): who may take part, identity, CSRF.

The account of a person is derived from the experiment and the YWeb user, never from a request parameter,
and equals the id the runtime derives from the same key (``human_id_for``). Writes go through the gateway
(``gateway.GatewayClient``); this module only decides what may be attempted. The server enforces the rules
again, so a switched-off interaction answers 403 whatever the page shows.
"""

import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from typing import Optional

from y_web.src.dating.gateway import human_config, human_enabled

PARTICIPANT_ROLES = ("user", "student")
CSRF_SESSION_KEY = "dating_csrf"
CSRF_HEADER = "X-CSRF-Token"
NOTICE_SESSION_PREFIX = "dating_notice_ok_"
MAX_NOTICE_CHARS = 4000

#: the actions a page may send; the runtime keeps the same list and checks the fields of each
ACTION_TYPES = frozenset(
    {
        "LIKE",
        "PASS",
        "SUPERLIKE",
        "OPEN_CONVERSATION",
        "IGNORE",
        "SEND_MESSAGE",
        "REPLY",
        "REACT_MESSAGE",
        "UNMATCH",
        "BLOCK",
        "REPORT",
        "PROPOSE_DATE",
        "ACCEPT_DATE",
        "DECLINE_DATE",
        "PAUSE_PROFILE",
        "RESUME_PROFILE",
        "UPDATE_PROFILE",
        "UPDATE_PREFERENCES",
        "VIEW_PROFILE",
        "ADD_PHOTO",
        "REMOVE_PHOTO",
    }
)
REPORT_REASONS = ("HARASSMENT", "SPAM", "FAKE", "INAPPROPRIATE")
REACTIONS = ("LOVE", "LAUGH", "LIKE")
INTENTS = ("serious", "casual", "friendship", "unsure")


@dataclass(frozen=True)
class Participant:
    user_id: int
    username: str
    key: str
    account_id: str
    exp_folder: str


def experiment_uid(exp) -> str:
    """Folder name of the experiment (``experiments/<uid>/database_server.db``)."""
    parts = str(exp.db_name).replace("\\", "/").split("/")
    return parts[1] if len(parts) > 1 else parts[0].removeprefix("experiments_")


def experiment_folder(exp) -> str:
    from y_web.src.system.path_utils import get_writable_path

    return os.path.join(
        get_writable_path(), "y_web", "experiments", experiment_uid(exp)
    )


def human_key(exp_uid: str, user_id: int) -> str:
    """The string the gateway is asked to register; stable for ``(experiment, user)``."""
    return f"{str(exp_uid).strip('/' + chr(92))}:{int(user_id)}"


def human_account_id(exp_uid: str, user_id: int) -> str:
    """Identical to ``YDating.YServer.human_service.human_id_for`` for the same key."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"ydating:human:{human_key(exp_uid, user_id)}")
    )


def participation_on(exp, ui) -> bool:
    """Human participation is on for the experiment and the researcher offers the mode."""
    return bool(ui.get("dating_participant_mode_enabled", True)) and human_enabled(
        experiment_folder(exp)
    )


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
    )


def max_humans(exp) -> int:
    return int(human_config(experiment_folder(exp)).get("max_humans", 200))


def pseudonym(user) -> str:
    """The name a participant may choose to show instead of their username."""
    return f"participant-{int(user.id)}"


# -- CSRF (the app has no global protection; these routes carry their own)
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


def account_from_form(form, language: str, username: str, photos=None) -> dict:
    """The account document the person filled in (the runtime validates it like an agent's).

    ``photos`` are the pictures already stored for the person (``{"caption", "media_url"?}``).
    """

    def num(name, default=None):
        try:
            return int(form.get(name))
        except (TypeError, ValueError):
            return default

    def dist(name, default):
        try:
            return float(form.get(name))
        except (TypeError, ValueError):
            return default

    seeking = [g.strip() for g in (form.get("seeking") or "").split(",") if g.strip()]
    interests = [
        i.strip() for i in (form.get("interests") or "").split(",") if i.strip()
    ]
    intent = form.get("intent") if form.get("intent") in INTENTS else "unsure"
    profile = {
        "seeking_genders": seeking,
        "age_min": num("age_min", 18),
        "age_max": num("age_max", 99),
        "max_distance_km": dist("max_distance_km", 50.0),
        "intent": intent,
        "bio": (form.get("bio") or "").strip(),
        "city": (form.get("city") or "").strip(),
    }
    return {
        "username": username,
        "age": num("age"),
        "gender": (form.get("gender") or "").strip(),
        "language": language,
        "profile": profile,
        "interests": interests,
        "photos": list(photos or []),
    }
