"""
User management routes.

Administrative routes for managing admin users including viewing user lists,
creating new users, and updating user permissions and settings.
"""

import os
import re

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from y_web import db  # , app
from y_web.models import Admin_users, Exps, User_Experiment, User_mgmt
from y_web.utils.external_processes import get_llm_models
from y_web.utils.miscellanea import check_privileges, llm_backend_status, ollama_status

users = Blueprint("users", __name__)

# Validation pattern constants for consistency between server and client
PASSWORD_SPECIAL_CHARS_PATTERN = r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\\/;'`~]"
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


@users.route("/admin/users")
@login_required
def user_data():
    """
    Display user management page (admin only).

    Returns:
        Rendered user data template with available models and ollama status
    """
    # Check if user is admin (researchers should not access this page)
    user = Admin_users.query.filter_by(username=current_user.username).first()
    if user.role != "admin":
        flash("Access denied. This page is only accessible to administrators.", "error")
        return redirect(url_for("admin.dashboard"))

    check_privileges(current_user.username)
    llm_backend = llm_backend_status()
    models = (
        get_llm_models(llm_backend["url"])
        if llm_backend and llm_backend.get("url")
        else []
    )

    # Get all experiments for bulk assignment
    experiments = Exps.query.all()

    # Get all users for bulk assignment
    all_users = Admin_users.query.order_by(Admin_users.username).all()

    return render_template(
        "admin/users.html",
        m=models,
        llm_backend=llm_backend,
        experiments=experiments,
        all_users=all_users,
    )


@users.route("/admin/user_data")
@login_required
def users_data():
    """
    Display list of all admin users.

    Returns:
        Rendered users list template
    """
    query = Admin_users.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(
            db.or_(
                Admin_users.username.like(f"%{search}%"),
                Admin_users.email.like(f"%{search}%"),
            )
        )
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["username", "role", "email"]:
                name = "name"
            col = getattr(Admin_users, name)
            if direction == "-":
                col = col.desc()
            order.append(col)
        if order:
            query = query.order_by(*order)

    # pagination
    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        query = query.offset(start).limit(length)

    # response
    res = query.all()

    return {
        "data": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "password": user.password,
                "last_seen": user.last_seen,
                "role": user.role,
            }
            for user in res
        ],
        "total": total,
    }


@users.route("/admin/user_data", methods=["POST"])
@login_required
def update():
    """
    Update user information from form data.

    Returns:
        Redirect to users page
    """
    data = request.get_json()
    if "id" not in data:
        abort(400)
    user = Admin_users.query.get(data["id"])
    for field in ["username", "password", "email", "last_seen", "role"]:
        if field in data:
            setattr(user, field, data[field])
    db.session.commit()
    return "", 204


@users.route("/admin/user_details/<int:uid>")
@login_required
def user_details(uid):
    """Handle user details operation."""
    # Get current user
    current_admin_user = Admin_users.query.filter_by(
        username=current_user.username
    ).first()

    # Allow access if user is admin/researcher OR if user is viewing their own profile
    if (
        current_admin_user.role not in ["admin", "researcher"]
        and current_admin_user.id != uid
    ):
        flash("You do not have permission to view this page.", "error")
        return redirect(url_for("admin.dashboard"))

    # get user details
    user = Admin_users.query.filter_by(id=uid).first()

    # get experiments for the user
    experiments = Exps.query.filter_by(owner=user.username).all()

    # get all experiments
    all_experiments = Exps.query.all()

    # get user experiments
    joined_exp = User_Experiment.query.filter_by(user_id=uid).all()

    # get user experiments details for the ones joined
    joined_exp = [
        (j.exp_id, Exps.query.filter_by(idexp=j.exp_id).first().exp_name)
        for j in joined_exp
    ]

    llm_backend = llm_backend_status()
    models = get_llm_models(llm_backend["url"]) if llm_backend["url"] else []

    return render_template(
        "admin/user_details.html",
        user=user,
        user_experiments=experiments,
        all_experiments=all_experiments,
        user_experiments_joined=joined_exp,
        none=None,
        llm_backend=llm_backend,
        models=models,
        current_user_role=current_admin_user.role,
    )


@users.route("/admin/add_user", methods=["POST"])
@login_required
def add_user():
    """
    Create a new admin user from form data.

    Returns:
        Redirect to users page
    """
    check_privileges(current_user.username)

    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    role = request.form.get("role")
    llm = request.form.get("llm")
    profile_pic = request.form.get("profile_pic")

    user = Admin_users(
        username=username,
        email=email,
        password=generate_password_hash(password),
        role=role,
        llm=llm,
        profile_pic=profile_pic,
    )

    db.session.add(user)
    db.session.commit()

    return user_data()


@users.route("/admin/delete_user/<int:uid>")
@login_required
def delete_user(uid):
    """Delete user."""
    check_privileges(current_user.username)

    user = Admin_users.query.filter_by(id=uid).first()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("users.user_data"))

    # Check if user can be deleted (not self-delete)
    current_admin_user = Admin_users.query.filter_by(
        username=current_user.username
    ).first()
    if current_admin_user.id == uid:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("users.user_data"))

    try:
        # Delete associated User_Experiment records first
        User_Experiment.query.filter_by(user_id=uid).delete()

        # Delete the user
        db.session.delete(user)
        db.session.commit()
        flash("User deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting user: {str(e)}", "error")

    return redirect(url_for("users.user_data"))


@users.route("/admin/add_user_to_experiment", methods=["POST"])
@login_required
def add_user_to_experiment():
    """
    Associate a user with an experiment.

    Returns:
        Redirect to user details
    """
    check_privileges(current_user.username)

    user_id = request.form.get("user_id")
    experiment_id = request.form.get("experiment_id")

    if not user_id or not experiment_id:
        flash("User ID and Experiment ID are required.", "error")
        return redirect(url_for("users.user_data"))

    try:
        user_id = int(user_id)
        experiment_id = int(experiment_id)
    except ValueError:
        flash("Invalid User ID or Experiment ID.", "error")
        return redirect(url_for("users.user_data"))

    # get username
    user = Admin_users.query.filter_by(id=user_id).first()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("users.user_data"))

    # get experiment
    exp = Exps.query.filter_by(idexp=experiment_id).first()
    if not exp:
        flash("Experiment not found.", "error")
        return user_details(user_id)

    # Use the proper experiment context registration
    from y_web.experiment_context import (
        get_db_bind_key_for_exp,
        register_experiment_database,
    )

    # Register the experiment database if not already registered
    bind_key = get_db_bind_key_for_exp(experiment_id)
    if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
        register_experiment_database(current_app, experiment_id, exp.db_name)

    # Temporarily switch to experiment database to create user
    old_bind = current_app.config["SQLALCHEMY_BINDS"].get("db_exp")
    try:
        current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
            "SQLALCHEMY_BINDS"
        ][bind_key]

        # check if the user is present in the User_mgmt table
        user_exp = db.session.query(User_mgmt).filter_by(username=user.username).first()

        if user_exp is None:
            new_user = User_mgmt(
                email=user.email,
                username=user.username,
                password=user.password,
                user_type="user",
                leaning="neutral",
                age=0,
                recsys_type="default",
                language="en",
                frecsys_type="default",
                round_actions=1,
                toxicity="no",
                joined_on=0,
            )
            db.session.add(new_user)
            db.session.commit()

        # Add to User_Experiment if not present
        user_exp_record = (
            db.session.query(User_Experiment)
            .filter_by(user_id=user_id, exp_id=experiment_id)
            .first()
        )

        if user_exp_record is None:
            user_exp_record = User_Experiment(user_id=user_id, exp_id=experiment_id)
            db.session.add(user_exp_record)
            db.session.commit()
            flash(
                f"User '{user.username}' successfully added to experiment '{exp.exp_name}'.",
                "success",
            )
        else:
            flash(
                f"User '{user.username}' is already assigned to experiment '{exp.exp_name}'.",
                "info",
            )

    except Exception as e:
        db.session.rollback()
        flash(f"Error adding user to experiment: {str(e)}", "error")
    finally:
        # Restore original db_exp binding
        if old_bind:
            current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = old_bind

    return user_details(user_id)


@users.route("/admin/update_user_llm", methods=["POST"])
@login_required
def update_user_llm():
    """
    Update user's LLM configuration including model and server URL.

    Returns:
        Redirect to user details
    """
    user_id = request.form.get("user_id")

    # Validate user_id
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        flash("Invalid user ID.", "error")
        return redirect(url_for("admin.dashboard"))

    # Get current user
    current_admin_user = Admin_users.query.filter_by(
        username=current_user.username
    ).first()

    # Allow access if user is admin/researcher OR if user is updating their own LLM settings
    if (
        current_admin_user.role not in ["admin", "researcher"]
        and current_admin_user.id != user_id_int
    ):
        flash("You do not have permission to perform this action.", "error")
        return redirect(url_for("admin.dashboard"))
    llm = request.form.get("llm")
    llm_url = request.form.get("custom_llm_url", "").strip()

    user = Admin_users.query.filter_by(id=user_id_int).first()
    user.llm = llm
    user.llm_url = llm_url
    db.session.commit()

    return user_details(user_id_int)


@users.route("/admin/set_perspective_api_user", methods=["POST"])
@login_required
def set_perspective_api_user():
    """
    Set Perspective API key for a user.

    Returns:
        Redirect to user details
    """
    user_id = request.form.get("user_id")

    # Validate user_id
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        flash("Invalid user ID.", "error")
        return redirect(url_for("admin.dashboard"))

    # Get current user
    current_admin_user = Admin_users.query.filter_by(
        username=current_user.username
    ).first()

    # Allow access if user is admin/researcher OR if user is updating their own API key
    if (
        current_admin_user.role not in ["admin", "researcher"]
        and current_admin_user.id != user_id_int
    ):
        flash("You do not have permission to perform this action.", "error")
        return redirect(url_for("admin.dashboard"))
    perspective_api = request.form.get("perspective_api")

    user = Admin_users.query.filter_by(id=user_id_int).first()
    user.perspective_api = perspective_api
    db.session.commit()

    return user_details(user_id_int)


def validate_password(password):
    """
    Validate password complexity requirements.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one number
    - At least one special symbol

    Args:
        password: Password string to validate

    Returns:
        Tuple of (is_valid: bool, error_message: str or None)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"

    if not re.search(PASSWORD_SPECIAL_CHARS_PATTERN, password):
        return False, "Password must contain at least one special symbol"

    return True, None


def validate_email(email):
    """
    Validate email format.

    Args:
        email: Email string to validate

    Returns:
        Tuple of (is_valid: bool, error_message: str or None)
    """
    if not email or not email.strip():
        return False, "Email cannot be empty"

    if not re.match(EMAIL_PATTERN, email):
        return False, "Invalid email format"

    return True, None


@users.route("/admin/update_user_password", methods=["POST"])
@login_required
def update_user_password():
    """
    Update user password with validation.

    Password requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one number
    - At least one special symbol

    Returns:
        Redirect to user details
    """
    user_id = request.form.get("user_id")

    # Validate user_id
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        flash("Invalid user ID.", "error")
        return redirect(url_for("admin.dashboard"))

    # Get current user
    current_admin_user = Admin_users.query.filter_by(
        username=current_user.username
    ).first()

    # Allow access if user is admin/researcher OR if user is updating their own password
    if (
        current_admin_user.role not in ["admin", "researcher"]
        and current_admin_user.id != user_id_int
    ):
        flash("You do not have permission to perform this action.", "error")
        return redirect(url_for("admin.dashboard"))
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    # Check if passwords match
    if new_password != confirm_password:
        flash("Passwords do not match", "error")
        return user_details(user_id)

    # Validate password complexity
    is_valid, error_message = validate_password(new_password)
    if not is_valid:
        flash(error_message, "error")
        return user_details(user_id_int)

    # Update password
    user = Admin_users.query.filter_by(id=user_id_int).first()
    if not user:
        flash("User not found", "error")
        return redirect(url_for("users.user_data"))

    user.password = generate_password_hash(new_password)
    db.session.commit()

    flash("Password updated successfully", "success")
    return user_details(user_id_int)


@users.route("/admin/update_user_email", methods=["POST"])
@login_required
def update_user_email():
    """
    Update user email with validation.

    Returns:
        Redirect to user details
    """
    user_id = request.form.get("user_id")

    # Validate user_id
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        flash("Invalid user ID.", "error")
        return redirect(url_for("admin.dashboard"))

    # Get current user
    current_admin_user = Admin_users.query.filter_by(
        username=current_user.username
    ).first()

    # Allow access if user is admin/researcher OR if user is updating their own email
    if (
        current_admin_user.role not in ["admin", "researcher"]
        and current_admin_user.id != user_id_int
    ):
        flash("You do not have permission to perform this action.", "error")
        return redirect(url_for("admin.dashboard"))
    new_email = request.form.get("new_email")

    # Validate email format
    is_valid, error_message = validate_email(new_email)
    if not is_valid:
        flash(error_message, "error")
        return user_details(user_id_int)

    # Check if email is already taken by another user
    existing_user = Admin_users.query.filter_by(email=new_email).first()
    if existing_user and existing_user.id != user_id_int:
        flash("Email is already in use by another user", "error")
        return user_details(user_id_int)

    # Update email
    user = Admin_users.query.filter_by(id=user_id_int).first()
    if not user:
        flash("User not found", "error")
        return redirect(url_for("users.user_data"))

    user.email = new_email
    db.session.commit()

    flash("Email updated successfully", "success")
    return user_details(user_id_int)


@users.route("/admin/bulk_create_users", methods=["POST"])
@login_required
def bulk_create_users():
    """
    Bulk create multiple users from a list.

    Expected format: username,email,role per line (password will be auto-generated)
    or with password: username,email,role,password

    Returns:
        Redirect to users page with status message
    """
    check_privileges(current_user.username)

    users_data = request.form.get("users_data", "").strip()
    role_filter = request.form.get("role", "user")  # Default role for bulk creation

    if not users_data:
        flash("No user data provided.", "error")
        return redirect(url_for("users.user_data"))

    lines = users_data.split("\n")
    created = 0
    errors = []

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]

        if len(parts) < 3:
            errors.append(
                f"Line {i}: Invalid format (expected: username,email,role or username,email,role,password)"
            )
            continue

        username = parts[0]
        email = parts[1]
        role = parts[2] if len(parts) > 2 else role_filter
        password = (
            parts[3] if len(parts) > 3 else f"{username}123!"
        )  # Auto-generate password

        # Validate role
        if role not in ["admin", "researcher", "user"]:
            errors.append(
                f"Line {i}: Invalid role '{role}' (must be admin, researcher, or user)"
            )
            continue

        # Check if user already exists
        existing = Admin_users.query.filter(
            (Admin_users.username == username) | (Admin_users.email == email)
        ).first()

        if existing:
            errors.append(
                f"Line {i}: User '{username}' or email '{email}' already exists"
            )
            continue

        try:
            # Create user
            new_user = Admin_users(
                username=username,
                email=email,
                password=generate_password_hash(password),
                role=role,
                last_seen="",
            )
            db.session.add(new_user)
            created += 1
        except Exception as e:
            errors.append(f"Line {i}: Error creating user '{username}': {str(e)}")

    try:
        db.session.commit()
        if created > 0:
            flash(f"Successfully created {created} user(s).", "success")
        if errors:
            flash(
                f"Errors: {'; '.join(errors[:5])}"
                + (" ..." if len(errors) > 5 else ""),
                "warning",
            )
    except Exception as e:
        db.session.rollback()
        flash(f"Database error: {str(e)}", "error")

    return redirect(url_for("users.user_data"))


@users.route("/admin/bulk_assign_users", methods=["POST"])
@login_required
def bulk_assign_users():
    """
    Bulk assign users to an experiment.

    Returns:
        Redirect to users page with status message
    """
    check_privileges(current_user.username)

    user_ids = request.form.getlist("user_ids")
    exp_id = request.form.get("experiment_id")

    if not user_ids or not exp_id:
        flash("No users or experiment selected.", "error")
        return redirect(url_for("users.user_data"))

    try:
        exp_id = int(exp_id)
        exp = Exps.query.filter_by(idexp=exp_id).first()
        if not exp:
            flash("Experiment not found.", "error")
            return redirect(url_for("users.user_data"))

        # Use the proper experiment context registration
        from y_web.experiment_context import (
            get_db_bind_key_for_exp,
            register_experiment_database,
        )

        # Register the experiment database if not already registered
        bind_key = get_db_bind_key_for_exp(exp_id)
        if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
            register_experiment_database(current_app, exp_id, exp.db_name)

        # Temporarily switch to experiment database
        old_bind = current_app.config["SQLALCHEMY_BINDS"].get("db_exp")
        current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
            "SQLALCHEMY_BINDS"
        ][bind_key]

        assigned = 0
        errors = []

        try:
            for user_id_str in user_ids:
                try:
                    user_id = int(user_id_str)
                    user = Admin_users.query.filter_by(id=user_id).first()

                    if not user:
                        errors.append(f"User ID {user_id} not found")
                        continue

                    # Check if already assigned
                    existing = User_Experiment.query.filter_by(
                        user_id=user_id, exp_id=exp_id
                    ).first()

                    if existing:
                        errors.append(
                            f"User '{user.username}' already assigned to this experiment"
                        )
                        continue

                    # Ensure user exists in experiment database (User_mgmt)
                    user_agent = User_mgmt.query.filter_by(
                        username=user.username
                    ).first()
                    if not user_agent:
                        new_user_mgmt = User_mgmt(
                            email=user.email,
                            username=user.username,
                            password=user.password,  # Already hashed
                            user_type="user",
                            leaning="neutral",
                            age=0,
                            recsys_type="default",
                            language="en",
                            frecsys_type="default",
                            round_actions=1,
                            toxicity="no",
                            joined_on=0,
                        )
                        db.session.add(new_user_mgmt)
                        db.session.commit()

                    # Create User_Experiment record
                    user_exp = User_Experiment(user_id=user_id, exp_id=exp_id)
                    db.session.add(user_exp)
                    db.session.commit()

                    assigned += 1
                except ValueError:
                    errors.append(f"Invalid user ID: {user_id_str}")
                except Exception as e:
                    db.session.rollback()
                    errors.append(f"Error assigning user {user_id_str}: {str(e)}")

            if assigned > 0:
                flash(
                    f"Successfully assigned {assigned} user(s) to experiment '{exp.exp_name}'.",
                    "success",
                )
            if errors:
                flash(
                    f"Errors: {'; '.join(errors[:5])}"
                    + (" ..." if len(errors) > 5 else ""),
                    "warning",
                )

        finally:
            # Restore original db_exp binding
            if old_bind:
                current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = old_bind

    except Exception as e:
        flash(f"Error during bulk assignment: {str(e)}", "error")

    return redirect(url_for("users.user_data"))


@users.route("/admin/update_telemetry_preference", methods=["POST"])
@login_required
def update_telemetry_preference():
    """
    Update user's telemetry preference (admin only).

    Returns:
        Redirect to user details page
    """
    user_id = request.form.get("user_id")

    # Validate user_id
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        flash("Invalid user ID.", "error")
        return redirect(url_for("admin.dashboard"))

    # Check if user is admin
    current_admin_user = Admin_users.query.filter_by(
        username=current_user.username
    ).first()

    if not current_admin_user or current_admin_user.role != "admin":
        flash(
            "Access denied. Only administrators can modify telemetry settings.", "error"
        )
        return redirect(url_for("admin.dashboard"))

    # Only allow admins to update their own telemetry settings
    if current_admin_user.id != user_id_int:
        flash("You can only modify your own telemetry settings.", "error")
        return redirect(url_for("users.user_details", uid=user_id_int))

    # Get telemetry preference from form
    telemetry_enabled = request.form.get("telemetry_enabled") == "1"

    # Update user's telemetry preference
    user = Admin_users.query.filter_by(id=user_id_int).first()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("users.user_data"))

    user.telemetry_enabled = telemetry_enabled
    db.session.commit()

    flash(
        f"Telemetry {'enabled' if telemetry_enabled else 'disabled'} successfully.",
        "success",
    )
    return redirect(url_for("users.user_details", uid=user_id_int))


@users.route("/admin/check_for_updates", methods=["POST"])
@login_required
def check_for_updates_route():
    """
    Manually trigger a check for YSocial updates (admin only).

    Returns:
        Redirect to user details page with status message
    """
    # Check if user is admin
    current_admin_user = Admin_users.query.filter_by(
        username=current_user.username
    ).first()

    if not current_admin_user or current_admin_user.role != "admin":
        flash("Access denied. Only administrators can check for updates.", "error")
        return redirect(url_for("admin.dashboard"))

    try:
        from y_web.utils.check_release import update_release_info_in_db

        has_update, release_info = update_release_info_in_db()

        if has_update:
            flash(
                f"New version available: {release_info.get('release_name')} (v{release_info.get('latest_version')})",
                "success",
            )
        else:
            flash("Your YSocial installation is up to date.", "info")
    except Exception as e:
        flash(f"Error checking for updates: {str(e)}", "error")

    # Redirect back to the user details page
    return redirect(url_for("users.user_details", uid=current_admin_user.id))


@users.route("/admin/mark_blog_post_read/<int:post_id>", methods=["POST"])
@login_required
def mark_blog_post_read(post_id):
    """
    Mark a blog post as read.

    This endpoint is called when a user dismisses a blog post banner
    or clicks on the blog post link.

    Args:
        post_id: ID of the blog post to mark as read

    Returns:
        JSON response indicating success or error
    """
    from flask import jsonify

    from y_web.models import BlogPost

    # Check if user is admin using existing check_privileges helper
    if not check_privileges(current_user.username):
        return jsonify({"error": "Access denied"}), 403

    try:
        blog_post = BlogPost.query.get_or_404(post_id)
        blog_post.is_read = True
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
