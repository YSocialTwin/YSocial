"""Instant messaging observer frontend (plan, 6.2, 6.3): chats of an IM experiment, read only.

All routes carry ``<int:exp_id>`` so the experiment context and access guards apply; none of them binds
``db_exp`` (the IM database is opened by ``y_web.src.im.engine`` in read-only mode, plan 4.1). Three
viewpoints: ``public`` (all roles), ``account`` and ``overview`` (admin and researcher only).
"""

import os
import uuid
from urllib.parse import urlencode

from flask import abort, jsonify, redirect, render_template, request, session as flask_session, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.routes.social._blueprint import main
from y_web.src.im import is_im_experiment
from y_web.src.im.engine import ImReadError, open_reader
from y_web.src.im.reader import Reader, Viewpoint, ViewpointError, avatar_hue, latest_round, status
from y_web.src.im.timeline import clamp_round, day_slot, ordinal
from y_web.src.im import participant as participation
from y_web.src.im.gateway_client import GatewayClient, GatewayUnavailable
from y_web.src.im.gateway_process import is_running as gateway_running
from y_web.src.models import Exps, User_Experiment

POLL_SECONDS = 10  # used when the experiment's own setting is missing


def _ui(exp_id):
    from y_web.routes.social.helpers import _load_ui_settings

    return _load_ui_settings(exp_id)


def _poll_seconds(ui):
    try:
        return max(1, min(60, int(ui.get("im_participant_poll_seconds", POLL_SECONDS))))
    except (TypeError, ValueError):
        return POLL_SECONDS


def _page_size(ui):
    try:
        return max(1, min(100, int(ui.get("posts_per_page", 30))))
    except (TypeError, ValueError):
        return 30


def _staff_user():
    """The admin or researcher behind the session, or ``None`` (participants and anyone else)."""
    from y_web.routes.admin.sub.experiments._helpers import _current_admin_user_or_none

    user = _current_admin_user_or_none()
    return user if user is not None and getattr(user, "role", None) in ("admin", "researcher") else None


def _experiment_or_404(exp_id):
    exp = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
    if exp is None or not is_im_experiment(exp):
        abort(404)
    return exp


def _db_path(exp) -> str:
    from y_web.src.system.path_utils import get_writable_path

    parts = exp.db_name.split(os.sep)
    return os.path.join(get_writable_path(), "y_web", "experiments", parts[1], "database_server.db")


class _Context:
    """What every page needs: experiment, viewpoint, round and the query string that keeps them."""

    def __init__(self, exp, staff, viewpoint, latest, live, ui=None, participant=None):
        self.exp, self.staff, self.vp, self.latest, self.live = exp, staff, viewpoint, latest, live
        self.ui = ui or {}
        self.participant = participant  # set in participant mode (plan 6.8); never from the request
        self.pending_account = False  # participation is on but the account does not exist yet
        self.reader = None  # set by ``_view``: the sidebar of every page lists the chats of the viewpoint
        self.session = None

    @property
    def writable(self):
        """A participant can write while the run is live and the gateway answers."""
        return bool(
            self.participant
            and self.live
            and self.latest
            and gateway_running(self.participant.exp_folder)
        )

    @property
    def params(self):
        out = {"vp": self.vp.kind}
        if self.vp.kind == "account":
            out["acc"] = self.vp.account_id
        if self.vp.round != self.latest:
            out["round"] = self.vp.round
        return out

    def day_slot(self):
        return day_slot(self.vp.round) if self.vp.round else (0, 0)


def _open_context(session, exp_id):
    """Resolve experiment, access and viewpoint for the request; aborts with 404/403 when not allowed."""
    from y_web.src.experiment.access import user_can_view_experiment

    exp = _experiment_or_404(exp_id)
    staff = _staff_user()
    if staff is not None and not user_can_view_experiment(staff, exp):
        abort(403)
    ui = _ui(exp_id)
    part = _participant(session, exp, ui) if staff is None else None
    if part is not None and part is not False:
        return _participant_context(session, exp, ui, part)
    pending = part is False  # participation is on, the account is not there yet
    if staff is None and not ui.get("im_public_observer_enabled", True) and not pending:
        abort(403)  # the researcher closed the public pages of this experiment
    kind = request.args.get("vp") or ("overview" if staff is not None else "public")
    if kind != "public" and staff is None:
        abort(403)  # participants see the public observer view only
    latest = latest_round(session)
    requested = request.args.get("round")
    time_travel = staff is not None or ui.get("im_allow_time_travel", True)
    if not time_travel:
        requested = None
    elif request.args.get("day") and request.args.get("slot"):
        try:
            requested = ordinal(int(request.args["day"]), int(request.args["slot"]))
        except ValueError:
            abort(400)
    rnd = clamp_round(requested, latest)
    try:
        viewpoint = Viewpoint(kind, request.args.get("acc") or None, rnd)
    except ViewpointError:
        abort(400)
    ctx = _Context(exp, staff, viewpoint, latest, bool(exp.running), ui)
    ctx.pending_account = pending
    return ctx


class _Redirect(Exception):
    def __init__(self, url):
        self.url = url


def _participant(session, exp, ui):
    """The participant behind the session: a ``Participant``, ``False`` (account not created yet), or ``None``."""
    user = current_user if current_user.is_authenticated else None
    if user is None:
        return None
    assigned = (
        db.session.scalars(
            select(User_Experiment).filter_by(user_id=user.id, exp_id=exp.idexp)
        ).first()
        is not None
    )
    part = participation.participant_for(exp, user, ui, assigned)
    if part is None:
        return None
    from y_web.src.im.engine import im_modules

    models = im_modules()[0]
    if session.get(models.Account, part.account_id) is not None:
        return part
    try:  # first entry: the account is created through the gateway (never by YWeb)
        code, _body = GatewayClient(part.exp_folder).ensure(
            part.key, participation.pseudonym(user)
        )
    except GatewayUnavailable:
        return False
    if code != 200:
        return False
    session.rollback()  # end the read snapshot so the new row is visible
    return part if session.get(models.Account, part.account_id) is not None else False


def _participant_context(session, exp, ui, part):
    from y_web.src.im.reader import Viewpoint

    notice = (ui.get("im_participant_notice") or "").strip()
    ack_key = participation.NOTICE_SESSION_PREFIX + str(exp.idexp)
    if notice and not flask_session.get(ack_key) and request.endpoint != "main.im_notice":
        raise _Redirect(url_for("main.im_notice", exp_id=exp.idexp))
    latest = latest_round(session)
    viewpoint = Viewpoint("account", part.account_id, latest)  # fixed: no time travel, no other account
    return _Context(exp, None, viewpoint, latest, bool(exp.running), ui, participant=part)


def _annotation_flags(ctx):
    """Which annotation chips a page shows: staff see every one, the others what the experiment switches on."""
    ui = ctx.ui
    master = ctx.staff is not None or bool(ui.get("annotations_enabled", True))
    return {
        "topics": master and (ctx.staff is not None or bool(ui.get("annotation_topics", True))),
        "sentiment": master and (ctx.staff is not None or bool(ui.get("annotation_sentiment", True))),
        "toxicity": master and (ctx.staff is not None or bool(ui.get("annotation_toxicity", True))),
        "emotion": master and (ctx.staff is not None or bool(ui.get("annotation_emotions", True))),
    }


def _shell(ctx, values):
    """Context of the three-pane shell: the chats of the viewpoint, the staff menu and the viewed account."""
    out = {}
    chats = values.get("chats")
    if chats is None and ctx.reader is not None:
        try:
            chats = ctx.reader.chat_list()
        except ImReadError:
            chats = []
    out["sidebar_chats"] = chats or []
    accounts = values.get("accounts")
    if accounts is None and ctx.staff is not None and ctx.session is not None:
        accounts = _accounts_for_picker(ctx.session)
    out["accounts"] = accounts or []
    viewed = None
    if ctx.vp.kind == "account":
        viewed = next((a for a in out["accounts"] if a["id"] == ctx.vp.account_id), None) or {
            "id": ctx.vp.account_id,
            "username": ctx.vp.account_id,
            "kind": None,
            "hue": avatar_hue(ctx.vp.account_id),
        }
        if ctx.participant is not None:
            viewed = None  # a participant is not "viewing as" anyone
    out["viewed_account"] = viewed
    out["annotation_flags"] = _annotation_flags(ctx)
    out["admin_links"] = [(_("Dashboard"), "/admin/dashboard")] if ctx.staff is not None else []
    return out


def _render(template, ctx, **values):
    shell = _shell(ctx, values)
    values.pop("accounts", None)
    values.pop("chats", None)
    return render_template(
        template,
        exp=ctx.exp,
        ctx=ctx,
        params=ctx.params,
        is_staff=ctx.staff is not None,
        day_slot=ctx.day_slot(),
        poll_seconds=_poll_seconds(ctx.ui) if (ctx.live and ctx.vp.round == ctx.latest) else 0,
        ui=ctx.ui,
        time_travel=ctx.participant is None
        and (ctx.staff is not None or bool(ctx.ui.get("im_allow_time_travel", True))),
        platform_ui="im",
        frontend_adds_on_modules=[],  # no frontend plugin module attaches to the chat pages
        participant=ctx.participant,
        writable=ctx.writable,
        pending_account=ctx.pending_account,
        csrf_token=participation.csrf_token(flask_session) if ctx.participant else "",
        **shell,
        **values,
    )


def _unavailable(exp, message, code=503):
    return render_template("im/unavailable.html", exp=exp, message=message), code


def _view(exp_id, handler):
    """Run ``handler(session, ctx, reader)`` on a read-only session; unreadable databases get a plain page."""
    exp = _experiment_or_404(exp_id)
    try:
        with open_reader(_db_path(exp)) as session:
            ctx = _open_context(session, exp_id)
            ctx.session = session
            ctx.reader = Reader(session, ctx.vp)
            return handler(session, ctx, ctx.reader)
    except _Redirect as redirect_to:
        return redirect(redirect_to.url)
    except ViewpointError:
        abort(400)
    except ImReadError as exc:
        return _unavailable(exp, str(exc))


def _accounts_for_picker(session):
    from y_web.src.im.engine import im_modules

    models = im_modules()[0]
    return [
        {"id": row.id, "username": row.username, "kind": row.kind, "hue": avatar_hue(row.id)}
        for row in session.scalars(select(models.Account).order_by(models.Account.username))
    ]


def _record_exposure(ctx, chat_id, page):
    """Tell the server what a participant is being shown, so human reads are exposures like the agents' ones.

    The pages read the database; the exposure goes through the gateway, which applies the same visibility checks
    as ``read_chat``. A gateway that does not answer never breaks the page.
    """
    part = ctx.participant
    if not part or not page or not ctx.live:
        return
    ids = [item["id"] for item in page.get("items", []) if not item.get("deleted")][:200]
    if not ids:
        return
    try:
        GatewayClient(part.exp_folder).exposures(
            part.account_id,
            chat_id,
            ids,
            participation.exposure_request_id(part.account_id, ctx.latest, chat_id),
        )
    except GatewayUnavailable:
        pass


def _info(rd, chat_id):
    """The info panel of a chat: its facts and members."""
    return {"info": rd.chat_info(chat_id), "members": rd.members(chat_id) or []}


def _history(rd, ctx, chat_id, forum_topic_id=None):
    """One page of a chat, sized and opened where the experiment's settings say."""
    before = request.args.get("before") or None
    after = request.args.get("after") or None
    from_start = before is None and after is None and ctx.ui.get("im_default_view") == "start"
    return rd.history(
        chat_id,
        before=before,
        after=after,
        from_start=from_start,
        limit=_page_size(ctx.ui),
        forum_topic_id=forum_topic_id,
    )


@main.route("/<int:exp_id>/im")
@login_required
def im_index(exp_id):
    def handler(session, ctx, rd):
        return _render("im/index.html", ctx)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/im/chat/<chat_id>")
@login_required
def im_chat(exp_id, chat_id):
    def handler(session, ctx, rd):
        page = _history(rd, ctx, chat_id)
        if page is None:
            abort(404)
        _record_exposure(ctx, chat_id, page)
        topics = rd.forum_topics(chat_id)
        return _render("im/chat.html", ctx, page=page, chat_id=chat_id, topics=topics, topic=None, **_info(rd, chat_id))

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/im/chat/<chat_id>/topic/<int:topic_id>")
@login_required
def im_chat_topic(exp_id, chat_id, topic_id):
    def handler(session, ctx, rd):
        topics = rd.forum_topics(chat_id)
        if topics is None:
            abort(404)
        topic = next((t for t in topics if t["id"] == topic_id), None)
        if topic is None:
            abort(404)
        page = _history(rd, ctx, chat_id, forum_topic_id=topic_id)
        _record_exposure(ctx, chat_id, page)
        return _render("im/chat.html", ctx, page=page, chat_id=chat_id, topics=topics, topic=topic, **_info(rd, chat_id))

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/im/chat/<chat_id>/members")
@login_required
def im_members(exp_id, chat_id):
    def handler(session, ctx, rd):
        members = rd.members(chat_id)
        if members is None:
            abort(404)
        title = rd.history(chat_id, limit=1)["title"]
        return _render("im/members.html", ctx, members=members, chat_id=chat_id, title=title)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/im/thread/<message_id>")
@login_required
def im_thread(exp_id, message_id):
    def handler(session, ctx, rd):
        thread = rd.thread(message_id)
        if thread is None:
            abort(404)
        return _render("im/thread.html", ctx, thread=thread)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/im/search")
@login_required
def im_search(exp_id):
    def handler(session, ctx, rd):
        q = (request.args.get("q") or "").strip()
        return _render("im/search.html", ctx, q=q, hits=rd.search(q))

    return _view(exp_id, handler)


# what the search overlay can look for: tab -> (chat types, or None for people and messages)
_FIND_KINDS = {
    "chats": ("private", "group", "supergroup", "channel"),
    "groups": ("group", "supergroup"),
    "channels": ("channel",),
    "users": None,
    "posts": None,
}


def _find_payload(ctx, rd, kind, q):
    """The results of one search tab as the overlay shows them (texts already translated)."""
    suffix = "?" + urlencode(ctx.params) if ctx.params else ""
    base = f"/{ctx.exp.idexp}/im"
    need = 2 if kind == "posts" else 1
    if len(q) < need:
        hint = _("Type at least two characters.") if kind == "posts" else _("Type to search.")
        return {"kind": kind, "q": q, "results": [], "message": hint}
    results = []
    if kind == "users":
        for a in rd.find_accounts(q):
            results.append(
                {
                    "href": f"{base}/profile/{a['id']}{suffix}",
                    "title": a["username"],
                    "subtitle": a["kind"] or "",
                    "hue": a["hue"],
                }
            )
    elif kind == "posts":
        for m in rd.search(q):
            sender = (m.get("sender") or {}).get("username")
            text = (m.get("text") or "").strip().replace("\n", " ")
            results.append(
                {
                    "href": f"{base}/chat/{m['chat_id']}{suffix}#m-{m['id']}",
                    "title": m["chat_title"],
                    "subtitle": _("d%(d)s · %(s)s", d=m["day"], s=m["slot"]),
                    "snippet": ((sender + ": ") if sender else "") + text[:160],
                    "hue": avatar_hue(m["chat_id"]),
                }
            )
    else:
        for c in rd.find_chats(q, kinds=_FIND_KINDS[kind]):
            parts = [_("%(n)s members", n=c["members"])]
            if c["username"]:
                parts.append("@" + c["username"])
            if c["visibility"] == "private":
                parts.append(_("private"))
            if c["joined"]:
                parts.append(_("joined"))
            results.append(
                {
                    "href": f"{base}/chat/{c['id']}{suffix}",
                    "title": c["title"],
                    "subtitle": " · ".join(parts),
                    "type": c["type"],
                    "hue": c["hue"],
                    "chat_id": c["id"],
                    "joined": c["joined"],
                }
            )
    return {"kind": kind, "q": q, "results": results, "message": "" if results else _("Nothing found.")}


@main.route("/<int:exp_id>/im/api/search")
@login_required
def im_api_search(exp_id):
    def handler(session, ctx, rd):
        kind = request.args.get("kind", "chats")
        if kind not in _FIND_KINDS:
            kind = "chats"
        return jsonify(_find_payload(ctx, rd, kind, (request.args.get("q") or "").strip()))

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/im/profile/<account_id>")
@login_required
def im_profile(exp_id, account_id):
    def handler(session, ctx, rd):
        profile = rd.profile(account_id, include_persona=ctx.staff is not None)
        if profile is None:
            abort(404)
        return _render("im/profile.html", ctx, profile=profile)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/im/api/status")
@login_required
def im_api_status(exp_id):
    exp = _experiment_or_404(exp_id)
    try:
        after = int(request.args.get("after", 0))
    except ValueError:
        after = 0
    try:
        with open_reader(_db_path(exp)) as session:
            return jsonify({**status(session, after), "running": bool(exp.running)})
    except ImReadError as exc:
        return jsonify({"error": str(exc)}), 503


@main.route("/<int:exp_id>/im/api/chat/<chat_id>/history")
@login_required
def im_api_history(exp_id, chat_id):
    def handler(session, ctx, rd):
        page = _history(rd, ctx, chat_id)
        if page is None:
            abort(404)
        _record_exposure(ctx, chat_id, page)
        return jsonify(page)

    return _view(exp_id, handler)


# -- participant mode (plan 6.8): every write goes through the human gateway ----------------------
def _participant_or_403(exp_id):
    """Experiment and participant of the session for a write; 403 for everyone else."""
    exp = _experiment_or_404(exp_id)
    ui = _ui(exp_id)
    user = current_user if current_user.is_authenticated else None
    assigned = (
        user is not None
        and db.session.scalars(
            select(User_Experiment).filter_by(user_id=user.id, exp_id=exp.idexp)
        ).first()
        is not None
    )
    part = participation.participant_for(exp, user, ui, bool(assigned))
    if part is None:
        abort(403)
    return exp, ui, part


def _json_error(status, code, message=None):
    return jsonify({"ok": False, "code": code, "message": message}), status


@main.route("/<int:exp_id>/im/notice", methods=["GET", "POST"])
@login_required
def im_notice(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    notice = (ui.get("im_participant_notice") or "").strip()
    key = participation.NOTICE_SESSION_PREFIX + str(exp.idexp)
    if request.method == "POST":
        if not participation.csrf_ok(flask_session, request.form.get("csrf_token")):
            abort(400)
        flask_session[key] = True
        return redirect(url_for("main.im_index", exp_id=exp.idexp))
    if not notice:
        return redirect(url_for("main.im_index", exp_id=exp.idexp))
    return render_template(
        "im/notice.html",
        exp=exp,
        notice=notice,
        csrf_token=participation.csrf_token(flask_session),
        ui=ui,
        platform_ui="im",
        participant=part,
        ctx=None,
        params={},
        poll_seconds=0,
    )


@main.route("/<int:exp_id>/im/act", methods=["POST"])
@login_required
def im_act(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    if not participation.csrf_ok(flask_session, request.headers.get(participation.CSRF_HEADER)):
        return _json_error(400, "csrf", "missing or wrong CSRF token")
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or request.content_length is None or request.content_length > 16384:
        return _json_error(400, "invalid_request", "a JSON object (up to 16 KiB) is expected")
    action_type = body.get("type")
    reason = participation.action_allowed(ui, action_type)
    if reason == "unknown_action":
        return _json_error(400, "invalid_request", "unknown action")
    if reason:
        return _json_error(403, reason, "this interaction is switched off for the experiment")
    if not exp.running:
        return _json_error(409, "not_running", "the simulation is not running")
    action_id = participation.namespaced_action_id(part.account_id, body.get("client_action_id"))
    if action_id is None:
        return _json_error(400, "invalid_request", "client_action_id is required (up to 64 chars)")
    fields = {k: v for k, v in body.items() if k not in ("type", "client_action_id")}
    action = {"type": action_type, "client_action_id": action_id, **fields}
    try:
        code, payload = GatewayClient(part.exp_folder).actions(part.account_id, [action])
    except GatewayUnavailable:
        return _json_error(503, "unavailable", "connection lost: try again in a moment")
    return jsonify(payload), code


@main.route("/<int:exp_id>/im/invite", methods=["POST"])
@login_required
def im_invite(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    if not participation.csrf_ok(flask_session, request.headers.get(participation.CSRF_HEADER)):
        return _json_error(400, "csrf", "missing or wrong CSRF token")
    if not ui.get("interactions_enabled", True):
        return _json_error(403, "interactions_disabled")
    body = request.get_json(silent=True) or {}
    chat_id = str(body.get("chat_id") or "")
    if not chat_id:
        return _json_error(400, "invalid_request", "chat_id is required")
    try:
        code, payload = GatewayClient(part.exp_folder).invite(part.account_id, chat_id)
    except GatewayUnavailable:
        return _json_error(503, "unavailable", "connection lost: try again in a moment")
    return jsonify(payload), code


def _participant_sidebar(exp, part):
    """The chat list of a participant's own viewpoint, for pages that do not run through ``_view``."""
    try:
        with open_reader(_db_path(exp)) as session:
            latest = latest_round(session)
            reader = Reader(session, Viewpoint("account", part.account_id, latest))
            return {"sidebar_chats": reader.chat_list(), "latest": latest}
    except (ImReadError, ViewpointError):
        return {"sidebar_chats": [], "latest": 0}


@main.route("/<int:exp_id>/im/notifications")
@login_required
def im_notifications(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    if not ui.get("notifications_menu", True):
        abort(404)
    error, items = None, []
    try:
        code, payload = GatewayClient(part.exp_folder).notifications(part.account_id)
        if code == 200:
            per_account = (payload.get("data") or {}).get("notifications") or {}
            items = per_account.get(part.account_id, [])
        else:
            error = payload.get("message") or payload.get("code")
    except GatewayUnavailable:
        error = _("Connection lost: the notifications will appear when it is back.")
    return render_template(
        "im/notifications.html",
        exp=exp,
        items=items,
        error=error,
        ui=ui,
        platform_ui="im",
        participant=part,
        ctx=None,
        params={},
        poll_seconds=0,
        csrf_token="",
        active_chat_id=None,
        **_participant_sidebar(exp, part),
    )


@main.route("/<int:exp_id>/im/api/gateway")
@login_required
def im_api_gateway(exp_id):
    """Is the gateway answering? The participant pages poll this to show 'connection lost'."""
    exp, ui, part = _participant_or_403(exp_id)
    try:
        code, payload = GatewayClient(part.exp_folder).state()
    except GatewayUnavailable:
        return jsonify({"ok": False, "online": False}), 200
    return jsonify({"ok": code == 200, "online": code == 200, "state": payload.get("data")}), 200
