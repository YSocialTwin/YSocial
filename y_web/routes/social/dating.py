"""Dating observer frontend (plan, 6.1-6.4): the app of a dating experiment, read only.

Every route carries ``<int:exp_id>`` so the experiment context and access guards apply; none binds ``db_exp``
(the run database is opened by ``y_web.src.dating.reader`` with ``mode=ro``). Three viewpoints: ``overview``
and ``account`` (admin and researcher only) and ``public`` (everyone, unless the experiment closes it).
Pages for the ``public`` and ``account`` viewpoints are built from the reader's whitelisted fields only (IR-D-16).
"""

import os

from flask import abort, current_app, jsonify, redirect, render_template, request
from flask import session as flask_session
from flask import url_for
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.routes.social._blueprint import main
from y_web.src.dating import human, is_dating_experiment
from y_web.src.dating.reader import (
    ACCOUNT,
    OVERVIEW,
    PUBLIC,
    DatingReadError,
    Viewpoint,
    ViewpointError,
    open_reader,
)
from y_web.src.models import Exps, User_Experiment

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


class _Redirect(Exception):
    """Raised inside a context to send the person somewhere else (entry form, notice)."""

    def __init__(self, url):
        self.url = url


def participant_of(exp, ui):
    """The participant behind the session (``human.Participant``), or ``None`` (observer only)."""
    from flask_login import current_user

    user = current_user if current_user.is_authenticated else None
    if user is None:
        return None
    assigned = (
        db.session.scalars(
            select(User_Experiment).filter_by(user_id=user.id, exp_id=exp.idexp)
        ).first()
        is not None
    )
    return human.participant_for(exp, user, ui, assigned)


class _Context:
    def __init__(self, exp, staff, vp, latest, ui, focus=None, participant=None):
        self.exp, self.staff, self.vp, self.latest, self.ui = exp, staff, vp, latest, ui
        self.participant = participant
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
    part = participant_of(exp, ui) if staff is None else None
    if part is not None:
        return _participant_context(reader, exp, ui, part)
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
    if acc and staff is not None:
        acc = (
            reader.resolve_account(acc) or acc
        )  # a username is accepted as well as an id
    try:
        vp = Viewpoint(kind, acc, rnd)
    except ViewpointError:
        abort(400)
    focus = acc if kind == OVERVIEW else None
    return _Context(exp, staff, vp, latest, ui, focus)


def _participant_context(reader, exp, ui, part):
    """A person plays: their own account, the latest round, no time travel, no other account."""
    if not reader.has_account(part.account_id):
        raise _Redirect(url_for("main.dating_join", exp_id=exp.idexp))
    notice = (ui.get("dating_participant_notice") or "").strip()
    ack_key = human.NOTICE_SESSION_PREFIX + str(exp.idexp)
    if (
        notice
        and not flask_session.get(ack_key)
        and request.endpoint != "main.dating_notice"
    ):
        raise _Redirect(url_for("main.dating_notice", exp_id=exp.idexp))
    latest = reader.latest_round()
    return _Context(
        exp,
        None,
        Viewpoint(ACCOUNT, part.account_id, latest),
        latest,
        ui,
        participant=part,
    )


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
    viewed = None
    if ctx.staff is not None and (ctx.vp.account_id or ctx.focus):
        viewed = reader.account_brief(ctx.vp.account_id or ctx.focus, ctx.vp.round)
    time_travel = ctx.participant is None and (
        ctx.staff is not None or bool(ctx.ui.get("dating_allow_time_travel", True))
    )
    unread = (
        reader.unread_count(ctx.vp.account_id, ctx.vp) if ctx.vp.kind == ACCOUNT else 0
    )
    return render_template(
        template,
        unread=unread,
        exp=ctx.exp,
        ctx=ctx,
        params=ctx.params,
        link=_linker(ctx),
        is_staff=ctx.staff is not None,
        participant=ctx.participant,
        csrf_token=human.csrf_token(flask_session) if ctx.participant else "",
        day=day,
        hour=hour,
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
    except _Redirect as moved:
        return redirect(moved.url)
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
        if ctx.participant is not None:
            return _render("dating/play.html", ctx, reader)
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
        convo = None
        if ctx.participant is not None:
            from y_web.routes.social.dating_participant import conversation_for

            convo = conversation_for(ctx.exp, ctx.participant, match_id)
        return _render(
            "dating/chat.html",
            ctx,
            reader,
            chat=chat,
            matches=items,
            match_id=match_id,
            convo=convo,
        )

    return _view(exp_id, handler)


def _record_view(ctx, account_id):
    """VIEW_PROFILE of a person opening a profile; the page does not depend on the answer."""
    from y_web.routes.social.dating_participant import _gateway

    source = request.args.get("src")
    action = {
        "type": "VIEW_PROFILE",
        "payload": {
            "target_id": account_id,
            "source": source if source in ("deck", "match", "chat") else "profile",
        },
    }
    try:
        _gateway(ctx.exp, ctx.participant, "act", ctx.participant.account_id, [action])
    except Exception:  # a view that is not recorded must not break the page
        current_app.logger.info("dating: profile view not recorded", exc_info=True)


@main.route("/<int:exp_id>/dating/profile/<account_id>")
def dating_profile(exp_id, account_id):
    def handler(ctx, reader):
        profile = reader.profile(account_id, ctx.vp)
        if profile is None:
            abort(404)
        if ctx.participant is not None and account_id != ctx.participant.account_id:
            _record_view(ctx, account_id)
        return _render("dating/profile.html", ctx, reader, profile=profile)

    return _view(exp_id, handler)


def _search_filters(args):
    """The filters of the search page from the query string (anything unreadable is ignored)."""
    filters = {
        "genders": [g for g in args.getlist("gender") if g],
        "intents": [i for i in args.getlist("intent") if i],
        "city": args.get("city", ""),
        "interest": args.get("interest", ""),
        "photo": args.get("photo") == "1",
    }
    lo, hi = _int(args.get("age_min")), _int(args.get("age_max"))
    if lo is not None:
        filters["age_min"] = lo
    if hi is not None:
        filters["age_max"] = hi
    return filters


@main.route("/<int:exp_id>/dating/search")
def dating_search(exp_id):
    def handler(ctx, reader):
        term = request.args.get("q", "")
        filters = _search_filters(request.args)
        sort = request.args.get("sort", "relevance")
        if sort not in reader.SORTS:
            sort = "relevance"
        found = reader.search(term, ctx.vp.round, filters=filters, sort=sort)
        values = dict(
            term=term,
            results=found["results"],
            total=found["total"],
            filters=filters,
            sort=sort,
            searched=True,
            facets=reader.facets(ctx.vp.round),
        )
        if request.args.get("partial") == "1":
            return render_template(
                "dating/_search_results.html",
                link=_linker(ctx),
                ctx=ctx,
                exp=ctx.exp,
                participant=ctx.participant,
                **values,
            )
        return _render("dating/search.html", ctx, reader, **values)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/notifications")
def dating_notifications(exp_id):
    def handler(ctx, reader):
        if ctx.vp.kind != ACCOUNT:
            abort(404)
        items = reader.notifications(ctx.vp.account_id, ctx.vp)
        return _render("dating/notifications.html", ctx, reader, items=items)

    return _view(exp_id, handler)


@main.route("/<int:exp_id>/dating/api/accounts")
def dating_api_accounts(exp_id):
    """Accounts by username for the viewpoint bar (staff only): ``?q=ann`` -> name and small picture."""
    exp = _experiment_or_404(exp_id)
    staff = _staff_user()
    if staff is None:
        abort(403)
    from y_web.src.experiment.access import user_can_view_experiment

    if not user_can_view_experiment(staff, exp):
        abort(403)
    try:
        with open_reader(_db_path(exp)) as reader:
            ordinal = _int(request.args.get("round")) or reader.latest_round()
            found = reader.find_accounts(request.args.get("q", ""), ordinal)
    except DatingReadError:
        return jsonify({"accounts": []})
    media = current_app.jinja_env.globals["dating_media"]
    return jsonify(
        {
            "accounts": [
                {
                    "id": a["id"],
                    "username": a["username"],
                    "initials": a["initials"],
                    "hue": a["hue"],
                    "photo": media(a["photo"]) if a.get("photo") else "",
                }
                for a in found
            ]
        }
    )


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
