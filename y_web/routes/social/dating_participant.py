"""Participant mode of the dating frontend (IR-D-22, IR-D-27..31).

A person with the role user or student, assigned to the experiment, plays as their own account. They enter
with a profile (validated by the runtime like an agent's), read an initial notice, swipe a deck built by
the recommender of the experiment, chat, propose dates, block and report. YWeb never writes the run
database: every read of the deck and every action goes through the human gateway, which calls the server.
Pages that only read (matches, chats, profiles) use the read-only reader, fixed to the person's account.
"""

from flask import abort, current_app, jsonify, redirect, render_template, request
from flask import session as flask_session
from flask import url_for
from flask_login import current_user, login_required

from y_web.i18n import gettext as _
from y_web.routes.social._blueprint import main
from y_web.routes.social.dating import (
    _db_path,
    _experiment_or_404,
    _ui,
    participant_of,
)
from y_web.src.dating import human
from y_web.src.dating.gateway import (
    GatewayClient,
    GatewayUnavailable,
    is_running,
    start_for_experiment,
)
from y_web.src.dating.reader import DatingReadError, open_reader

MAX_BODY = 16384
MAX_ACTIONS = 20


def _participant_or_403(exp_id):
    exp = _experiment_or_404(exp_id)
    ui = _ui(exp_id)
    part = participant_of(exp, ui)
    if part is None:
        abort(403)
    return exp, ui, part


def _json_error(status, code, message=""):
    return jsonify({"ok": False, "error": message or code, "code": code}), status


def _csrf_header_ok():
    return human.csrf_ok(flask_session, request.headers.get(human.CSRF_HEADER))


def _revive(exp, part):
    """The server is up but the gateway is not: start it (a failure is only a warning)."""
    if exp.running and not is_running(part.exp_folder):
        start_for_experiment(part.exp_folder)
    return is_running(part.exp_folder)


def _gateway(exp, part, op, *args):
    """``(status, payload)`` of a gateway call; one revival attempt when it does not answer."""
    for attempt in (0, 1):
        try:
            return getattr(GatewayClient(part.exp_folder), op)(*args)
        except GatewayUnavailable:
            if attempt == 0 and _revive(exp, part):
                continue
            break
    return 503, {"ok": False, "error": "connection lost: try again in a moment"}


def conversation_for(exp, part, match_id):
    """The gateway's view of one conversation (reply state, date state), or ``None`` when it is not available."""
    status, data = _gateway(exp, part, "conversations", part.account_id)
    if status != 200:
        return None
    return next(
        (c for c in data.get("conversations", []) if c["match_id"] == match_id), None
    )


def _vocabulary(exp):
    try:
        with open_reader(_db_path(exp)) as reader:
            return reader.vocabulary()
    except DatingReadError:
        return {"genders": [], "interests": []}


def _account_exists(exp, part):
    try:
        with open_reader(_db_path(exp)) as reader:
            return reader.has_account(part.account_id)
    except DatingReadError:
        return False


def _shell(exp, ui, part, **values):
    from types import SimpleNamespace

    stub = SimpleNamespace(
        vp=SimpleNamespace(kind="account", round=0, account_id=part.account_id),
        latest=0,
        focus=None,
    )

    def link(path="", **_extra):
        return "/{}/dating{}".format(exp.idexp, path)

    return render_template(
        values.pop("template"),
        exp=exp,
        ui=ui,
        participant=part,
        csrf_token=human.csrf_token(flask_session),
        platform_ui="dating",
        frontend_adds_on_modules=[],
        is_staff=False,
        ctx=stub,
        link=link,
        params={},
        poll_seconds=0,
        time_travel=False,
        **values,
    )


@main.route("/<int:exp_id>/dating/join", methods=["GET", "POST"])
@login_required
def dating_join(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    if _account_exists(exp, part):
        return redirect(url_for("main.dating_home", exp_id=exp_id))
    error, form = None, {}
    if request.method == "POST":
        if not human.csrf_ok(flask_session, request.form.get("csrf_token")):
            abort(400)
        form = request.form
        shown = (
            human.pseudonym(current_user)
            if form.get("name_mode") == "pseudonym"
            else part.username
        )
        language = (exp.prompt_language or "en")[:8]
        account = human.account_from_form(form, language, shown)
        status, payload = _gateway(exp, part, "register", part.key, account)
        if status in (200, 201):
            return redirect(url_for("main.dating_home", exp_id=exp_id))
        error = {
            403: _("Taking part is closed for this experiment."),
            409: _("This name is taken or there is no room for more participants."),
            503: _("The experiment is not reachable right now. Try again in a moment."),
        }.get(status)
        if error is None:
            error = _(
                "Please check your profile: %(why)s", why=payload.get("error", "")
            )
        current_app.logger.info("dating entry refused with %s", status)
    return _shell(
        exp,
        ui,
        part,
        template="dating/join.html",
        form=form,
        error=error,
        vocab=_vocabulary(exp),
        pseudonym=human.pseudonym(current_user),
        intents=human.INTENTS,
        notice=(ui.get("dating_participant_notice") or "").strip(),
    )


@main.route("/<int:exp_id>/dating/notice", methods=["GET", "POST"])
@login_required
def dating_notice(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    notice = (ui.get("dating_participant_notice") or "").strip()
    key = human.NOTICE_SESSION_PREFIX + str(exp.idexp)
    if request.method == "POST":
        if not human.csrf_ok(flask_session, request.form.get("csrf_token")):
            abort(400)
        flask_session[key] = True
        return redirect(url_for("main.dating_home", exp_id=exp.idexp))
    if not notice:
        return redirect(url_for("main.dating_home", exp_id=exp.idexp))
    return _shell(exp, ui, part, template="dating/notice.html", notice=notice)


@main.route("/<int:exp_id>/dating/api/deck")
@login_required
def dating_api_deck(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    status, payload = _gateway(exp, part, "browse", part.account_id)
    return jsonify(payload), status


@main.route("/<int:exp_id>/dating/api/state")
@login_required
def dating_api_state(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    status, payload = _gateway(exp, part, "state", part.account_id)
    return jsonify(payload), status


@main.route("/<int:exp_id>/dating/api/inbox")
@login_required
def dating_api_inbox(exp_id):
    """Conversations (with date state) and the new notifications of the person."""
    exp, ui, part = _participant_or_403(exp_id)
    status, convs = _gateway(exp, part, "conversations", part.account_id)
    if status != 200:
        return jsonify(convs), status
    status, notes = _gateway(exp, part, "notifications", part.account_id)
    return (
        jsonify(
            {
                "ok": status == 200,
                "conversations": convs.get("conversations", []),
                "notifications": (
                    notes.get("notifications", []) if status == 200 else []
                ),
            }
        ),
        200,
    )


@main.route("/<int:exp_id>/dating/api/act", methods=["POST"])
@login_required
def dating_api_act(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    if not _csrf_header_ok():
        return _json_error(400, "csrf", "missing or wrong CSRF token")
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or request.content_length is None
        or request.content_length > MAX_BODY
    ):
        return _json_error(
            400, "invalid_request", "a JSON object (up to 16 KiB) is expected"
        )
    actions = body.get("actions")
    if not isinstance(actions, list) or not 0 < len(actions) <= MAX_ACTIONS:
        return _json_error(
            400, "invalid_request", "actions: a non-empty list is expected"
        )
    clean = []
    for raw in actions:
        kind = raw.get("type") if isinstance(raw, dict) else None
        payload = raw.get("payload") if isinstance(raw, dict) else None
        if kind not in human.ACTION_TYPES or not isinstance(payload or {}, dict):
            return _json_error(400, "invalid_request", "unknown action")
        clean.append({"type": kind, "payload": payload or {}})
    # the account is the session's, never a request field; the server checks every rule again
    status, payload = _gateway(exp, part, "act", part.account_id, clean)
    return jsonify(payload), status


@main.route("/<int:exp_id>/dating/api/leave", methods=["POST"])
@login_required
def dating_api_leave(exp_id):
    exp, ui, part = _participant_or_403(exp_id)
    if not _csrf_header_ok():
        return _json_error(400, "csrf", "missing or wrong CSRF token")
    status, payload = _gateway(exp, part, "leave", part.account_id)
    return jsonify(payload), status


@main.route("/<int:exp_id>/dating/me")
@login_required
def dating_me(exp_id):
    from y_web.routes.social.dating import _render, _view

    def handler(ctx, reader):
        if ctx.participant is None:
            abort(404)
        exp, ui, part = ctx.exp, ctx.ui, ctx.participant
        status, state = _gateway(exp, part, "state", part.account_id)
        return _render(
            "dating/me.html",
            ctx,
            reader,
            me=state if status == 200 else None,
            intents=human.INTENTS,
        )

    return _view(exp_id, handler)
