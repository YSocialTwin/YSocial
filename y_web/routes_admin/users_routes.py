"""
User management routes.

Administrative routes for managing admin users including viewing user lists,
creating new users, and updating user permissions and settings.
"""

import os

from flask import Blueprint, abort, current_app, render_template, request
from flask_login import current_user, login_required

from y_web import db  # , app
from y_web.models import Admin_users, Exps, User_Experiment, User_mgmt
from y_web.utils.external_processes import get_llm_models
from y_web.utils.miscellanea import check_privileges, llm_backend_status, ollama_status

users = Blueprint("users", __name__)


@users.route("/admin/users")
@login_required
def user_data():
    """
    Display user management page.

    Returns:
        Rendered user data template with available models and ollama status
    """
    check_privileges(current_user.username)
    llm_backend = llm_backend_status()
    models = get_llm_models(llm_backend["url"]) if llm_backend and llm_backend.get("url") else []
    ollamas = ollama_status()
    return render_template("admin/users.html", m=models, ollamas=ollamas)


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
    check_privileges(current_user.username)

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
    ollamas = ollama_status()

    return render_template(
        "admin/user_details.html",
        user=user,
        user_experiments=experiments,
        all_experiments=all_experiments,
        user_experiments_joined=joined_exp,
        none=None,
        llm_backend=llm_backend,
        models=models,
        ollamas=ollamas,
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
        password=password,
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
    db.session.delete(user)
    db.session.commit()

    return user_data()


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

    # get username
    user = Admin_users.query.filter_by(id=user_id).first()
    # get experiment
    exp = Exps.query.filter_by(idexp=experiment_id).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # app.config["SQLALCHEMY_BINDS"]["db_exp"] = f"sqlite:///{BASE_DIR}/{exp.db_name}"

    current_app.config["SQLALCHEMY_BINDS"][
        "db_exp"
    ] = f"sqlite:///{BASE_DIR}/{exp.db_name}"

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
        )
        db.session.add(new_user)
        db.session.commit()

        # ad to experiment if not present
        user_exp = (
            db.session.query(User_Experiment)
            .filter_by(user_id=user_id, exp_id=experiment_id)
            .first()
        )

        if user_exp is None:
            user_exp = User_Experiment(user_id=user_id, exp_id=experiment_id)
            db.session.add(user_exp)
            db.session.commit()

    db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})
    db.session.query(Exps).filter_by(db_name=exp.db_name).update({Exps.status: 1})
    db.session.commit()

    return user_details(user_id)


@users.route("/admin/update_user_llm", methods=["POST"])
@login_required
def update_user_llm():
    """
    Update user's LLM configuration including model and server URL.

    Returns:
        Redirect to user details
    """
    check_privileges(current_user.username)

    user_id = request.form.get("user_id")
    llm = request.form.get("llm")
    llm_url = request.form.get("custom_llm_url", "").strip()

    user = Admin_users.query.filter_by(id=user_id).first()
    user.llm = llm
    user.llm_url = llm_url
    db.session.commit()

    return user_details(user_id)


@users.route("/admin/set_perspective_api_user", methods=["POST"])
@login_required
def set_perspective_api_user():
    """
    Set Perspective API key for a user.

    Returns:
        Redirect to user details
    """
    check_privileges(current_user.username)

    user_id = request.form.get("user_id")
    perspective_api = request.form.get("perspective_api")

    user = Admin_users.query.filter_by(id=user_id).first()
    user.perspective_api = perspective_api
    db.session.commit()

    return user_details(user_id)
