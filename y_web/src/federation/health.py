"""Health of running World Simulations (F5.5, F5.6): coordinator down, member failed, run completed.

``check_federation`` is called by the schedule monitor on every poll; it acts only on running or paused simulations.
"""

from __future__ import annotations

from y_web import db
from y_web.src.federation import coordinator_process as cp
from y_web.src.federation.notifications import notify_failure


def check_federation(fed, *, status_timeout: float = 2.0) -> str:
    """Return "idle", "ok", "completed", "failed". Stops the processes when it ends the run."""
    from y_web.src.simulation import execution_backend as eb

    if fed.status not in ("running", "paused"):
        return "idle"
    if not cp._pid_alive(fed.coordinator_pid):
        detail = "the coordinator stopped unexpectedly"
        notify_failure(fed, "coordinator", detail)
        eb.stop_federation(fed)
        fed.status = "failed"
        db.session.commit()
        return "failed"
    status = cp.coordinator_status(fed, timeout=status_timeout)
    members = (status or {}).get("members") or {}
    if members and all(
        m.get("status") in ("finished", "failed") for m in members.values()
    ):
        failed = sorted(
            name for name, m in members.items() if m.get("status") == "failed"
        )
        eb.stop_federation(fed)
        if failed:
            notify_failure(fed, "member", "failed: " + ", ".join(failed))
            fed.status = "failed"
        else:
            fed.status = "completed"
        db.session.commit()
        return fed.status
    return "ok"
