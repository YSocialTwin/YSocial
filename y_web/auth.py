"""
Authentication and user management routes.

Handles user registration, login, and logout functionality for both
administrative users and experiment participants. Manages session creation
and validation for the YSocial platform.
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, login_required, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User_mgmt, Admin_users, Exps
from . import db

auth = Blueprint("auth", __name__)


@auth.route("/signup")
def signup():
    """Display user registration page."""
    return render_template("register.html")


@auth.route("/signup", methods=["POST"])
def signup_post():
    """
    Process user registration form submission.
    
    Creates new user accounts in both admin and experiment databases,
    with password hashing for security.
    
    Returns:
        Redirect to main feed on success, or back to signup on error
    """
    # code to validate and add user to database goes here

    email = request.form.get("email")
    name = request.form.get("name")
    password = request.form.get("password")

    user = Admin_users.query.filter_by(email=email).first()

    if (
        user
    ):  # if a user is found, we want to redirect back to signup page so user can try again
        flash("Email address already exists")
        return redirect(url_for("auth.signup_post"))

    # create a new user with the form data. Hash the password so the plaintext version isn't saved.
    new_user = Admin_users(
        email=email,
        username=name,
        password=generate_password_hash(password, method="pbkdf2:sha256"),
        role="user",
    )
    db.session.add(new_user)

    # check if experiment exists
    try:
        User_mgmt.query.first()
        new_user_exp = User_mgmt(
            email=email,
            username=name,
            password=generate_password_hash(password, method="pbkdf2:sha256"),
        )
        db.session.add(new_user_exp)
    except:
        flash("Server not ready. Please try again later.")
        return redirect(url_for("auth.signup_post"))

    db.session.commit()
    return redirect(url_for("main.feeed_logged"))


@auth.route("/login")
def login():
    """Display login page."""
    return render_template("login.html")


@auth.route("/login", methods=["POST"])
def login_post():
    """
    Process login form submission and authenticate user.
    
    Validates credentials, distinguishes between admin and regular users,
    and redirects to appropriate dashboard/feed based on role.
    
    Returns:
        Redirect to admin dashboard for admins, main feed for users,
        or back to login page on authentication failure
    """
    if request.method == "GET":
        return render_template("login.html")
    # login code goes here
    email = request.form.get("email")
    password = request.form.get("password")
    remember = True if request.form.get("remember") else False

    user = Admin_users.query.filter_by(email=email).first()

    # check if the user actually exists
    # take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user or not check_password_hash(user.password, password):
        flash("Please check your login details and try again.")
        return redirect(
            url_for("auth.login")
        )  # if the user doesn't exist or password is wrong, reload the page

    # if the above check passes, then we know the user has the right credentials
    if user.role != "admin":
        # get the agent for the simulation
        try:
            exp = Exps.query.filter_by(status=1).first()
            if exp is None:
                flash("No active experiment. Please load an experiment.")
                return redirect(request.referrer)

            user_agent = User_mgmt.query.filter_by(username=user.username).first()
            login_user(user_agent, remember=remember)
            return redirect(url_for("main.feeed_logged"))
        except:
            flash("Please check your login details and try again.")
            redirect(url_for("main.login"))

    else:
        try:
            _ = User_mgmt.query.first()
        except:
            flash("Server not ready. Please try again later.")
            redirect(url_for("main.login"))

        user_agent = User_mgmt.query.filter_by(username=user.username).first()
        login_user(user_agent, remember=remember)
        return redirect(url_for("admin.dashboard"))


@auth.route("/logout")
@login_required
def logout():
    """Log out the current user and return to login page."""
    logout_user()
    return render_template("login.html")
