"""Dating analytics pages (plan S7): dashboard on the derived database, rebuild, CSV exports and a comparison."""

import csv
import io
import os
import zipfile

from flask import Response, flash, redirect, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.dating import analytics_etl as etl
from y_web.src.dating import is_dating_experiment
from y_web.src.models import Exps
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import experiments


def _dating_experiment_or_none(idexp):
    exp = db.session.scalars(select(Exps).filter_by(idexp=idexp)).first()
    return exp if exp is not None and is_dating_experiment(exp) else None


def _folder(exp) -> str:
    from y_web.src.system.path_utils import get_writable_path

    parts = exp.db_name.split(os.sep)
    return os.path.join(get_writable_path(), "y_web", "experiments", parts[1])


def _csv(columns, rows) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    writer.writerows(rows)
    return out.getvalue()


@experiments.route("/admin/dating_analytics/<int:idexp>")
@login_required
def dating_analytics(idexp):
    """Dashboard of a dating experiment: run totals, recommenders, days, date funnel and exits."""
    check_privileges(current_user.username)
    exp = _dating_experiment_or_none(idexp)
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect("/admin/experiments")
    data = etl.cards(_folder(exp))
    others = [
        e
        for e in db.session.scalars(select(Exps).order_by(Exps.exp_name)).all()
        if is_dating_experiment(e) and e.idexp != idexp
    ]
    return render_template(
        "admin/dating_analytics.html",
        experiment=exp,
        data=data,
        tables=etl.EXPORT_TABLES,
        others=others,
    )


@experiments.route("/admin/dating_analytics/<int:idexp>/rebuild", methods=["POST"])
@login_required
def dating_analytics_rebuild(idexp):
    check_privileges(current_user.username)
    exp = _dating_experiment_or_none(idexp)
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect("/admin/experiments")
    result = etl.build(_folder(exp))
    if not result["ok"]:
        flash(
            _(
                "Analytics data could not be built: %(message)s",
                message=result["message"],
            ),
            "error",
        )
    return redirect(f"/admin/dating_analytics/{idexp}")


@experiments.route("/admin/dating_analytics/<int:idexp>/export/<table>.csv")
@login_required
def dating_analytics_export(idexp, table):
    check_privileges(current_user.username)
    exp = _dating_experiment_or_none(idexp)
    if exp is None or table not in etl.EXPORT_TABLES:
        flash(_("Nothing to export."), "error")
        return redirect("/admin/experiments")
    folder = _folder(exp)
    etl.ensure_derived(folder)
    if not os.path.isfile(etl.analytics_path(folder)):
        flash(_("Analytics data have not been built yet."), "error")
        return redirect(f"/admin/dating_analytics/{idexp}")
    columns, rows = etl.table_rows(folder, table)
    return Response(
        _csv(columns, rows),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="dating_{table}.csv"'},
    )


@experiments.route("/admin/dating_analytics/<int:idexp>/export.zip")
@login_required
def dating_analytics_export_all(idexp):
    """Every derived table as CSV plus the field map, in one archive."""
    check_privileges(current_user.username)
    exp = _dating_experiment_or_none(idexp)
    if exp is None:
        flash(_("Nothing to export."), "error")
        return redirect("/admin/experiments")
    folder = _folder(exp)
    etl.ensure_derived(folder)
    if not os.path.isfile(etl.analytics_path(folder)):
        flash(_("Analytics data have not been built yet."), "error")
        return redirect(f"/admin/dating_analytics/{idexp}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for table in etl.EXPORT_TABLES:
            columns, rows = etl.table_rows(folder, table)
            archive.writestr(f"{table}.csv", _csv(columns, rows))
        archive.writestr("FIELD_MAP.md", etl.render_field_map() + "\n")
    return Response(
        buffer.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="dating_analytics_{idexp}.zip"'
        },
    )


@experiments.route("/admin/dating_analytics/compare")
@login_required
def dating_analytics_compare():
    """Recommender measures of two dating experiments side by side (same population and seed compare cleanly)."""
    check_privileges(current_user.username)
    a = _dating_experiment_or_none(request.args.get("a", type=int))
    b = _dating_experiment_or_none(request.args.get("b", type=int))
    if a is None or b is None:
        flash(_("Choose two dating experiments to compare."), "error")
        return redirect(request.referrer or "/admin/experiments")
    sides = []
    for exp in (a, b):
        data = etl.cards(_folder(exp))
        sides.append({"experiment": exp, "data": data})
    return render_template("admin/dating_analytics_compare.html", sides=sides)
