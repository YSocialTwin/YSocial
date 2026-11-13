"""Identity of a human participant in an IM run (plan 4.8, 6.8, DEC-19).

The IM account of a participant is derived from the experiment and the YWeb user, never from a request
parameter. The derivation is the one of the runtime (``OrchestratorServer.human_account_id``), so the
same person always finds the same account, also after a restart or a resumed run.
"""

import uuid

HUMAN_KEY_PREFIX = "yim-human:"


def human_key(exp_uid: str, admin_user_id: int) -> str:
    """The string the gateway is asked to register; stable for ``(experiment, user)``."""
    uid = str(exp_uid).strip("/\\")
    return f"{uid}:{int(admin_user_id)}"


def human_account_id(exp_uid: str, admin_user_id: int) -> str:
    """``h-<uuid5>``; identical to the id the IM server assigns for the same key."""
    key = human_key(exp_uid, admin_user_id)
    return "h-" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"{HUMAN_KEY_PREFIX}{key}"))


def experiment_uid(exp) -> str:
    """Folder name of the experiment (``experiments/<uid>/database_server.db``)."""
    parts = str(exp.db_name).replace("\\", "/").split("/")
    return parts[1] if len(parts) > 1 else parts[0].removeprefix("experiments_")


def display_name(user, pseudonymise: bool = False) -> str:
    """Name shown to the simulated agents: the username, or ``participant-<id>`` when pseudonymised."""
    if pseudonymise:
        return f"participant-{int(user.id)}"
    return str(user.username)
