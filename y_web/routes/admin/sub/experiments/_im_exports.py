"""Instant messaging experiments: export job and report listing (plan, 5.7)."""

import os

from flask import flash, redirect, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.im import is_im_experiment
from y_web.src.im.analysis import EXPORT_FORMATS, resolve_artifact, run_export
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
        flash(_("Export finished. The files are listed in the Export and reports panel."))
    else:
        flash(_("Export failed: %(error)s", error=result.get("error", "")), "error")
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


# analytics pages read the YSocial schema; an IM database has none of it (plan, 5.7)
_YSOCIAL_ANALYTICS_ENDPOINTS = frozenset(
    {
        "opinion_evolution", "opinion_evolution_data", "stress_reward_evolution",
        "stress_reward_evolution_data", "toxicity_evolution", "toxicity_evolution_data",
        "sentiment_evolution", "sentiment_evolution_data", "emotion_statistics",
        "emotion_statistics_data", "topic_evolution", "topic_evolution_data",
        "hashtag_evolution", "hashtag_evolution_data", "recsys_evolution",
        "recsys_evolution_data", "network_analysis", "network_analysis_data",
    }
)


@experiments.before_request
def _keep_ysocial_analytics_away_from_im_databases():
    endpoint = (request.endpoint or "").rpartition(".")[2]
    expid = (request.view_args or {}).get("expid")
    if endpoint not in _YSOCIAL_ANALYTICS_ENDPOINTS or expid is None:
        return None
    if not current_user.is_authenticated:
        return None  # login_required answers
    if _im_experiment_or_none(expid) is None:
        return None
    flash(_("This analysis is not available for instant messaging experiments."), "error")
    if endpoint.endswith("_data"):
        from flask import jsonify

        return jsonify({"error": _("This analysis is not available for instant messaging experiments.")}), 404
    return redirect(url_for("experiments.experiment_details", uid=expid))
