"""Instant messaging observer frontend (plan, 6.2, 6.3): chats of an IM experiment, read only.

All routes carry ``<int:exp_id>`` so the experiment context and access guards apply; none of them binds
``db_exp`` (the IM database is opened by ``y_web.src.im.engine`` in read-only mode, plan 4.1). Three
viewpoints: ``public`` (all roles), ``account`` and ``overview`` (admin and researcher only).
"""

import os

from flask import abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.routes.social._blueprint import main
from y_web.src.im import is_im_experiment
from y_web.src.im.engine import ImReadError, open_reader
from y_web.src.im.reader import Reader, Viewpoint, ViewpointError, latest_round, status
from y_web.src.im.timeline import clamp_round, day_slot, ordinal
from y_web.src.models import Exps

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

    def __init__(self, exp, staff, viewpoint, latest, live, ui=None):
        self.exp, self.staff, self.vp, self.latest, self.live = exp, staff, viewpoint, latest, live
        self.ui = ui or {}

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
    if staff is None and not ui.get("im_public_observer_enabled", True):
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
    return _Context(exp, staff, viewpoint, latest, bool(exp.running), ui)


def _render(template, ctx, **values):
    return render_template(
        template,
        exp=ctx.exp,
        ctx=ctx,
        params=ctx.params,
        is_staff=ctx.staff is not None,
        day_slot=ctx.day_slot(),
        poll_seconds=_poll_seconds(ctx.ui) if (ctx.live and ctx.vp.round == ctx.latest) else 0,
        ui=ctx.ui,
        time_travel=ctx.staff is not None or bool(ctx.ui.get("im_allow_time_travel", True)),
        platform_ui="im",
        frontend_adds_on_modules=[],  # no frontend plugin module attaches to the chat pages
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
            return handler(session, ctx, Reader(session, ctx.vp))
    except ViewpointError:
        abort(400)
    except ImReadError as exc:
        return _unavailable(exp, str(exc))


def _accounts_for_picker(session):
    from y_web.src.im.engine import im_modules

    models = im_modules()[0]
    return [
        {"id": row.id, "username": row.username, "kind": row.kind}
        for row in session.scalars(select(models.Account).order_by(models.Account.username))
    ]


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
        accounts = _accounts_for_picker(session) if ctx.staff is not None else []
        return _render("im/index.html", ctx, chats=rd.chat_list(), accounts=accounts)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/im/chat/<chat_id>")
@login_required
def im_chat(exp_id, chat_id):
    def handler(session, ctx, rd):
        page = _history(rd, ctx, chat_id)
        if page is None:
            abort(404)
        topics = rd.forum_topics(chat_id)
        return _render("im/chat.html", ctx, page=page, chat_id=chat_id, topics=topics, topic=None)

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
        return _render("im/chat.html", ctx, page=page, chat_id=chat_id, topics=topics, topic=topic)

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
        return jsonify(page)

    return _view(exp_id, handler)
