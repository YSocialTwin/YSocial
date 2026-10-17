"""
Authentication and user management routes.

Handles user login and logout functionality for administrative users,
researchers, and experiment participants. Manages session creation
and validation for the YSocial platform.
"""

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import login_required, login_user, logout_user
from sqlalchemy import select
from werkzeug.security import check_password_hash

from y_web import db
from y_web.routes.auth._blueprint import auth
from y_web.src.experiment.helpers import ensure_experiment_user
from y_web.src.external_runtime.plugin_hooks import (
    call_first_non_null,
    is_local_redirect,
)
from y_web.src.models import Admin_users, Exps, User_Experiment, User_mgmt
from y_web.i18n import gettext as _

# Roles that log in as experiment participants. "student" is an alias of
# "user": it follows exactly the same flow (experiment selection, feed).
PARTICIPANT_ROLES = ("user", "student")


@auth.route("/login")
def login():
    """
    Display login page.

    Returns:
        Rendered login template
    """
    return render_template("login/login.html")


@auth.route("/login", methods=["POST"])
def login_post():
    """
    Process login form submission and authenticate user.

    Validates credentials and redirects based on role:
    - admin/researcher: admin dashboard
    - teacher: the Training modules page
    - user: experiment selection page (if multiple) or direct to feed

    Returns:
        Redirect to appropriate page based on role, or back to login on failure
    """
    if request.method == "GET":
        return render_template("login/login.html")

    email = request.form.get("email")
    password = request.form.get("password")
    remember = True if request.form.get("remember") else False

    user = db.session.scalars(select(Admin_users).filter_by(email=email)).first()

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user or not check_password_hash(user.password, password):
        flash(_("Please check your login details and try again."))
        return redirect(url_for("auth.login"))

        # Log service start event
    try:
        from y_web.src.telemetry import Telemetry

        telemetry = Telemetry()
        telemetry.log_event({"action": "login", "data": {"role": user.role}})
    except Exception as e:
        print(f"Failed to log start event: {e}")

    # Never carry a platform account id over from an earlier login in this browser
    session.pop("platform_account_id", None)

    # Handle different roles
    if user.role in PARTICIPANT_ROLES:
        # Platform account id of the participant, available to plugins (the
        # session may later hold an experiment-specific id instead).
        session["platform_account_id"] = user.id
        # Optional plugin hook: may redirect the participant (e.g. to a
        # training area) before the experiment selection.
        hook_url = call_first_non_null("post_login", user)
        if is_local_redirect(hook_url):
            return redirect(hook_url)

        # Regular users: need to select experiment
        # Do NOT log them in yet - just show experiment selection
        # Get experiments this user is assigned to
        user_experiments = db.session.scalars(
            select(User_Experiment).filter_by(user_id=user.id)
        ).all()

        if not user_experiments:
            flash(
                _("You are not assigned to any experiments. Please contact an administrator.")
            )
            return redirect(url_for("auth.login"))

        # Get active experiments from the user's assigned experiments
        exp_ids = [ue.exp_id for ue in user_experiments]
        active_exps = db.session.scalars(
            select(Exps).filter(Exps.idexp.in_(exp_ids), Exps.status == 1)
        ).all()

        if not active_exps:
            flash(_("No active experiments available. Please contact an administrator."))
            return redirect(url_for("auth.login"))

        # Store credentials in session for experiment selection
        import secrets

        auth_token = secrets.token_urlsafe(32)
        session["exp_select_token"] = auth_token
        session["exp_select_user_id"] = user.id
        session["exp_select_remember"] = remember
        session["exp_select_experiments"] = [
            {
                "idexp": exp.idexp,
                "exp_name": exp.exp_name,
                "platform_type": exp.platform_type,
            }
            for exp in active_exps
        ]

        # Return to login page with experiment selection
        return render_template(
            "login/login.html",
            show_exp_selection=True,
            experiments=active_exps,
            auth_token=auth_token,
        )

    elif user.role == "admin" or user.role == "researcher":
        # Admin and researcher go to admin panel - they login with Admin_users, not User_mgmt
        login_user(user, remember=remember)
        return redirect(url_for("admin.dashboard"))

    elif user.role == "teacher":
        # A teacher works in the Training area only (see y_web.src.system.role_gate)
        try:
            home = url_for("training_modules.modules_page")
        except Exception:
            flash(
                _("The training area is not available. Please contact an administrator.")
            )
            return redirect(url_for("auth.login"))
        login_user(user, remember=remember)
        return redirect(home)

    else:
        flash(_("Invalid user role. Please contact an administrator."))
        return redirect(url_for("auth.login"))


def _signup_closed():
    flash(_("Registration is not available at the moment."))
    return redirect(url_for("auth.login"))


@auth.route("/signup", methods=["GET"])
def signup():
    """Self-registration page (only while the administrator has switched it on)."""
    from y_web.src import signup as signup_logic

    if not signup_logic.is_open():
        return _signup_closed()
    import secrets

    token = session["signup_token"] = secrets.token_urlsafe(24)
    return render_template(
        "login/register.html", offers=signup_logic.offers(), signup_token=token, form={}
    )


@auth.route("/signup", methods=["POST"])
def signup_post():
    """Create a participant account and join the chosen experiments / training modules."""
    import hmac

    from y_web.src import signup as signup_logic

    if not signup_logic.is_open():
        return _signup_closed()
    expected = session.get("signup_token") or ""
    supplied = request.form.get("signup_token") or ""
    if not expected or not hmac.compare_digest(expected, supplied):
        flash(_("Invalid or expired session. Please try again."))
        return redirect(url_for("auth.signup"))

    form = {
        "username": request.form.get("name", ""),
        "email": request.form.get("email", ""),
        "picks": request.form.getlist("pick"),
    }
    try:
        result = signup_logic.create_account(
            form["username"], form["email"], request.form.get("password", ""), form["picks"]
        )
    except signup_logic.SignupError as exc:
        return render_template(
            "login/register.html",
            offers=signup_logic.offers(),
            signup_token=expected,
            form=form,
            error=str(exc),
        )

    session.pop("signup_token", None)
    if result["failed"]:
        flash(
            _(
                "Your account has been created, but you could not be added to: %(names)s. Please contact an administrator.",
                names=", ".join(result["failed"]),
            )
        )
    else:
        flash(_("Your account has been created. You can now sign in."))
    return redirect(url_for("auth.login"))


@auth.route("/select_experiment", methods=["POST"])
def select_experiment():
    """
    Handle experiment selection for users with multiple active experiments.

    Returns:
        Redirect to the selected experiment's feed
    """
    exp_id = request.form.get("experiment_id")
    auth_token = request.form.get("auth_token")

    if not exp_id or not auth_token:
        flash(_("Invalid request."))
        return redirect(url_for("auth.login"))

    # Verify session token
    if "exp_select_token" not in session or session["exp_select_token"] != auth_token:
        flash(_("Invalid or expired session. Please log in again."))
        return redirect(url_for("auth.login"))

    user_id = session.get("exp_select_user_id")
    remember = session.get("exp_select_remember", False)

    # Clear session data
    session.pop("exp_select_token", None)
    session.pop("exp_select_user_id", None)
    session.pop("exp_select_remember", None)

    # Get user
    user = db.session.scalars(select(Admin_users).filter_by(id=user_id)).first()
    if not user:
        flash(_("User not found."))
        return redirect(url_for("auth.login"))

    username = str(getattr(user, "username", "") or "")
    email = str(getattr(user, "email", "") or "")
    password = str(getattr(user, "password", "") or "")

    # Verify user has access to this experiment
    user_exp = db.session.scalars(
        select(User_Experiment).filter_by(user_id=user.id, exp_id=int(exp_id))
    ).first()
    if not user_exp:
        flash(_("You do not have access to this experiment."))
        return redirect(url_for("auth.login"))

    # Get experiment
    exp = db.session.scalars(
        select(Exps).filter_by(idexp=int(exp_id), status=1)
    ).first()
    if not exp:
        flash(_("Experiment not found or not active."))
        return redirect(url_for("auth.login"))

    try:
        user_agent, _created = ensure_experiment_user(
            exp,
            user_id=user.id,
            username=username,
            email=email,
            password=password,
            joined_on=0,
            account_id=user.id,
        )
        if not user_agent:
            flash(_("User not found in experiment database."))
            return redirect(url_for("auth.login"))

        login_user(user_agent, remember=remember)
        session["platform_account_id"] = user.id

        # Redirect to onboarding — it will skip to feed if already completed
        return redirect(f"/{exp.idexp}/onboarding/{user_agent.id}")

    except Exception as e:
        flash(_("Error accessing experiment: %(error)s", error=str(e)))
        return redirect(url_for("auth.login"))


@auth.route("/logout")
@login_required
def logout():
    """
    Log out the current user and return to login page.

    Returns:
        Rendered login template after logout
    """

    try:
        from flask_login import current_user

        from y_web.src.telemetry import Telemetry

        telemetry = Telemetry()
        telemetry.log_event({"action": "logout", "data": {"role": current_user.role}})
    except Exception as e:
        print(f"Failed to log start event: {e}")

    logout_user()
    session.pop("platform_account_id", None)

    return render_template("login/login.html")
