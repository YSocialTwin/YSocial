"""World Simulation routes (admin section "World Simulation", guide F5, D-12).

Pages: list of simulations, guided creation, detail with the Configuration and Execution tabs, analytics selection and
the schedule. In the interface the feature is always called "World Simulation"; in code it is the federation.
Only admins and researchers reach these routes (a researcher sees only the simulations they own)."""

import json
import sqlite3
from pathlib import Path

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.federation import coordinator_process as cp
from y_web.src.federation import service
from y_web.src.experiment.access import get_visible_experiment_query
from y_web.src.models import Admin_users, Exps
from y_web.src.models.admin import Federation

world_simulation = Blueprint("world_simulation", __name__, url_prefix="/admin/world_simulation")

PLATFORM_LABELS = {
    "microblogging": "Microblogging",
    "forum": "Forum",
    "photo_sharing": "Photo sharing",
    "instant_messaging": "Instant messaging",
    "dating": "Dating",
}
STATE_BADGES = {
    "stopped": "badge-secondary",
    "starting": "badge-info",
    "running": "badge-success",
    "paused": "badge-warning",
    "stopping": "badge-info",
    "completed": "badge-primary",
    "failed": "badge-danger",
}
SWITCHES = ("attention", "discovery", "leave", "pseudonyms")  # parameter blocks with an "enabled" switch (guide 4.7)


def _admin_user():
    return db.session.scalars(select(Admin_users).filter_by(username=current_user.username)).first()


def _allowed(user):
    return user is not None and user.role in ("admin", "researcher")


def _visible_federations(user):
    query = Federation.query.order_by(Federation.id.desc())
    if user.role != "admin":
        query = query.filter(Federation.owner == user.username)
    return query.all()


def _get_or_404(fed_id, user):
    fed = db.session.get(Federation, fed_id)
    if fed is None or (user.role != "admin" and fed.owner != user.username):
        abort(404)
    return fed


def guarded(view):
    """Login required, admin or researcher only (others are sent back to the home page, JSON routes get 403)."""
    from functools import wraps

    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        user = _admin_user()
        if not _allowed(user):
            if request.path.endswith(".json"):
                return jsonify({"error": _("Access denied")}), 403
            return redirect(url_for("main.index"))
        return view(user, *args, **kwargs)

    return wrapper


def _row(fed):
    members = service.members_of(fed)
    status = cp.coordinator_status(fed, timeout=1.0) if fed.status in ("running", "paused") else None
    return {
        "fed": fed,
        "badge": STATE_BADGES.get(fed.status, "badge-secondary"),
        "members": [(m.member, PLATFORM_LABELS.get(m.platform_type, m.platform_type), exp) for m, exp in members],
        "tick": None if not status else status.get("global_tick"),
    }


@world_simulation.route("", strict_slashes=False)
@guarded
def simulations(user):
    return render_template("admin/world_simulation/list.html", rows=[_row(f) for f in _visible_federations(user)])


def _candidates(user):
    exps = get_visible_experiment_query(user).filter(Exps.is_remote == 0).order_by(Exps.exp_name).all()
    out = []
    for exp in exps:
        info = service.collect_member_info(exp)
        out.append({"exp": exp, "platform": PLATFORM_LABELS.get(exp.platform_type, exp.platform_type), "info": info})
    return out


def _options_from_form(form):
    options = {}
    for block in SWITCHES:
        if form.get(f"{block}_enabled"):
            options[block] = {"enabled": True}
    if form.get("topics_present") and not form.get("topic_migration"):
        options["topics"] = {"migration": False}  # on by default: only the opt-out is stored
    raw = (form.get("advanced") or "").strip()
    if raw:
        try:
            extra = json.loads(raw)
        except ValueError:
            raise service.WorldSimulationError({"code": "options", "message": _("The advanced parameters are not valid JSON.")})
        if not isinstance(extra, dict):
            raise service.WorldSimulationError({"code": "options", "message": _("The advanced parameters must be a JSON object.")})
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(options.get(key), dict):
                options[key] = {**value, **options[key]}
            else:
                options[key] = value
    if form.get("crosspost_content_present") and isinstance(options.get("crosspost", {}), dict):
        # nothing checked = all content = the default, not stored; the form wins over a stale copy of the setting in the advanced JSON (the detail page pre-fills it there)
        form_content = [c for c in service.CROSSPOST_CONTENT if c in [service.CROSSPOST_CONTENT_ALIASES.get(v, v) for v in form.getlist("crosspost_content")]]
        crosspost = {k: v for k, v in (options.get("crosspost") or {}).items() if k != "content"}
        if form_content:
            crosspost["content"] = form_content
        if crosspost:
            options["crosspost"] = crosspost
        else:
            options.pop("crosspost", None)
    return options


ERROR_TEXT = {
    "member_count": lambda: _("A World Simulation needs 2 to 5 experiments."),
    "experiment_running": lambda: _("An experiment is running: stop it first."),
    "remote": lambda: _("Remote experiments cannot take part in a World Simulation."),
    "population": lambda: _("All experiments must use the same population."),
    "duplicate_platform": lambda: _("Choose at most one experiment for each platform."),
    "platform": lambda: _("One of the platforms cannot take part in a World Simulation."),
    "simulator_type": lambda: _("One of the experiments uses a backend that is not supported for its platform."),
    "clock": lambda: _("All experiments must use the simulated clock with 24 slots a day."),
    "already_member": lambda: _("An experiment already belongs to another World Simulation."),
    "already_queued": lambda: _("The World Simulation is already in the queue."),
    "member_busy": lambda: _("Member experiments are running or in the experiment schedule."),
    "state": lambda: _("The World Simulation is not in the right state for this operation."),
    "no_member": lambda: _("Pick at least one platform."),
    "unknown_member": lambda: _("That platform is not a member of this World Simulation."),
    "platform_not_supported": lambda: _("This platform has no gateway for human participants."),
    "gateway_unavailable": lambda: _("The gateway of a platform cannot be reached."),
    "gateway_refused": lambda: _("The gateway of a platform refused the account."),
    "coordinator_refused": lambda: _("The coordinator did not accept the participant."),
}


def _flash_errors(error):
    for item in error.errors:
        text = ERROR_TEXT.get(item["code"])
        message = "%s (%s)" % (text(), item["message"]) if text else item["message"]
        flash(message, "error")


@world_simulation.route("/new", methods=["GET", "POST"])
@guarded
def new(user):
    form = request.form
    if request.method == "POST":
        try:
            seed = form.get("seed", "").strip()
            fed = service.create_federation(
                form.get("name"),
                [int(i) for i in form.getlist("experiments")],
                owner=user.username,
                seed=int(seed) if seed else None,
                granularity=form.get("granularity", "slot"),
                options=_options_from_form(form),
                exposures=bool(form.get("discovery_enabled")),
            )
            flash(_("World Simulation created."), "success")
            return redirect(url_for("world_simulation.detail", fed_id=fed.id))
        except service.WorldSimulationError as exc:
            _flash_errors(exc)
        except ValueError:
            flash(_("The seed must be an integer."), "error")
    return render_template("admin/world_simulation/new.html", candidates=_candidates(user), form=form)


@world_simulation.route("/<int:fed_id>")
@guarded
def detail(user, fed_id):
    fed = _get_or_404(fed_id, user)
    options = json.loads(fed.config_json or "{}")
    return render_template(
        "admin/world_simulation/detail.html",
        row=_row(fed),
        participants=_participants(fed),
        candidates_users=db.session.scalars(select(Admin_users).order_by(Admin_users.username)).all(),
        options=options,
        crosspost_content=service.crosspost_content_of(options),
        options_text=json.dumps({k: v for k, v in options.items() if k != "exposures"}, indent=2, sort_keys=True),
        editable=fed.status in ("stopped", "completed", "failed"),
    )


def _participants(fed):
    """The people enrolled: ``[(user, status, [(member label, account id, created)])]`` for the Configuration tab."""
    from y_web.src.federation import humans

    labels = {m.member: PLATFORM_LABELS.get(m.platform_type, m.platform_type) for m, _exp in service.members_of(fed)}
    out = []
    for h in humans.list_humans(fed):
        u = db.session.get(Admin_users, h.user_id)
        state = humans.members_state(h)
        out.append({"user_id": h.user_id, "username": u.username if u else str(h.user_id), "human_id": h.human_id, "status": h.status,
                    "members": [(labels.get(m, m), i["account_id"], bool(i.get("created", True))) for m, i in sorted(state.items())]})
    return out


@world_simulation.route("/<int:fed_id>/humans/enrol", methods=["POST"])
@guarded
def humans_enrol(user, fed_id):
    """Enrol a person (a YWeb user) in some platforms; allowed also while the World Simulation runs (D3)."""
    from y_web.src.federation import humans

    fed = _get_or_404(fed_id, user)
    person = db.session.get(Admin_users, int(request.form.get("user_id") or 0))
    if person is None:
        flash(_("Choose a user."), "error")
        return redirect(url_for("world_simulation.detail", fed_id=fed.id))
    try:
        humans.enrol(fed, person, request.form.getlist("members"))
        flash(_("Participant enrolled."), "success")
    except service.WorldSimulationError as exc:
        _flash_errors(exc)
    return redirect(url_for("world_simulation.detail", fed_id=fed.id))


@world_simulation.route("/<int:fed_id>/humans/<int:user_id>/unenrol", methods=["POST"])
@guarded
def humans_unenrol(user, fed_id, user_id):
    from y_web.src.federation import humans

    fed = _get_or_404(fed_id, user)
    if humans.unenrol(fed, user_id):
        flash(_("Participant removed from the World Simulation. Their accounts stay in the experiments."), "success")
    return redirect(url_for("world_simulation.detail", fed_id=fed.id))


@world_simulation.route("/<int:fed_id>/configuration", methods=["POST"])
@guarded
def configure(user, fed_id):
    """Change the parameters (only while the World Simulation is stopped)."""
    fed = _get_or_404(fed_id, user)
    if fed.status not in ("stopped", "completed", "failed"):
        flash(_("Stop the World Simulation before changing its parameters."), "error")
        return redirect(url_for("world_simulation.detail", fed_id=fed.id))
    try:
        options = _options_from_form(request.form)
        options = service._clean_options(options)
        seed = request.form.get("seed", "").strip()
        granularity = request.form.get("granularity", fed.granularity)
        if granularity not in service.GRANULARITIES:
            raise service.WorldSimulationError({"code": "granularity", "message": _("Granularity must be slot or day.")})
        fed.seed = int(seed) if seed else fed.seed
        fed.granularity = granularity
        fed.config_json = json.dumps({**options, "exposures": bool(request.form.get("discovery_enabled"))})
        service.write_federation_files(fed)
        db.session.commit()
        flash(_("Parameters saved."), "success")
    except service.WorldSimulationError as exc:
        db.session.rollback()
        _flash_errors(exc)
    except ValueError:
        db.session.rollback()
        flash(_("The seed must be an integer."), "error")
    return redirect(url_for("world_simulation.detail", fed_id=fed.id))


def _command(fed_id, user, action):
    from y_web.src.simulation import execution_backend as eb

    fed = _get_or_404(fed_id, user)
    try:
        if action == "start":
            eb.start_federation(fed)
            flash(_("World Simulation started."), "success")
        elif action == "pause":
            eb.pause_federation(fed)
            flash(_("World Simulation paused."), "success")
        elif action == "resume":
            eb.resume_federation(fed)
            flash(_("World Simulation resumed."), "success")
        elif action == "stop":
            errors = eb.stop_federation(fed)
            flash(_("World Simulation stopped."), "success")
            for message in errors:
                flash(message, "error")
    except service.WorldSimulationError as exc:
        _flash_errors(exc)
    except Exception as exc:
        db.session.rollback()
        flash(_("The World Simulation could not complete the operation: %(error)s", error=str(exc)), "error")
    return redirect(url_for("world_simulation.detail", fed_id=fed.id))


for _action in ("start", "pause", "resume", "stop"):

    def _make(action):
        @guarded
        def view(user, fed_id):
            return _command(fed_id, user, action)

        view.__name__ = f"command_{action}"
        return view

    world_simulation.add_url_rule(f"/<int:fed_id>/{_action}", f"command_{_action}", _make(_action), methods=["POST"])


@world_simulation.route("/<int:fed_id>/export")
@guarded
def export(user, fed_id):
    """Bundle of the World Simulation: manifest, coordinator database, analytics and the archive of every member."""
    import tempfile

    from flask import send_file

    from y_web.src.federation import lifecycle

    fed = _get_or_404(fed_id, user)
    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    handle.close()
    try:
        name = lifecycle.export_bundle(fed, handle.name)
    except Exception as exc:  # noqa: BLE001 - shown to the admin, the page stays usable
        Path(handle.name).unlink(missing_ok=True)
        flash(_("The export failed: %(why)s", why=str(exc)), "error")
        return redirect(url_for("world_simulation.detail", fed_id=fed.id))
    response = send_file(handle.name, mimetype="application/zip", as_attachment=True, download_name=name)
    response.call_on_close(lambda: Path(handle.name).unlink(missing_ok=True))
    return response


@world_simulation.route("/import", methods=["POST"])
@guarded
def import_bundle(user):
    from y_web.src.federation import lifecycle

    upload = request.files.get("bundle")
    if upload is None or not upload.filename:
        flash(_("Choose a bundle to import."), "error")
        return redirect(url_for("world_simulation.simulations"))
    import tempfile

    handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    handle.close()
    try:
        upload.save(handle.name)
        fed, report = lifecycle.import_bundle(handle.name, owner=user.username, name=request.form.get("name") or None)
    except service.WorldSimulationError as exc:
        flash(_("The bundle could not be imported: %(why)s", why=str(exc)), "error")
        return redirect(url_for("world_simulation.simulations"))
    finally:
        Path(handle.name).unlink(missing_ok=True)
    flash(_("World Simulation imported.") + (" " + " ".join(_(n) for n in report["notes"]) if report["notes"] else ""), "success")
    return redirect(url_for("world_simulation.detail", fed_id=fed.id))


@world_simulation.route("/<int:fed_id>/clone", methods=["POST"])
@guarded
def clone(user, fed_id):
    from y_web.src.federation import lifecycle

    fed = _get_or_404(fed_id, user)
    try:
        new = lifecycle.clone(fed, request.form.get("name"), owner=user.username)
    except service.WorldSimulationError as exc:
        flash(_("The World Simulation could not be copied: %(why)s", why=str(exc)), "error")
        return redirect(url_for("world_simulation.detail", fed_id=fed.id))
    flash(_("World Simulation copied."), "success")
    return redirect(url_for("world_simulation.detail", fed_id=new.id))


@world_simulation.route("/<int:fed_id>/reset", methods=["POST"])
@guarded
def reset(user, fed_id):
    from y_web.src.federation import lifecycle

    fed = _get_or_404(fed_id, user)
    try:
        lifecycle.reset(fed)
        flash(_("World Simulation reset."), "success")
    except service.WorldSimulationError:
        flash(_("Stop the World Simulation before resetting it."), "error")
    return redirect(url_for("world_simulation.detail", fed_id=fed.id))


@world_simulation.route("/<int:fed_id>/delete", methods=["POST"])
@guarded
def delete(user, fed_id):
    fed = _get_or_404(fed_id, user)
    try:
        service.delete_federation(fed)
        flash(_("World Simulation deleted."), "success")
    except service.WorldSimulationError:
        flash(_("Stop the World Simulation before deleting it."), "error")
        return redirect(url_for("world_simulation.detail", fed_id=fed_id))
    return redirect(url_for("world_simulation.simulations"))


def _read_bus(fed):
    """Counters of the bus and the last events, read from the database of the coordinator (read only)."""
    path = Path(fed.folder) / "federation.db"
    out = {"messages": 0, "deliveries": 0, "events": []}
    if not path.is_file():
        return out
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            out["messages"] = conn.execute("SELECT COUNT(*) FROM federation_message").fetchone()[0]
            out["deliveries"] = conn.execute("SELECT COUNT(*) FROM federation_delivery").fetchone()[0]
            rows = conn.execute("SELECT tick, kind, detail_json FROM federation_event ORDER BY rowid DESC LIMIT 30").fetchall()
            out["events"] = [{"tick": t, "kind": k, "detail": d} for t, k, d in rows]
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return out


def _log_tail(fed, lines=40):
    path = Path(fed.folder) / "coordinator.log"
    try:
        return path.read_text(errors="replace").splitlines()[-lines:]
    except OSError:
        return []


@world_simulation.route("/<int:fed_id>/status.json")
@guarded
def status(user, fed_id):
    fed = _get_or_404(fed_id, user)
    coordinator = cp.coordinator_status(fed, timeout=1.5) if fed.status in ("running", "paused") else None
    waiting = cp.waiting_members(coordinator)
    members = []
    for row, exp in service.members_of(fed):
        live = ((coordinator or {}).get("members") or {}).get(row.member, {})
        members.append(
            {
                "member": row.member,
                "label": PLATFORM_LABELS.get(row.platform_type, row.platform_type),
                "experiment": exp.exp_name,
                "state": live.get("status"),
                "tick": live.get("last_ready_tick"),
                "waiting_for": waiting.get(row.member, []),
            }
        )
    return jsonify(
        {
            "state": fed.status,
            "global_tick": None if not coordinator else coordinator.get("global_tick"),
            "skew": None if not coordinator else coordinator.get("skew"),
            "coordinator_up": coordinator is not None,
            "members": members,
            "bus": _read_bus(fed),
            "log": _log_tail(fed),
        }
    )


@world_simulation.route("/<int:fed_id>/agents")
@guarded
def agents(user, fed_id):
    """Who is active on which platform: one row per agent or person, one state per platform (read from the coordinator)."""
    from y_web.src.federation import agent_states as ast

    fed = _get_or_404(fed_id, user)
    data = ast.table(fed)
    member, state = request.args.get("member", ""), request.args.get("state", "")
    kind, q = request.args.get("kind", ""), request.args.get("q", "")
    if member not in data["members"]:
        member = ""
    if state not in ast.STATES:
        state = ""
    if kind not in ("agent", "human"):
        kind = ""
    rows = ast.filtered(data, member, state, q, kind)
    page = max(1, request.args.get("page", 1, type=int) or 1)
    pages = max(1, -(-len(rows) // ast.PAGE_SIZE))
    page = min(page, pages)
    labels = {m.member: PLATFORM_LABELS.get(m.platform_type, m.platform_type) for m, _exp in service.members_of(fed)}
    return render_template(
        "admin/world_simulation/agents.html", row=_row(fed), members=data["members"], labels=labels, source=data["source"],
        rows=rows[(page - 1) * ast.PAGE_SIZE: page * ast.PAGE_SIZE], total=len(rows), page=page, pages=pages,
        counts=ast.counts(data), states=ast.STATES, f={"member": member, "state": state, "kind": kind, "q": q},
    )


@world_simulation.route("/<int:fed_id>/agents.csv")
@guarded
def agents_csv(user, fed_id):
    """Every account of the World Simulation with its state (one line per identity and platform)."""
    import csv
    import io

    from flask import Response

    from y_web.src.federation import agent_states as ast

    fed = _get_or_404(fed_id, user)
    data = ast.table(fed)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["global_agent_id", "name", "kind", "member", "account_id", "state", "joined_tick", "left_tick"])
    for r in data["rows"]:
        for m in data["members"]:
            c = r["states"].get(m)
            if c:
                writer.writerow([r["id"], r["name"], r["kind"], m, c["account"], c["state"], c["joined"] if c["joined"] is not None else "",
                                 c["left"] if c["left"] is not None else ""])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=world_simulation_{fed.id}_agents.csv"})


@world_simulation.route("/<int:fed_id>/analytics.json")
@guarded
def analytics_data(user, fed_id):
    """Derived analytics of one World Simulation (built on first use and when the run has moved on)."""
    from y_web.src.federation import analytics_etl, service

    fed = _get_or_404(fed_id, user)
    return jsonify(analytics_etl.cards(fed.folder, service.member_databases(fed)))


@world_simulation.route("/<int:fed_id>/analytics/rebuild", methods=["POST"])
@guarded
def analytics_rebuild(user, fed_id):
    """Manual recalculation of the derived analytics."""
    from y_web.src.federation import analytics_etl, service

    fed = _get_or_404(fed_id, user)
    result = analytics_etl.build(fed.folder, service.member_databases(fed))
    if not result["ok"]:
        flash(_("The analytics could not be recalculated: %(why)s", why=result["message"]), "warning")
    return redirect(url_for("world_simulation.detail", fed_id=fed.id) + "#analytics")


@world_simulation.route("/<int:fed_id>/analytics/<table>.csv")
@guarded
def analytics_csv(user, fed_id, table):
    """One derived table as CSV."""
    import csv
    import io

    from flask import Response

    from y_web.src.federation import analytics_etl, service

    fed = _get_or_404(fed_id, user)
    if table not in analytics_etl.EXPORT_TABLES:
        abort(404)
    analytics_etl.ensure_derived(fed.folder, service.member_databases(fed))
    if not Path(analytics_etl.analytics_path(fed.folder)).is_file():
        abort(404)
    columns, rows = analytics_etl.table_rows(fed.folder, table)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    writer.writerows(rows)
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=world_simulation_{fed.id}_{table}.csv"})


@world_simulation.route("/analytics")
@guarded
def analytics(user):
    return render_template("admin/world_simulation/analytics.html", rows=[_row(f) for f in _visible_federations(user)])


@world_simulation.route("/schedule")
@guarded
def schedule(user):
    from y_web.src.federation import schedule_queue

    visible = {f.id: f for f in _visible_federations(user)}
    entries = [(item, fed) for item, fed in schedule_queue.rows() if fed is not None and fed.id in visible]
    queued = {item.federation_id for item, _fed in entries if item.status in schedule_queue.OPEN_STATES}
    addable = [f for f in visible.values() if f.id not in queued and f.status in ("stopped", "completed", "failed")]
    return render_template(
        "admin/world_simulation/schedule.html", entries=entries, addable=addable, badges=STATE_BADGES
    )


@world_simulation.route("/schedule/enqueue", methods=["POST"])
@guarded
def schedule_enqueue(user):
    from y_web.src.federation import schedule_queue

    try:
        fed = _get_or_404(int(request.form.get("simulation_id", 0)), user)
        schedule_queue.enqueue(fed)
        flash(_("World Simulation added to the queue."), "success")
    except service.WorldSimulationError as exc:
        _flash_errors(exc)
    return redirect(url_for("world_simulation.schedule"))


@world_simulation.route("/schedule/<int:item_id>/cancel", methods=["POST"])
@guarded
def schedule_cancel(user, item_id):
    from y_web.src.federation import schedule_queue
    from y_web.src.models.admin import FederationScheduleQueue

    item = db.session.get(FederationScheduleQueue, item_id)
    if item is None:
        abort(404)
    _get_or_404(item.federation_id, user)
    if schedule_queue.cancel(item):
        flash(_("Removed from the queue."), "success")
    else:
        flash(_("Only a waiting World Simulation can be removed from the queue."), "error")
    return redirect(url_for("world_simulation.schedule"))


@world_simulation.record_once
def _start_schedule_monitor(state):
    """Start the queue monitor with the application (not in tests, not when switched off)."""
    app = state.app
    if app.config.get("TESTING") or app.config.get("WORLD_SIMULATION_MONITOR") is False:
        return
    from y_web.src.federation.schedule_monitor import init_federation_schedule_monitor

    init_federation_schedule_monitor(app)
