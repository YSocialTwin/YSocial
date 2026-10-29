"""Dating observer frontend (plan, 6.1-6.4): the app of a dating experiment, read only.

Every route carries ``<int:exp_id>`` so the experiment context and access guards apply; none binds ``db_exp``
(the run database is opened by ``y_web.src.dating.reader`` with ``mode=ro``). Three viewpoints: ``overview``
and ``account`` (admin and researcher only) and ``public`` (everyone, unless the experiment closes it).
Pages for the ``public`` and ``account`` viewpoints are built from the reader's whitelisted fields only (IR-D-16).
"""

import os

from flask import abort, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.routes.social._blueprint import main
from y_web.src.dating import is_dating_experiment
from y_web.src.dating.reader import (
    ACCOUNT,
    OVERVIEW,
    PUBLIC,
    DatingReadError,
    Viewpoint,
    ViewpointError,
    open_reader,
)
from y_web.src.models import Exps

POLL_SECONDS = 10
PAGE_SIZE = 24


def _ui(exp_id):
    from y_web.routes.social.helpers import _load_ui_settings

    return _load_ui_settings(exp_id)


def _staff_user():
    from y_web.routes.admin.sub.experiments._helpers import _current_admin_user_or_none

    user = _current_admin_user_or_none()
    return (
        user
        if user is not None and getattr(user, "role", None) in ("admin", "researcher")
        else None
    )


def _experiment_or_404(exp_id):
    exp = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
    if exp is None or not is_dating_experiment(exp):
        abort(404)
    return exp


def _db_path(exp) -> str:
    from y_web.src.system.path_utils import get_writable_path

    parts = exp.db_name.split(os.sep)
    return os.path.join(
        get_writable_path(), "y_web", "experiments", parts[1], "database_server.db"
    )


class _Context:
    def __init__(self, exp, staff, vp, latest, ui, focus=None):
        self.exp, self.staff, self.vp, self.latest, self.ui = exp, staff, vp, latest, ui
        self.live = bool(exp.running)
        self.focus = (
            focus  # overview only: account whose deck the researcher is looking at
        )

    @property
    def params(self):
        out = {"vp": self.vp.kind}
        if self.vp.kind == ACCOUNT:
            out["acc"] = self.vp.account_id
        elif self.focus:
            out["acc"] = self.focus
        if self.vp.round != self.latest:
            out["round"] = self.vp.round
        return out


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _open_context(reader, exp_id):
    from y_web.src.experiment.access import user_can_view_experiment

    exp = _experiment_or_404(exp_id)
    staff = _staff_user()
    if staff is not None and not user_can_view_experiment(staff, exp):
        abort(403)
    ui = _ui(exp_id)
    if staff is None and not ui.get("dating_public_observer_enabled", True):
        abort(403)
    kind = request.args.get("vp") or (OVERVIEW if staff is not None else PUBLIC)
    if kind != PUBLIC and staff is None:
        abort(403)  # everyone else sees the public view only
    latest = reader.latest_round()
    rnd = latest
    if staff is not None or ui.get("dating_allow_time_travel", True):
        requested = _int(request.args.get("round"))
        if requested is not None:
            rnd = min(max(requested, 1), latest) if latest else 0
    acc = request.args.get("acc") or None
    try:
        vp = Viewpoint(kind, acc, rnd)
    except ViewpointError:
        abort(400)
    focus = acc if kind == OVERVIEW else None
    return _Context(exp, staff, vp, latest, ui, focus)


def _poll_seconds(ctx):
    if not ctx.live or ctx.vp.round != ctx.latest:
        return 0
    value = _int(ctx.ui.get("dating_poll_seconds"), POLL_SECONDS)
    return max(1, min(60, value))


def _linker(ctx):
    """``link('/matches', round=3)``: a page of this experiment that keeps viewpoint, account and round."""
    from urllib.parse import urlencode

    def link(path="", **extra):
        params = {**ctx.params, **extra}
        for key in [k for k, v in params.items() if v is None]:
            del params[key]
        return "/{}/dating{}?{}".format(ctx.exp.idexp, path, urlencode(params))

    return link


def _render(template, ctx, reader, **values):
    day, hour = reader.day_hour(ctx.vp.round)
    accounts = reader.accounts(ctx.vp.round) if ctx.staff is not None else []
    viewed = None
    if ctx.vp.kind == ACCOUNT:
        viewed = next((a for a in accounts if a["id"] == ctx.vp.account_id), None)
    time_travel = ctx.staff is not None or bool(
        ctx.ui.get("dating_allow_time_travel", True)
    )
    return render_template(
        template,
        exp=ctx.exp,
        ctx=ctx,
        params=ctx.params,
        link=_linker(ctx),
        is_staff=ctx.staff is not None,
        day=day,
        hour=hour,
        accounts=accounts,
        viewed=viewed,
        time_travel=time_travel,
        poll_seconds=_poll_seconds(ctx),
        ui=ctx.ui,
        platform_ui="dating",
        frontend_adds_on_modules=[],
        slots=reader.slots,
        **values,
    )


def _view(exp_id, handler):
    exp = _experiment_or_404(exp_id)
    try:
        with open_reader(_db_path(exp)) as reader:
            ctx = _open_context(reader, exp_id)
            return handler(ctx, reader)
    except ViewpointError:
        abort(400)
    except DatingReadError as exc:
        return (
            render_template("dating/unavailable.html", exp=exp, message=str(exc)),
            503,
        )


@main.route("/<int:exp_id>/dating")
def dating_home(exp_id):
    def handler(ctx, reader):
        page = max(_int(request.args.get("page"), 1), 1)
        deck = None
        showcase = None
        target = ctx.vp.account_id or ctx.focus
        if ctx.vp.kind == PUBLIC or (ctx.vp.kind == OVERVIEW and not target):
            showcase = reader.showcase(ctx.vp.round, page, PAGE_SIZE)
        else:
            deck = reader.deck(target, ctx.vp)
        return _render(
            "dating/home.html",
            ctx,
            reader,
            deck=deck,
            showcase=showcase,
            target=target,
            page=page,
        )

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/matches")
def dating_matches(exp_id):
    def handler(ctx, reader):
        if ctx.vp.kind == PUBLIC:
            abort(404)  # the public view has no matches
        items = reader.matches(ctx.vp.account_id, ctx.vp)
        return _render("dating/matches.html", ctx, reader, matches=items)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/chat/<match_id>")
def dating_chat(exp_id, match_id):
    def handler(ctx, reader):
        if ctx.vp.kind == PUBLIC:
            abort(404)
        chat = reader.chat(match_id, ctx.vp)
        if chat is None:
            abort(404)
        items = reader.matches(ctx.vp.account_id, ctx.vp)
        return _render(
            "dating/chat.html", ctx, reader, chat=chat, matches=items, match_id=match_id
        )

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/profile/<account_id>")
def dating_profile(exp_id, account_id):
    def handler(ctx, reader):
        profile = reader.profile(account_id, ctx.vp)
        if profile is None:
            abort(404)
        return _render("dating/profile.html", ctx, reader, profile=profile)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/search")
def dating_search(exp_id):
    def handler(ctx, reader):
        term = request.args.get("q", "")
        results = reader.search(term, ctx.vp.round)
        return _render("dating/search.html", ctx, reader, term=term, results=results)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/notifications")
def dating_notifications(exp_id):
    def handler(ctx, reader):
        if ctx.vp.kind != ACCOUNT:
            abort(404)
        items = reader.notifications(ctx.vp.account_id, ctx.vp)
        return _render("dating/notifications.html", ctx, reader, items=items)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/api/status")
def dating_api_status(exp_id):
    def handler(ctx, reader):
        return jsonify({**reader.status(), "running": ctx.live})

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/api/history")
def dating_api_history(exp_id):
    def handler(ctx, reader):
        if ctx.vp.kind != OVERVIEW:
            abort(404)
        return jsonify({"history": reader.history(ctx.vp)})

    return _view(exp_id, handler)
