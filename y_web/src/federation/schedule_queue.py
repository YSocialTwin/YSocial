"""Queue of World Simulations (F5.5, D-13), separate from the experiment scheduler.

One World Simulation runs at a time, in order of ``position``; the next one starts when the previous one is completed or
failed. A simulation is accepted, and started, only when none of its member experiments is running or sits in a group of
the experiment scheduler. Nothing of the experiment scheduler is read for writing or changed."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from y_web import db
from y_web.src.federation import health, service
from y_web.src.federation.notifications import notify_failure
from y_web.src.models.admin import Federation, FederationScheduleQueue

OPEN_STATES = ("queued", "running")
FINAL_STATES = ("completed", "failed", "cancelled")


def members_busy(fed) -> list:
    """Names of the member experiments that are running or belong to an open group of the experiment scheduler."""
    from y_web.src.models import ExperimentScheduleGroup, ExperimentScheduleItem

    busy = []
    for _, exp in service.members_of(fed):
        running = bool(exp.running) or str(exp.exp_status) in ("active", "scheduled")
        scheduled = (
            db.session.query(ExperimentScheduleItem)
            .join(ExperimentScheduleGroup, ExperimentScheduleGroup.id == ExperimentScheduleItem.group_id)
            .filter(ExperimentScheduleItem.experiment_id == exp.idexp, ExperimentScheduleGroup.is_completed == 0)
            .first()
            is not None
        )
        if running or scheduled:
            busy.append(exp.exp_name)
    return busy


def enqueue(fed) -> FederationScheduleQueue:
    open_item = FederationScheduleQueue.query.filter(
        FederationScheduleQueue.federation_id == fed.id, FederationScheduleQueue.status.in_(OPEN_STATES)
    ).first()
    if open_item is not None:
        raise service.WorldSimulationError({"code": "already_queued", "message": "The World Simulation is already in the queue."})
    if fed.status in ("starting", "running", "paused", "stopping"):
        raise service.WorldSimulationError({"code": "state", "message": f"The World Simulation is {fed.status}."})
    busy = members_busy(fed)
    if busy:
        raise service.WorldSimulationError(
            {"code": "member_busy", "message": "Member experiments are running or scheduled: " + ", ".join(busy)}
        )
    last = db.session.query(db.func.max(FederationScheduleQueue.position)).scalar()
    item = FederationScheduleQueue(federation_id=fed.id, position=(last or 0) + 1, status="queued")
    db.session.add(item)
    db.session.commit()
    return item


def cancel(item) -> bool:
    """Only a queued entry can be cancelled (a running one is stopped from its own page)."""
    if item.status != "queued":
        return False
    item.status = "cancelled"
    item.finished_at = datetime.now()
    db.session.commit()
    return True


def rows() -> list:
    out = []
    for item in FederationScheduleQueue.query.order_by(FederationScheduleQueue.position).all():
        out.append((item, db.session.get(Federation, item.federation_id)))
    return out


def _finish(item, status):
    item.status = status
    item.finished_at = datetime.now()
    db.session.commit()


def advance() -> dict:
    """One step of the queue: close the running entry when its simulation ended, start the next queued one."""
    from y_web.src.simulation import execution_backend as eb

    result = {"completed": [], "failed": [], "cancelled": [], "started": []}
    running = FederationScheduleQueue.query.filter_by(status="running").order_by(FederationScheduleQueue.position).first()
    if running is not None:
        fed = db.session.get(Federation, running.federation_id)
        if fed is None:
            _finish(running, "cancelled")
        else:
            health.check_federation(fed)
            if fed.status == "completed":
                _finish(running, "completed")
                result["completed"].append(running.id)
            elif fed.status == "failed":
                _finish(running, "failed")
                result["failed"].append(running.id)
            elif fed.status == "stopped":  # stopped by hand from its page
                _finish(running, "cancelled")
                result["cancelled"].append(running.id)
        if running.status == "running":
            return result
    while True:
        item = FederationScheduleQueue.query.filter_by(status="queued").order_by(FederationScheduleQueue.position).first()
        if item is None:
            return result
        fed = db.session.get(Federation, item.federation_id)
        if fed is None:
            _finish(item, "cancelled")
            continue
        busy = members_busy(fed)
        if busy:
            notify_failure(fed, "start", "member experiments are running or scheduled: " + ", ".join(busy))
            _finish(item, "failed")
            result["failed"].append(item.id)
            continue
        item.status = "running"
        item.started_at = datetime.now()
        db.session.commit()
        try:
            eb.start_federation(fed)  # notifies a failed start itself
        except Exception:
            _finish(item, "failed")
            result["failed"].append(item.id)
            continue
        result["started"].append(item.id)
        return result
