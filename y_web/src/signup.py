"""Self-registration of participants.

The administrator switches the signup page on and chooses which experiments and
training modules a visitor may join (Miscellanea > System Settings). A target is
*offered* only while it is available: the experiment is activated (``Exps.status``
is 1), the module is not archived and has an open run.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.models import (
    Admin_users,
    Exps,
    SignupSettings,
    SignupTarget,
    User_Experiment,
)

EXPERIMENT = "experiment"
TRAINING = "training"

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


def is_enabled() -> bool:
    row = db.session.get(SignupSettings, 1)
    return bool(row and row.enabled)


def selected() -> dict[str, set[str]]:
    """The targets the administrator allowed, whether or not they are available right now."""
    out: dict[str, set[str]] = {EXPERIMENT: set(), TRAINING: set()}
    for row in db.session.scalars(select(SignupTarget)).all():
        out.setdefault(row.kind, set()).add(row.ref)
    return out


def save(enabled: bool, experiments, modules) -> None:
    """Replace the switch and the allowed targets."""
    row = db.session.get(SignupSettings, 1)
    if row is None:
        row = SignupSettings(id=1, enabled=bool(enabled))
        db.session.add(row)
    row.enabled = bool(enabled)
    db.session.query(SignupTarget).delete()
    for exp_id in sorted({str(int(e)) for e in experiments or []}):
        db.session.add(SignupTarget(kind=EXPERIMENT, ref=exp_id))
    for uid in sorted({str(m) for m in modules or [] if str(m)}):
        db.session.add(SignupTarget(kind=TRAINING, ref=uid[:64]))
    db.session.commit()


def training_candidates() -> list[dict] | None:
    """Modules of the Training plugin, or ``None`` when the plugin is missing or disabled."""
    try:
        from y_web.src.external_runtime.backend_plugins import training_signup_api

        api = training_signup_api()
        return api.candidates() if api else None
    except Exception:
        return None


def candidates() -> dict:
    """Everything the configuration box shows: all experiments / modules, flagged with the selection."""
    chosen = selected()
    experiments = [
        {
            "id": exp.idexp,
            "name": exp.exp_name,
            "platform": exp.platform_type,
            "active": exp.status == 1,
            "selected": str(exp.idexp) in chosen[EXPERIMENT],
        }
        for exp in db.session.scalars(select(Exps).order_by(Exps.exp_name)).all()
    ]
    modules = training_candidates()
    if modules is not None:
        modules = [
            dict(m, selected=m["uid"] in chosen[TRAINING], active=not m["archived"])
            for m in modules
        ]
    return {"enabled": is_enabled(), "experiments": experiments, "modules": modules}


def offers() -> list[dict]:
    """What a visitor can join right now: ``{"kind", "ref", "label", "detail"}``."""
    chosen = selected()
    out = []
    if chosen[EXPERIMENT]:
        ids = [int(r) for r in chosen[EXPERIMENT]]
        for exp in db.session.scalars(
            select(Exps)
            .where(Exps.idexp.in_(ids), Exps.status == 1)
            .order_by(Exps.exp_name)
        ).all():
            out.append(
                {
                    "kind": EXPERIMENT,
                    "ref": str(exp.idexp),
                    "label": exp.exp_name,
                    "detail": exp.platform_type,
                }
            )
    if chosen[TRAINING]:
        for module in training_candidates() or []:
            if (
                module["uid"] in chosen[TRAINING]
                and not module["archived"]
                and module["open_run"]
            ):
                out.append(
                    {
                        "kind": TRAINING,
                        "ref": module["uid"],
                        "label": module["title"],
                        "detail": "",
                    }
                )
    return out


def is_open() -> bool:
    """The page works: switched on and at least one target to join."""
    return is_enabled() and bool(offers())


class SignupError(Exception):
    """A validation problem, with a message fit for the visitor."""


def create_account(username: str, email: str, password: str, picks: list[str]) -> dict:
    """Validate, create the participant and join the picked targets.

    ``picks`` are ``"experiment:<id>"`` / ``"training:<uid>"`` strings; each must be offered right now.
    Returns ``{"user_id", "joined", "failed"}``. Raises :class:`SignupError`.
    """
    username = (username or "").strip()
    email = (email or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise SignupError(
            _(
                "The username must have 3 to 15 characters: letters, digits, dots, dashes or underscores."
            )
        )
    if not EMAIL_RE.match(email) or len(email) > 50:
        raise SignupError(_("Please enter a valid email address."))
    if len(password or "") < MIN_PASSWORD:
        raise SignupError(
            _("The password must have at least %(n)s characters.", n=MIN_PASSWORD)
        )

    available = {f"{o['kind']}:{o['ref']}": o for o in offers()}
    chosen = [available[p] for p in dict.fromkeys(picks or []) if p in available]
    if not chosen:
        raise SignupError(_("Choose at least one of the available activities."))

    if (
        db.session.scalars(select(Admin_users).filter_by(email=email)).first()
        or db.session.scalars(select(Admin_users).filter_by(username=username)).first()
    ):
        raise SignupError(_("An account with this username or email already exists."))

    user = Admin_users(
        username=username,
        email=email,
        password=generate_password_hash(password),
        role="user",
        last_seen="",
    )
    db.session.add(user)
    db.session.flush()
    for offer in chosen:
        if offer["kind"] == EXPERIMENT:
            db.session.add(User_Experiment(user_id=user.id, exp_id=int(offer["ref"])))
    db.session.commit()

    joined, failed = [o["label"] for o in chosen if o["kind"] == EXPERIMENT], []
    modules = [o for o in chosen if o["kind"] == TRAINING]
    if modules:
        try:
            from y_web.src.external_runtime.backend_plugins import training_signup_api

            api = training_signup_api()
        except Exception:
            api = None
        for offer in modules:
            outcome = api.enroll(offer["ref"], user.id) if api else "unavailable"
            (joined if outcome in ("enrolled", "duplicate") else failed).append(
                offer["label"]
            )
    return {"user_id": user.id, "joined": joined, "failed": failed}
