"""Admin notifications of World Simulation failures (F5.6): coordinator errors and starts that failed.

They use the notification records the admin interface already shows (``DownloadNotification``, status "failed"); the
text always says "World Simulation"."""

from __future__ import annotations

from y_web import db

TITLES = {
    "start": "World Simulation: start failed",
    "coordinator": "World Simulation: coordinator error",
    "member": "World Simulation: a member failed",
}


def _recipients(fed):
    from sqlalchemy import select

    from y_web.src.models import Admin_users

    owner = (
        db.session.scalars(select(Admin_users).filter_by(username=fed.owner)).first()
        if fed.owner
        else None
    )
    if owner is not None:
        return [owner]
    return list(db.session.scalars(select(Admin_users).filter_by(role="admin")))


def notify_failure(fed, kind: str, detail: str = "") -> list:
    """Create one failed notification for the owner (or for the admins when the owner is unknown). Never raises."""
    from y_web.src.models import DownloadNotification

    try:
        title = TITLES.get(kind, "World Simulation: error")
        message = f"{fed.name}: {detail}".strip(": ")[:500]
        rows = []
        for user in _recipients(fed):
            row = DownloadNotification(
                user_id=user.id,
                title=title,
                message=message,
                status="failed",
                is_read=False,
                error_message=message,
            )
            db.session.add(row)
            rows.append(row)
        db.session.commit()
        return rows
    except Exception:  # a failing notification must never hide the original error
        db.session.rollback()
        return []
