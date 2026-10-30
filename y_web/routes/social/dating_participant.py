"""Participant mode of the dating frontend (IR-D-22, IR-D-27..31).

A person with the role user or student, assigned to the experiment, plays as their own account. They enter
with a profile (validated by the runtime like an agent's), read an initial notice, swipe a deck built by
the recommender of the experiment, chat, propose dates, block and report. YWeb never writes the run
database: every read of the deck and every action goes through the human gateway, which calls the server.
Pages that only read (matches, chats, profiles) use the read-only reader, fixed to the person's account.
"""

from flask import (
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
)
from flask import session as flask_session
from flask import url_for
from flask_login import current_user, login_required

from y_web.i18n import gettext as _
from y_web.routes.social._blueprint import main
from y_web.routes.social.dating import (
    _db_path,
    _experiment_or_404,
    _staff_user,
    _ui,
    participant_of,
)
from y_web.src.dating import human, photos
from y_web.src.dating.gateway import (
    GatewayClient,
    GatewayUnavailable,
    is_running,
    start_for_experiment,
)
from y_web.src.dating.reader import DatingReadError, open_reader

MAX_BODY = 16384
MAX_ACTIONS = 20
MAX_JOIN_PHOTOS = 3
MAX_UPLOAD = photos.MAX_BYTES + 65536  # the picture and the form around it


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


def _photo_error(code):
    """The translated message of a refused upload (``photos.PhotoError.code``)."""
    return {
        "empty": _("The file is empty."),
        "too_large": _("The picture is larger than 5 MB."),
        "format": _("Use a PNG, JPEG or WebP picture."),
        "pixels": _("The picture has too many pixels."),
        "unreadable": _("The file is not a readable picture."),
        "caption": _(
            "Describe every photo: the other people and the simulated users decide on the description."
        ),
    }.get(code, _("The picture could not be stored."))


def _join_photos(part, form, files):
    """``(photos, stored)`` of the entry form: up to three rows of description and optional picture."""
    out, stored = [], []
    try:
        for n in range(1, MAX_JOIN_PHOTOS + 1):
            caption = (form.get(f"photo_caption_{n}") or "").strip()
            upload = files.get(f"photo_file_{n}")
            has_file = upload is not None and bool(upload.filename)
            if not caption and not has_file:
                continue
            if not caption:
                raise photos.PhotoError("caption")
            photo = {"caption": caption[:500]}
            if has_file:
                url = photos.store_upload(
                    part.exp_folder, part.account_id, upload.stream
                )
                stored.append(url)
                photo["media_url"] = url
            out.append(photo)
    except photos.PhotoError:
        for url in stored:
            photos.delete_upload(part.exp_folder, url)
        raise
    return out, stored


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
        try:
            pictures, stored = _join_photos(part, form, request.files)
        except photos.PhotoError as exc:
            error = _photo_error(exc.code)
        else:
            account = human.account_from_form(form, language, shown, pictures)
            status, payload = _gateway(exp, part, "register", part.key, account)
            if status in (200, 201):
                if status == 200 and not payload.get("created"):
                    for (
                        url
                    ) in (
                        stored
                    ):  # the account already existed: the files are not needed
                        photos.delete_upload(part.exp_folder, url)
                return redirect(url_for("main.dating_home", exp_id=exp_id))
            for url in stored:  # the account was not created: the files are not needed
                photos.delete_upload(part.exp_folder, url)
            error = {
                403: _("Taking part is closed for this experiment."),
                409: _("This name is taken or there is no room for more participants."),
                503: _(
                    "The experiment is not reachable right now. Try again in a moment."
                ),
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


@main.route("/<int:exp_id>/dating/api/photo", methods=["POST"])
@login_required
def dating_api_photo(exp_id):
    """Add a picture to the profile: it is checked and re-encoded here, then added through the gateway."""
    exp, ui, part = _participant_or_403(exp_id)
    if request.content_length is None or request.content_length > MAX_UPLOAD:
        return _json_error(413, "too_large", _photo_error("too_large"))
    if not human.csrf_ok(
        flask_session,
        request.headers.get(human.CSRF_HEADER) or request.form.get("csrf_token"),
    ):
        return _json_error(400, "csrf", "missing or wrong CSRF token")
    caption = (request.form.get("caption") or "").strip()
    upload = request.files.get("photo")
    if not caption:
        return _json_error(400, "caption", _photo_error("caption"))
    if upload is None or not upload.filename:
        return _json_error(400, "empty", _photo_error("empty"))
    try:
        url = photos.store_upload(part.exp_folder, part.account_id, upload.stream)
    except photos.PhotoError as exc:
        return _json_error(400, exc.code, _photo_error(exc.code))
    action = {
        "type": "ADD_PHOTO",
        "payload": {"caption": caption[:500], "media_url": url},
    }
    status, payload = _gateway(exp, part, "act", part.account_id, [action])
    outcomes = payload.get("outcomes") or [] if isinstance(payload, dict) else []
    if status == 200 and outcomes and outcomes[0].get("success"):
        return jsonify({"ok": True})
    photos.delete_upload(part.exp_folder, url)
    reason = (outcomes[0].get("error") if outcomes else None) or payload.get("error")
    return _json_error(status if status != 200 else 400, "refused", reason or "refused")


@main.route("/<int:exp_id>/dating/media/<path:name>")
def dating_media(exp_id, name):
    """A profile picture, of an agent or of a person: only files of the media folder of the experiment."""
    from y_web.src.experiment.access import user_can_view_experiment

    exp = _experiment_or_404(exp_id)
    staff = _staff_user()
    if staff is not None:
        if not user_can_view_experiment(staff, exp):
            abort(403)
    else:
        ui = _ui(exp_id)
        if participant_of(exp, ui) is None and not ui.get(
            "dating_public_observer_enabled", True
        ):
            abort(403)
    path = photos.resolve_media(human.experiment_folder(exp), name)
    if path is None:
        abort(404)
    response = send_file(path, mimetype=photos.content_type(name), max_age=300)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, max-age=300"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


@main.app_template_global("dating_media")
def dating_media_url(url):
    """Address of a picture of the experiment being shown (empty when the profile has no file)."""
    exp_id = (request.view_args or {}).get("exp_id")
    if not url or exp_id is None:
        return ""
    return url_for("main.dating_media", exp_id=exp_id, name=url)


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
