"""Instant messaging experiments: export job and report listing (plan, 5.7)."""

import os

from flask import flash, redirect, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.im import is_im_experiment
from y_web.src.im.analysis import (
    EXPORT_FORMATS,
    REPORT_COMMANDS,
    resolve_artifact,
    run_export,
    run_report,
)
from y_web.src.models import Exps
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import experiments


def _im_experiment_or_none(idexp):
    exp = db.session.scalars(select(Exps).filter_by(idexp=idexp)).first()
    return exp if exp is not None and is_im_experiment(exp) else None


def _folder(exp) -> str:
    from y_web.src.system.path_utils import get_writable_path

    parts = exp.db_name.split(os.sep)
    return os.path.join(get_writable_path(), "y_web", "experiments", parts[1])


@experiments.route("/admin/im_export/<int:idexp>", methods=["POST"])
@login_required
def im_export(idexp):
    """Run ``yim-export`` for an IM experiment (a snapshot of the database while it runs)."""
    check_privileges(current_user.username)
    back = request.referrer or url_for("admin.dashboard")
    exp = _im_experiment_or_none(idexp)
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect(back)
    fmt = request.form.get("format", "csv")
    if fmt not in EXPORT_FORMATS:
        flash(_("Unknown export format."), "error")
        return redirect(back)
    ok, result = run_export(
        _folder(exp),
        fmt,
        no_text=request.form.get("no_text") in {"1", "true", "on"},
        snapshot=bool(exp.running),
    )
    if ok:
        flash(
            _("Export finished. The files are listed in the Export and reports panel.")
        )
    else:
        flash(_("Export failed: %(error)s", error=result.get("error", "")), "error")
    return redirect(back)


@experiments.route("/admin/im_report/<int:idexp>", methods=["POST"])
@login_required
def im_report(idexp):
    """Run one ``yim-analyze`` report for an IM experiment (a snapshot of the database while it runs)."""
    check_privileges(current_user.username)
    back = request.referrer or url_for("admin.dashboard")
    exp = _im_experiment_or_none(idexp)
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect(back)
    command = request.form.get("report", "")
    if command not in REPORT_COMMANDS:
        flash(_("Unknown report."), "error")
        return redirect(back)
    ok, result = run_report(_folder(exp), command, snapshot=bool(exp.running))
    if ok:
        flash(_("Report finished. It is listed in the Export and reports panel."))
    else:
        flash(_("Report failed: %(error)s", error=result.get("error", "")), "error")
    return redirect(back)


@experiments.route("/admin/im_artifact/<int:idexp>/<kind>/<path:name>")
@login_required
def im_artifact(idexp, kind, name):
    """Download one export or report file of an IM experiment."""
    check_privileges(current_user.username)
    exp = _im_experiment_or_none(idexp)
    path = resolve_artifact(_folder(exp), kind, name) if exp is not None else None
    if path is None:
        flash(_("File not found."), "error")
        return redirect(request.referrer or url_for("admin.dashboard"))
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@experiments.route("/admin/im/analytics/<int:idexp>/refresh", methods=["POST"])
@login_required
def im_analytics_refresh(idexp):
    """Rebuild the derived analytics database now (plan 5.7, 8.2)."""
    check_privileges(current_user.username)
    exp = _im_experiment_or_none(idexp)
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect("/admin/experiments")
    from y_web.src.im import analytics

    result = analytics.ensure_derived(exp, force=True)
    if result.get("state") == "failed":
        flash(
            _(
                "Analytics data could not be built: %(message)s",
                message=result.get("message", ""),
            ),
            "error",
        )
    elif result.get("state") == "running":
        flash(_("Analytics data are being built."), "info")
    elif result.get("state") == "never":
        flash(_("The experiment has no data to analyze yet."), "info")
    else:
        flash(_("Analytics data refreshed."), "success")
    return redirect(url_for("experiments.experiment_details", uid=idexp))


# the analytics pages of IM experiments read the derived database; bring it up to date before any of them runs, so
# their own checks (``Exps.annotations``, table presence) see the current state (plan 4.7)
_ANALYTICS_ENDPOINTS = frozenset(
    {
        "opinion_evolution",
        "opinion_evolution_data",
        "stress_reward_evolution",
        "stress_reward_evolution_data",
        "toxicity_evolution",
        "toxicity_analytics_data",
        "sentiment_evolution",
        "sentiment_analytics_data",
        "emotion_statistics",
        "emotion_analytics_data",
        "emotion_statistics_data",
        "topic_evolution",
        "topic_evolution_data",
        "hashtag_evolution",
        "hashtag_evolution_data",
        "recsys_evolution",
        "recsys_evolution_data",
        "network_analysis",
        "network_analysis_data",
    }
)


@experiments.before_request
def _refresh_im_analytics_before_the_pages():
    endpoint = (request.endpoint or "").rpartition(".")[2]
    expid = (request.view_args or {}).get("expid")
    if (
        endpoint not in _ANALYTICS_ENDPOINTS
        or expid is None
        or not current_user.is_authenticated
    ):
        return None
    exp = _im_experiment_or_none(expid)
    if exp is not None:
        from y_web.src.im import analytics

        analytics.ensure_derived(exp)
    return None
