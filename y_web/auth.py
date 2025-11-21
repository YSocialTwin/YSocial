"""
Authentication and user management routes.

Handles user login and logout functionality for administrative users,
researchers, and experiment participants. Manages session creation
and validation for the YSocial platform.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from . import db
from .models import Admin_users, Exps, User_Experiment, User_mgmt

auth = Blueprint("auth", __name__)


@auth.route("/login")
def login():
    """
    Display login page.

    Returns:
        Rendered login template
    """
    return render_template("login.html")


@auth.route("/login", methods=["POST"])
def login_post():
    """
    Process login form submission and authenticate user.

    Validates credentials and redirects based on role:
    - admin/researcher: admin dashboard
    - user: experiment selection page (if multiple) or direct to feed

    Returns:
        Redirect to appropriate page based on role, or back to login on failure
    """
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email")
    password = request.form.get("password")
    remember = True if request.form.get("remember") else False

    user = Admin_users.query.filter_by(email=email).first()

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user or not check_password_hash(user.password, password):
        flash("Please check your login details and try again.")
        return redirect(url_for("auth.login"))

        # Log service start event
    try:
        from y_web.telemetry import Telemetry

        telemetry = Telemetry()
        telemetry.log_event({
            "action": "login",
            "data": {"role": user.role}
        })
    except Exception as e:
        print(f"Failed to log start event: {e}")

    # Handle different roles
    if user.role == "user":
        # Regular users: need to select experiment
        # Do NOT log them in yet - just show experiment selection
        # Get experiments this user is assigned to
        user_experiments = User_Experiment.query.filter_by(user_id=user.id).all()

        if not user_experiments:
            flash(
                "You are not assigned to any experiments. Please contact an administrator."
            )
            return redirect(url_for("auth.login"))

        # Get active experiments from the user's assigned experiments
        exp_ids = [ue.exp_id for ue in user_experiments]
        active_exps = Exps.query.filter(Exps.idexp.in_(exp_ids), Exps.status == 1).all()

        if not active_exps:
            flash("No active experiments available. Please contact an administrator.")
            return redirect(url_for("auth.login"))

        # Store credentials in session for experiment selection
        import secrets

        from flask import session

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
            "login.html",
            show_exp_selection=True,
            experiments=active_exps,
            auth_token=auth_token,
        )

    elif user.role == "admin" or user.role == "researcher":
        # Admin and researcher go to admin panel - they login with Admin_users, not User_mgmt
        login_user(user, remember=remember)
        return redirect(url_for("admin.dashboard"))

    else:
        flash("Invalid user role. Please contact an administrator.")
        return redirect(url_for("auth.login"))


@auth.route("/select_experiment", methods=["POST"])
def select_experiment():
    """
    Handle experiment selection for users with multiple active experiments.

    Returns:
        Redirect to the selected experiment's feed
    """
    from flask import session

    exp_id = request.form.get("experiment_id")
    auth_token = request.form.get("auth_token")

    if not exp_id or not auth_token:
        flash("Invalid request.")
        return redirect(url_for("auth.login"))

    # Verify session token
    if "exp_select_token" not in session or session["exp_select_token"] != auth_token:
        flash("Invalid or expired session. Please log in again.")
        return redirect(url_for("auth.login"))

    user_id = session.get("exp_select_user_id")
    remember = session.get("exp_select_remember", False)

    # Clear session data
    session.pop("exp_select_token", None)
    session.pop("exp_select_user_id", None)
    session.pop("exp_select_remember", None)

    # Get user
    user = Admin_users.query.filter_by(id=user_id).first()
    if not user:
        flash("User not found.")
        return redirect(url_for("auth.login"))

    # Verify user has access to this experiment
    user_exp = User_Experiment.query.filter_by(
        user_id=user.id, exp_id=int(exp_id)
    ).first()
    if not user_exp:
        flash("You do not have access to this experiment.")
        return redirect(url_for("auth.login"))

    # Get experiment
    exp = Exps.query.filter_by(idexp=int(exp_id), status=1).first()
    if not exp:
        flash("Experiment not found or not active.")
        return redirect(url_for("auth.login"))

    try:
        # Use the proper experiment context registration
        from flask import current_app

        from y_web.experiment_context import (
            get_db_bind_key_for_exp,
            register_experiment_database,
        )

        # Register the experiment database if not already registered
        bind_key = get_db_bind_key_for_exp(int(exp_id))
        if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
            register_experiment_database(current_app, int(exp_id), exp.db_name)

        # Temporarily switch to experiment database to get user
        old_bind = current_app.config["SQLALCHEMY_BINDS"].get("db_exp")
        current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
            "SQLALCHEMY_BINDS"
        ][bind_key]

        try:
            user_agent = User_mgmt.query.filter_by(username=user.username).first()
            if not user_agent:
                flash("User not found in experiment database.")
                return redirect(url_for("auth.login"))

            login_user(user_agent, remember=remember)

            # Redirect to appropriate feed
            if exp.platform_type == "microblogging":
                return redirect(f"/{exp.idexp}/feed/{user_agent.id}/feed/rf/1")
            elif exp.platform_type == "forum":
                return redirect(f"/{exp.idexp}/rfeed/{user_agent.id}/rfeed/rf/1")
            else:
                flash("Unknown platform type.")
                return redirect(url_for("auth.login"))
        finally:
            # Restore original db_exp binding
            if old_bind:
                current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = old_bind

    except Exception as e:
        flash(f"Error accessing experiment: {str(e)}")
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
        from y_web.telemetry import Telemetry
        from flask_login import current_user

        telemetry = Telemetry()
        telemetry.log_event({
            "action": "logout",
            "data": {"role": current_user.role}
        })
    except Exception as e:
        print(f"Failed to log start event: {e}")

    logout_user()

    return render_template("login.html")
