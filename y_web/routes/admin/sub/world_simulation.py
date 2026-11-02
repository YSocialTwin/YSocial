"""World Simulation routes (admin section "World Simulation", guide F5, D-12).

Pages: list of simulations, guided creation, detail with the Configuration and Execution tabs, analytics selection and
the schedule. In the interface the feature is always called "World Simulation"; in code it is the federation.
Only admins and researchers reach these routes (a researcher sees only the simulations they own).

The parameters are edited with explicit form fields (``y_web.src.federation.options_schema`` is the table of fields,
defaults and limits); the stored options keep every key the form does not cover."""

import json
import sqlite3
from pathlib import Path

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.federation import availability
from y_web.src.federation import coordinator_process as cp
from y_web.src.federation import frontends
from y_web.src.federation import member_health as mh
from y_web.src.federation import options_schema as schema
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
PLATFORM_ICONS = {
    "microblogging": "mdi-message-text-outline",
    "forum": "mdi-forum-outline",
    "photo_sharing": "mdi-image-multiple-outline",
    "instant_messaging": "mdi-chat-processing-outline",
    "dating": "mdi-heart-outline",
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
# Status pill of the experiments pages (``exp-tag``) plus one modifier per state, defined in admin-world-simulation.css.
STATE_CLASSES = {state: "ws-state-" + state for state in STATE_BADGES}
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
        if not availability.sdk_available():  # the optional YFederation plugin is missing: a friendly page, never a 500
            return _unavailable()
        return view(user, *args, **kwargs)

    return wrapper


def _unavailable():
    """The page (or the JSON answer) shown instead of the World Simulation when the YFederation plugin is not installed."""
    message = _("The YFederation plugin is not installed")
    if request.path.endswith(".json"):
        return jsonify({"error": message, "available": False}), 503
    return render_template("admin/world_simulation/unavailable.html", message=message, reason=availability.sdk_reason()), 503


def _label_of(row, exp, repeated):
    """The label of a member in the admin pages: its platform type, or the name of its experiment when the World Simulation has
    several members of that type (P15: a type no longer tells them apart)."""
    if repeated and exp is not None:
        return exp.exp_name
    return PLATFORM_LABELS.get(row.platform_type, row.platform_type)


def _member_labels(fed):
    pairs = service.members_of(fed)
    repeated = service.has_repeated_platform(pairs)
    return {m.member: _label_of(m, _exp, repeated) for m, _exp in pairs}


def _badge_text(code, waiting_for=(), labels=None):
    """The short text of the status badge of a member (OK / waiting for X / stalled / not running ...)."""
    labels = labels or {}
    if code == mh.WAITING:
        return _("Waiting for %(who)s", who=", ".join(labels.get(w, w) for w in waiting_for))
    return {
        mh.OK: lambda: _("OK"),
        mh.STARTING: lambda: _("Starting"),
        mh.MISSING: lambda: _("Missing"),
        mh.STALLED: lambda: _("Stalled"),
        mh.DEAD: lambda: _("Not running"),
        mh.FAILED: lambda: _("Failed"),
        mh.FINISHED: lambda: _("Finished"),
        mh.UNKNOWN: lambda: _("Unknown"),
    }.get(code, lambda: code)()


def _cause_text(cause):
    if not cause:
        return ""
    kind, name = cause.get("kind"), cause.get("name")
    if kind == "module":
        return _("Probable cause: Python module '%(name)s' not found", name=name)
    if kind == "import":
        return _("Probable cause: cannot import '%(name)s'", name=name)
    if kind == "port":
        return _("Probable cause: the port is already in use")
    if kind == "refused":
        return _("Probable cause: connection refused")
    if kind == "database":
        return _("Probable cause: database error")
    if kind == "memory":
        return _("Probable cause: out of memory")
    return _("Last error in the log: %(line)s", line=cause.get("line", ""))


def _problem_text(code, state, health):
    if code == mh.MISSING:
        return _("has not said hello %(s)s s after the start (limit %(limit)s s)", s=state.get("since") or 0, limit=health.get("hello_timeout"))
    if code == mh.STALLED:
        return _("has not advanced for %(s)s (limit %(limit)s)", s=mh.format_duration(state.get("since")), limit=mh.format_duration(health.get("stall_after")))
    if code == mh.DEAD:
        return _("is not running: %(what)s exited", what=", ".join(state.get("dead") or []) or _("its process"))
    if code == mh.FAILED:
        return _("reported a failure to the coordinator")
    return ""


def _problems_from(health, labels):
    """``[{member, label, code, text, cause, log}]`` of the members in trouble, texts in the language of the request."""
    out = []
    for name in (health or {}).get("problems", []):
        state = health["members"][name]
        out.append({"member": name, "label": labels.get(name, name), "code": state["code"],
                    "text": _problem_text(state["code"], state, health), "cause": _cause_text(state.get("cause")),
                    "log": state.get("log", "")})
    return out


def _hints_from(health, labels):
    """Entries like those of ``_problems_from`` for the members that advance without any agent acting (a hint)."""
    out = []
    for name, info in sorted(((health or {}).get("silent") or {}).items()):
        out.append({"member": name, "label": labels.get(name, name), "code": "silent",
                    "text": _("advances but its server received no post, comment or reaction for %(n)s ticks (last one at tick %(last)s)",
                              n=info["ticks"], last=info["last_action_tick"]),
                    "cause": _("Check that the clients of this member sample agents (see the warnings in the client log)."),
                    "log": ""})
    return out


def _problem_lines(fed, coordinator):
    try:
        return _problems_from(mh.collect(fed, coordinator), _member_labels(fed))
    except Exception:  # noqa: BLE001 - a warning is never worth an error page
        return []


def _progress_text(progress):
    """``Tick 3/720, ~65 s per tick, ETA 13 h`` (the parts not known yet are left out)."""
    if not progress or not progress.get("tick"):
        return ""
    parts = [_("Tick %(done)s/%(total)s", done=progress["tick"], total=progress["total"]) if progress.get("total")
             else _("Tick %(done)s", done=progress["tick"])]
    if progress.get("seconds_per_tick"):
        parts.append(_("~%(t)s per tick", t=mh.format_duration(progress["seconds_per_tick"])))
    if progress.get("eta_seconds") is not None:
        parts.append(_("ETA %(eta)s", eta=mh.format_duration(progress["eta_seconds"])))
    return ", ".join(parts)


def _row(fed):
    members = service.members_of(fed)
    repeated = service.has_repeated_platform(members)
    status = cp.coordinator_status(fed, timeout=1.0) if fed.status in ("running", "paused") else None
    return {
        "fed": fed,
        "badge": STATE_BADGES.get(fed.status, "badge-secondary"),
        "state_class": STATE_CLASSES.get(fed.status, "ws-state-stopped"),
        "members": [(m.member, _label_of(m, exp, repeated), exp) for m, exp in members],
        "member_rows": [
            {"member": m.member, "label": _label_of(m, exp, repeated),
             "icon": PLATFORM_ICONS.get(m.platform_type, "mdi-web"), "exp": exp, "simulator": getattr(exp, "simulator_type", "") or "Standard"}
            for m, exp in members
        ],
        "tick": None if not status else status.get("global_tick"),
        "problems": _problem_lines(fed, status) if status is not None else [],
    }


@world_simulation.route("", strict_slashes=False)
@guarded
def simulations(user):
    rows = [_row(f) for f in _visible_federations(user)]
    counts = {"total": len(rows), "running": sum(1 for r in rows if r["fed"].status in ("running", "paused", "starting")),
              "stopped": sum(1 for r in rows if r["fed"].status in ("stopped", "completed", "failed"))}
    return render_template("admin/world_simulation/list.html", rows=rows, counts=counts)


_BLOCKING = ("experiment_running", "clock", "simulator_type", "platform", "already_member", "remote")


def _candidates(user):
    """The experiments that can be chosen, with their populations and what keeps one from being chosen."""
    from y_web.src.models.admin import Agent_Population, Population, Population_Experiment

    exps = get_visible_experiment_query(user).filter(Exps.is_remote == 0).order_by(Exps.exp_name).all()
    out = []
    for exp in exps:
        info = service.collect_member_info(exp)
        problems = [e for e in service.validate_members([info]) if e["code"] in _BLOCKING]
        pops = []
        for link in Population_Experiment.query.filter_by(id_exp=exp.idexp).all():
            pop = db.session.get(Population, link.id_population)
            if pop is not None:
                agents = Agent_Population.query.filter_by(population_id=pop.id).count()
                pops.append({"name": pop.name, "agents": agents})
        out.append({"exp": exp, "key": f"{exp.platform_type}-{exp.idexp}", "platform_type": exp.platform_type, "platform": PLATFORM_LABELS.get(exp.platform_type, exp.platform_type),
                    "icon": PLATFORM_ICONS.get(exp.platform_type, "mdi-web"), "info": info, "populations": pops,
                    "problems": [p["code"] for p in problems]})
    return out


def _grouped_candidates(candidates):
    """Candidates by platform, in the order of the platforms (one card for each)."""
    groups = []
    for platform in schema.PLATFORMS:
        items = [c for c in candidates if c["platform_type"] == platform]
        groups.append({"platform_type": platform, "label": PLATFORM_LABELS[platform], "icon": PLATFORM_ICONS[platform], "experiments": items})
    return groups


def _options_from_form(form, base=None, members=None):
    """The options a submitted form describes, over the stored ones ``base`` (keys the form does not cover are kept)."""
    options, errors = schema.apply_form(form, base, members)
    if errors:
        raise service.WorldSimulationError([{"code": "options", "message": message} for message in errors])
    return options


def _form_context(values, members=None, labels=None):
    """What ``_options_form.html`` needs: the schema, the values to show and the members the matrices are for.

    ``members`` are member names (or, in the creation form, the keys of the candidate experiments), in order; ``labels`` maps each to
    what a person reads (the name of its experiment). Without them every platform type is offered, as before P15."""
    keys = [m for m in schema.PLATFORMS] if members is None else list(members)
    return {
        "schema": schema,
        "values": values,
        "ws_platforms": keys,
        "ws_labels": {k: (labels or {}).get(k) or PLATFORM_LABELS.get(k, k) for k in keys},
        "ws_platform_types": [t for t in schema.PLATFORMS if t in set(_types_of(keys).values())],
        "platform_labels": PLATFORM_LABELS,
        "platform_icons": PLATFORM_ICONS,
    }


def _types_of(keys):
    """{key: platform type} of member names / candidate keys: the type is the name up to the last ``-<number>``."""
    out = {}
    for k in keys:
        base, _dash, tail = str(k).rpartition("-")
        out[k] = base if base and tail.isdigit() else k
    return out


ERROR_TEXT = {
    "member_count": lambda: _("A World Simulation needs 2 to 8 experiments."),
    "experiment_running": lambda: _("An experiment is running: stop it first."),
    "remote": lambda: _("Remote experiments cannot take part in a World Simulation."),
    "population": lambda: _("All experiments must use the same population."),
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
    "sdk_missing": lambda: _("The YFederation plugin is not installed."),
    "sdk_not_importable": lambda: _("The servers and clients of the members cannot import the YFederation plugin."),
}


def _flash_errors(error):
    for item in error.errors:
        text = ERROR_TEXT.get(item["code"])
        message = "%s (%s)" % (text(), item["message"]) if text else item["message"]
        flash(message, "error")


def _translate_form(form, keymap):
    """The creation form speaks of candidate experiments (``<platform>-<experiment id>``, known before anything is chosen); the
    World Simulation is made of members whose names depend on the choice (service.member_names). The pair and start fields are
    renamed from the first to the second; fields of experiments that were not chosen are left out by ``apply_form``."""
    from werkzeug.datastructures import MultiDict

    out = MultiDict()
    for key, value in form.items(multi=True):
        if key.startswith("prob__"):
            parts = key.split("__")
            if len(parts) == 3:
                key = f"prob__{keymap.get(parts[1], parts[1])}__{keymap.get(parts[2], parts[2])}"
        elif key.startswith("membership_p__"):
            key = "membership_p__" + keymap.get(key.split("__", 1)[1], key.split("__", 1)[1])
        out.add(key, value)
    return out


@world_simulation.route("/new", methods=["GET", "POST"])
@guarded
def new(user):
    form = request.form
    if request.method == "POST":
        try:
            seed = form.get("seed", "").strip()
            chosen = [int(i) for i in form.getlist("experiments")]
            picked = [e for e in (db.session.get(Exps, i) for i in chosen) if e is not None]
            names = service.member_names(picked)
            keymap = {f"{e.platform_type}-{e.idexp}": names[e.idexp] for e in picked}
            platforms = set(names.values())
            fed = service.create_federation(
                form.get("name"),
                chosen,
                owner=user.username,
                seed=int(seed) if seed else None,
                granularity=form.get("granularity", "slot"),
                options=_options_from_form(_translate_form(form, keymap), members=platforms),
                exposures=bool(form.get("discovery_enabled")),
            )
            flash(_("World Simulation created."), "success")
            return redirect(url_for("world_simulation.detail", fed_id=fed.id))
        except service.WorldSimulationError as exc:
            _flash_errors(exc)
        except ValueError:
            flash(_("The seed must be an integer."), "error")
    candidates = _candidates(user)
    offered = [c for c in candidates if not c["problems"]]  # the matrices have a row for each experiment that can be chosen
    keys = [c["key"] for c in offered]
    values = schema.values_from_form(form) if request.method == "POST" else schema.values_from_options({}, keys)
    return render_template("admin/world_simulation/new.html", candidates=candidates, groups=_grouped_candidates(candidates), form=form,
                           **_form_context(values, keys, {c["key"]: c["exp"].exp_name for c in offered}))


def _stored_options(fed):
    """The stored options without ``exposures`` (it follows the discovery switch)."""
    return {k: v for k, v in json.loads(fed.config_json or "{}").items() if k != "exposures"}


def _config_preview(fed):
    """The saved ``federation.json`` as text for the read-only preview (the long identity list is summarised)."""
    try:
        config = service.build_federation_config(fed)
    except Exception as exc:  # noqa: BLE001 - the preview must never stop the page
        return _("The file cannot be generated: %(error)s", error=str(exc))
    identity = config.pop("identity", [])
    config["identity"] = _("%(n)s accounts (not listed)", n=len(identity))
    return json.dumps(config, indent=2, sort_keys=False)


@world_simulation.route("/<int:fed_id>")
@guarded
def detail(user, fed_id):
    fed = _get_or_404(fed_id, user)
    options = json.loads(fed.config_json or "{}")
    row = _row(fed)
    pairs = service.members_of(fed)
    members = {m.member for m, _exp in pairs}
    return render_template(
        "admin/world_simulation/detail.html",
        row=row,
        frontends=frontends.frontend_rows(fed, user),
        crosspost_warning=schema.crosspost_warning(schema.crosspost_causes_from_options(options, members)),
        participants=_participants(fed),
        candidates_users=db.session.scalars(select(Admin_users).order_by(Admin_users.username)).all(),
        options=options,
        crosspost_content=service.crosspost_content_of(options),
        unknown=schema.unknown_paths(options),
        config_preview=_config_preview(fed),
        editable=fed.status in ("stopped", "completed", "failed"),
        **_form_context(schema.values_from_options(options, [m.member for m, _exp in pairs]), [m.member for m, _exp in pairs],
                        {m.member: _exp.exp_name for m, _exp in pairs}),
    )


def _participants(fed):
    """The people enrolled: ``[(user, status, [(member label, account id, created)])]`` for the Configuration tab."""
    from y_web.src.federation import humans

    labels = _member_labels(fed)
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
        members = {m.member for m, _exp in service.members_of(fed)}
        stored = _stored_options(fed)
        options = _options_from_form(request.form, base=stored, members=members)
        kept = {k: v for k, v in options.items() if k in stored and k not in service.OPTION_BLOCKS}  # blocks of another release stay
        options = {**service._clean_options({k: v for k, v in options.items() if k not in kept}), **kept}
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
            eb.start_federation(fed, admin_user=user)
            flash(_("World Simulation started."), "success")
            for message in getattr(fed, "frontend_warnings", None) or []:
                flash(_("Web interface not activated: %(reason)s", reason=message), "warning")
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


def _frontends_command(fed_id, user, activating):
    """Activate or deactivate the web interface of every member (allowed in any state of the World Simulation)."""
    fed = _get_or_404(fed_id, user)
    try:
        outcomes = (frontends.activate_frontends if activating else frontends.deactivate_frontends)(fed, user)
    except Exception as exc:  # noqa: BLE001 - reported, never a 500
        db.session.rollback()
        outcomes = []
        problems = [_("The web interfaces could not be changed: %(error)s", error=str(exc))]
    else:
        problems = frontends.warnings_of(outcomes)
    summary = frontends.summary(outcomes, activating) if outcomes else None
    wants_json = request.accept_mimetypes.best == "application/json" or request.is_json
    if wants_json:
        return jsonify({"ok": not problems, "message": summary, "problems": problems, "members": outcomes,
                        "frontends": frontends.frontend_rows(fed, user)}), (200 if not problems else 207)
    if summary:
        flash(summary, "success")
    for message in problems:
        flash(message, "error")
    return redirect(url_for("world_simulation.detail", fed_id=fed.id) + "#execution")


@world_simulation.route("/<int:fed_id>/frontends/activate", methods=["POST"])
@guarded
def frontends_activate(user, fed_id):
    return _frontends_command(fed_id, user, True)


@world_simulation.route("/<int:fed_id>/frontends/deactivate", methods=["POST"])
@guarded
def frontends_deactivate(user, fed_id):
    return _frontends_command(fed_id, user, False)


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
    out = {"messages": 0, "deliveries": 0, "events": [], "by_type": {}, "crosspost_ticks": 0, "crosspost_total": 0, "crosspost_pairs": {}, "crosspost_delivered": 0, "available": False}
    if not path.is_file():
        return out
    out["available"] = True
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            for kind, n in conn.execute("SELECT payload_type, COUNT(*) FROM federation_message GROUP BY payload_type").fetchall():
                out["by_type"][kind] = n  # one pass: the total and the exported content come from the same scan
            out["messages"] = sum(out["by_type"].values())
            _read_crossposts(conn, out)
            _read_agent_crossposts(conn, out)
            out["deliveries"] = conn.execute("SELECT COUNT(*) FROM federation_delivery").fetchone()[0]
            rows = conn.execute("SELECT tick, kind, detail_json FROM federation_event ORDER BY rowid DESC LIMIT 30").fetchall()
            out["events"] = [{"tick": t, "kind": k, "detail": d} for t, k, d in rows]
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return out


def _read_crossposts(conn, out, limit=20000):
    """Ticks with at least one cross-post and their total, from the ``crosspost_materialized`` events (one per tick, bounded)."""
    try:
        for (detail,) in conn.execute("SELECT detail_json FROM federation_event WHERE kind='crosspost_materialized' "
                                      "ORDER BY id DESC LIMIT ?", (limit,)):
            try:
                n = int(json.loads(detail).get("crossposts", 0))
            except (TypeError, ValueError, AttributeError):
                continue
            if n > 0:
                out["crosspost_ticks"] += 1
                out["crosspost_total"] += n
    except sqlite3.Error:
        pass  # no event table yet: counted as none


def _read_agent_crossposts(conn, out):
    """``crosspost.v1`` messages (what the members emit with ``crosspost.mode = agent_action``) by origin and destination, and
    how many of them have been delivered (read only, tolerant of missing tables)."""
    try:
        for source, target, n in conn.execute("SELECT source_member, target_member, COUNT(*) FROM federation_message "
                                              "WHERE payload_type = 'crosspost.v1' GROUP BY source_member, target_member"):
            out["crosspost_pairs"][f"{source}>{target}"] = n
        out["crosspost_delivered"] = conn.execute(
            "SELECT COUNT(*) FROM federation_delivery d JOIN federation_message m ON m.fed_msg_id = d.fed_msg_id "
            "WHERE m.payload_type = 'crosspost.v1'").fetchone()[0]
    except sqlite3.Error:
        pass


# the hint of the Execution tab appears once the run is past this tick with nothing exported and nothing materialised
CROSSPOST_HINT_AFTER_TICK = 6


def _crosspost_status(fed, bus, tick):
    """Text of the Cross-posts line and, when the run is past tick 6 with none, the hint with the probable cause.

    The line follows the mode: with ``agent_action`` the members emit ``crosspost.v1`` messages (counted by direction, with
    the deliveries); with ``coordinator_rule`` the coordinator marks ``content.v1`` and materialises it."""
    if not bus.get("available"):
        return {"exported": 0, "ticks": 0, "total": 0, "text": None, "hint": None}
    options = json.loads(fed.config_json or "{}")
    mode = (options.get("crosspost") or {}).get("mode") or "coordinator_rule"
    total, ticks = bus["crosspost_total"], bus["crosspost_ticks"]
    exported = bus["by_type"].get("content.v1", 0)
    if mode == "agent_action":
        pairs = bus.get("crosspost_pairs") or {}
        sent = sum(pairs.values())
        label = lambda m: str(m).replace("_", " ")  # noqa: E731
        directions = ", ".join(f"{label(k.split('>')[0])} → {label(k.split('>')[1])}: {n}" for k, n in sorted(pairs.items())) or "-"
        text = _("Cross-posts: %(sent)s sent by the agents (%(directions)s) · delivered: %(delivered)s", sent=sent,
                 directions=directions, delivered=bus.get("crosspost_delivered", 0))
        none = sent == 0
    else:
        text = _("Cross-posts: %(total)s materialised (in %(ticks)s ticks) · content exported: %(exported)s", total=total, ticks=ticks, exported=exported)
        none = exported == 0 and total == 0
    hint = None
    if fed.status in ("running", "paused") and tick is not None and tick > CROSSPOST_HINT_AFTER_TICK and none:
        members = {m.member for m, _exp in service.members_of(fed)}
        cause = schema.crosspost_warning(schema.crosspost_causes_from_options(options, members))
        hint = _("No content has been marked for cross-posting after %(tick)s ticks.", tick=tick) + " " + (
            cause or _("Check that the agents are posting and that the content filter lets their posts through."))
    return {"exported": exported, "ticks": ticks, "total": total, "sent": sum((bus.get("crosspost_pairs") or {}).values()),
            "delivered": bus.get("crosspost_delivered", 0), "mode": mode, "text": text, "hint": hint}


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
    try:
        health = mh.collect(fed, coordinator)  # {} unless running; cheap: three bounded reads and a few pid checks
    except Exception:  # noqa: BLE001 - the page keeps working without the warnings
        health = {}
    states = health.get("members", {})
    labels = _member_labels(fed)
    repeated = service.has_repeated_platform(service.members_of(fed))
    members = []
    for row, exp in service.members_of(fed):
        live = ((coordinator or {}).get("members") or {}).get(row.member, {})
        hs = states.get(row.member)
        members.append(
            {
                "member": row.member,
                "label": _label_of(row, exp, repeated),
                "experiment": exp.exp_name,
                "state": live.get("status"),
                "tick": live.get("last_ready_tick"),
                "waiting_for": waiting.get(row.member, []),
                "health": None if hs is None else {"code": hs["code"], "problem": hs["problem"],
                                                  "text": _badge_text(hs["code"], hs["waiting_for"], labels)},
            }
        )
    progress = health.get("progress")
    bus = _read_bus(fed)
    crossposts = _crosspost_status(fed, bus, None if not coordinator else coordinator.get("global_tick"))
    return jsonify(
        {
            "state": fed.status,
            "global_tick": None if not coordinator else coordinator.get("global_tick"),
            "skew": None if not coordinator else coordinator.get("skew"),
            "coordinator_up": coordinator is not None,
            "members": members,
            "problems": _problems_from(health, labels) + _hints_from(health, labels),
            "progress": progress,
            "progress_text": _progress_text(progress),
            "log_hint": _("The logs are in the folder of each experiment (server_stderr.log and <client>_client_stderr.log)."),
            "bus": bus,
            "crossposts": crossposts,
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
    activity = request.args.get("activity", "")
    sort, direction = request.args.get("sort", "name"), request.args.get("dir", "")
    if member not in data["members"]:
        member = ""
    if state not in ast.STATES:
        state = ""
    if kind not in ("agent", "human"):
        kind = ""
    if activity not in ast.ACTIVITIES:
        activity = ""
    if sort not in ast.SORTS:
        sort = "name"
    if direction not in ("asc", "desc"):
        direction = ""
    rows = ast.sorted_rows(ast.filtered(data, member, state, q, kind, activity), sort, direction)
    page = max(1, request.args.get("page", 1, type=int) or 1)
    pages = max(1, -(-len(rows) // ast.PAGE_SIZE))
    page = min(page, pages)
    labels = _member_labels(fed)
    f = {"member": member, "state": state, "kind": kind, "q": q, "activity": activity, "sort": sort, "dir": direction}
    effective = direction or ast.default_direction(sort)

    def sort_url(column):
        """Address of the table sorted by ``column``: the same filters, the opposite direction when it is already the sort."""
        flip = "asc" if effective == "desc" else "desc"
        args = {**f, "sort": column, "dir": flip if column == sort else ast.default_direction(column)}
        return url_for("world_simulation.agents", fed_id=fed.id, **{k: v for k, v in args.items() if v})

    return render_template(
        "admin/world_simulation/agents.html", row=_row(fed), members=data["members"], labels=labels, source=data["source"],
        rows=rows[(page - 1) * ast.PAGE_SIZE: page * ast.PAGE_SIZE], total=len(rows), page=page, pages=pages,
        counts=ast.counts(data), states=ast.STATES, platform_icons=PLATFORM_ICONS, f=f, names=data["names"],
        stats_available=data["stats_available"], activities=ast.ACTIVITIES, sort_url=sort_url, sort=sort, direction=effective,
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
    writer.writerow(["global_agent_id", "name", "kind", "member", "account_id", "state", "joined_tick", "left_tick",
                     "crossposts_own", "crossposts_of_others", "times_crossposted", "times_crossposted_by_destination"])
    for r in data["rows"]:
        st = r["stats"]  # the same numbers on every line of the identity: made (own, of others) and delivered copies of its content
        by_dest = "; ".join(f"{data['names'].get(m, m)}: {n}" for m, n in sorted(st["by_dest"].items()))
        for m in data["members"]:
            c = r["states"].get(m)
            if c:
                writer.writerow([r["id"], r["name"], r["kind"], m, c["account"], c["state"],
                                 c["joined"] if c["joined"] is not None else "", c["left"] if c["left"] is not None else "",
                                 st["made_own"], st["made_others"], st["times"], by_dest])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=world_simulation_{fed.id}_agents.csv"})


@world_simulation.route("/<int:fed_id>/crossposts")
@guarded
def crossposts(user, fed_id):
    """Cross-posted contents: one row per content copied to a destination, searchable and paged on the server (GET parameters)."""
    from y_web.src.federation import crossposts as cps

    fed = _get_or_404(fed_id, user)
    members = service.members_of(fed)
    f = cps.parse_filters(request.args, [m.member for m, _exp in members])
    result = cps.search(fed, f)
    pages = max(1, -(-min(result["total"], cps.MAX_OFFSET + f["size"]) // f["size"]))
    f["page"] = min(f["page"], pages)
    if result["total"] and not result["rows"] and f["page"] != request.args.get("page", 1, type=int):
        result = cps.search(fed, f)

    def page_url(page=None, **over):
        args = cps.query_args(f, **over)
        if page and page > 1:
            args["page"] = page
        return url_for("world_simulation.crossposts", fed_id=fed.id, **args)

    return render_template(
        "admin/world_simulation/crossposts.html", row=_row(fed), f=f, rows=result["rows"], total=result["total"], capped=result["capped"],
        available=result["available"], page=f["page"], pages=pages, page_sizes=cps.PAGE_SIZES, page_url=page_url,
        platform_icons=PLATFORM_ICONS, statuses=cps.STATUSES, modes=cps.MODES,
        member_options=[(m.member, exp.exp_name if exp is not None else m.member) for m, exp in members],
        export_args=cps.query_args(f), slots_per_day=cps.SLOTS_PER_DAY,
    )


@world_simulation.route("/<int:fed_id>/crossposts.csv")
@guarded
def crossposts_csv(user, fed_id):
    """The cross-posted contents that match the same filters as the page, as CSV (bounded to ``EXPORT_MAX`` rows)."""
    import csv
    import io

    from flask import Response

    from y_web.src.federation import crossposts as cps

    fed = _get_or_404(fed_id, user)
    f = cps.parse_filters(request.args, [m.member for m, _exp in service.members_of(fed)])
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(cps.CSV_COLUMNS)
    for r in cps.export_rows(fed, f):
        writer.writerow(cps.csv_row(r))
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=world_simulation_{fed.id}_crossposts.csv"})


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
