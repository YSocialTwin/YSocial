"""
Tests for researcher and admin login functionality.

This test verifies that users with 'researcher' and 'admin' roles can log in
directly using their Admin_users credentials without needing an entry in User_mgmt.
"""

import os
import tempfile

import pytest
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    """Create a test app with minimal configuration for researcher login testing"""
    app = Flask(__name__)
    db_fd1, db_path1 = tempfile.mkstemp()
    db_fd2, db_path2 = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path1}",
            "SQLALCHEMY_BINDS": {
                "db_admin": f"sqlite:///{db_path1}",
                "db_exp": f"sqlite:///{db_path2}",
            },
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"check_same_thread": False}},
        }
    )

    db = SQLAlchemy(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Define models for testing
    class Admin_users(db.Model):
        __bind_key__ = "db_admin"
        __tablename__ = "admin_users"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False, unique=True)
        email = db.Column(db.String(100), nullable=False, unique=True)
        password = db.Column(db.String(200), nullable=False)
        role = db.Column(db.String(20), default="user")
        last_seen = db.Column(db.String(30), nullable=False, default="")

        def is_authenticated(self):
            return True

        def is_active(self):
            return True

        def is_anonymous(self):
            return False

        def get_id(self):
            """Return user ID with 'admin_' prefix for Flask-Login."""
            return f"admin_{self.id}"

    class User_mgmt(db.Model):
        __bind_key__ = "db_exp"
        __tablename__ = "user_mgmt"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)
        password = db.Column(db.String(200), nullable=False)
        joined_on = db.Column(db.Integer, nullable=False, default=1234567890)

        def is_authenticated(self):
            return True

        def is_active(self):
            return True

        def is_anonymous(self):
            return False

        def get_id(self):
            return str(self.id)

    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID, supporting both Admin_users and User_mgmt."""
        user_id_str = str(user_id)
        if user_id_str.startswith("admin_"):
            admin_id = int(user_id_str.replace("admin_", ""))
            return Admin_users.query.get(admin_id)
        else:
            return User_mgmt.query.get(int(user_id))

    # Create auth blueprint
    from flask import (
        Blueprint,
        flash,
        redirect,
        render_template_string,
        request,
        url_for,
    )
    from flask_login import current_user, login_user, logout_user

    auth = Blueprint("auth", __name__)

    @auth.route("/login")
    def login():
        return render_template_string(
            """
        <form method="post">
            <input name="email" type="email" placeholder="Email" required>
            <input name="password" type="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        """
        )

    @auth.route("/login", methods=["POST"])
    def login_post():
        email = request.form.get("email")
        password = request.form.get("password")
        remember = True if request.form.get("remember") else False

        from werkzeug.security import check_password_hash

        user = Admin_users.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash("Please check your login details and try again.")
            return redirect(url_for("auth.login"))

        # Handle different roles
        if user.role == "user":
            # Regular users need User_mgmt entry
            user_agent = User_mgmt.query.filter_by(username=user.username).first()
            if user_agent:
                login_user(user_agent, remember=remember)
                return "Login successful - regular user"
            else:
                flash("User account not found.")
                return redirect(url_for("auth.login"))

        elif user.role == "admin" or user.role == "researcher":
            # Admin and researcher login directly with Admin_users
            login_user(user, remember=remember)
            return "Login successful - admin/researcher"

        else:
            flash("Invalid user role.")
            return redirect(url_for("auth.login"))

    @auth.route("/dashboard")
    def dashboard():
        from flask_login import login_required

        @login_required
        def protected():
            return f"Dashboard - Current user: {current_user.username}, Role: {current_user.role if hasattr(current_user, 'role') else 'N/A'}"

        return protected()

    @auth.route("/logout")
    def logout():
        logout_user()
        return "Logged out"

    app.register_blueprint(auth)

    with app.app_context():
        db.create_all()

        # Create test users
        admin_user = Admin_users(
            username="admin",
            email="admin@test.com",
            password=generate_password_hash("admin123"),
            role="admin",
            last_seen="",
        )
        db.session.add(admin_user)

        researcher_user = Admin_users(
            username="researcher1",
            email="researcher@test.com",
            password=generate_password_hash("research123"),
            role="researcher",
            last_seen="",
        )
        db.session.add(researcher_user)

        regular_user = Admin_users(
            username="testuser",
            email="test@test.com",
            password=generate_password_hash("test123"),
            role="user",
            last_seen="",
        )
        db.session.add(regular_user)

        # Create User_mgmt for regular user only
        user_mgmt_regular = User_mgmt(
            username="testuser",
            email="test@test.com",
            password=generate_password_hash("test123"),
            joined_on=1234567890,
        )
        db.session.add(user_mgmt_regular)

        db.session.commit()

    yield app

    os.close(db_fd1)
    os.unlink(db_path1)
    os.close(db_fd2)
    os.unlink(db_path2)


@pytest.fixture
def client(app):
    """Test client for the app"""
    return app.test_client()


class TestResearcherLogin:
    """Test researcher login functionality"""

    def test_researcher_login_success(self, client):
        """Test that researcher can log in without User_mgmt entry"""
        response = client.post(
            "/login",
            data={"email": "researcher@test.com", "password": "research123"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Login successful - admin/researcher" in response.data

    def test_admin_login_success(self, client):
        """Test that admin can log in without User_mgmt entry"""
        response = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )
        assert response.status_code == 200
        assert b"Login successful - admin/researcher" in response.data

    def test_researcher_login_invalid_password(self, client):
        """Test researcher login with invalid password"""
        response = client.post(
            "/login",
            data={"email": "researcher@test.com", "password": "wrongpassword"},
        )
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_regular_user_login_still_works(self, client):
        """Test that regular user login still works correctly"""
        response = client.post(
            "/login", data={"email": "test@test.com", "password": "test123"}
        )
        assert response.status_code == 200
        assert b"Login successful - regular user" in response.data

    def test_researcher_session_persistence(self, client):
        """Test that researcher session persists correctly"""
        # Login as researcher
        login_response = client.post(
            "/login",
            data={"email": "researcher@test.com", "password": "research123"},
        )
        assert login_response.status_code == 200
        assert b"Login successful - admin/researcher" in login_response.data

        # Access protected route (should work because logged in)
        dashboard_response = client.get("/dashboard")
        assert dashboard_response.status_code == 200
        assert b"researcher1" in dashboard_response.data
        assert b"researcher" in dashboard_response.data

    def test_admin_session_persistence(self, client):
        """Test that admin session persists correctly"""
        # Login as admin
        login_response = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )
        assert login_response.status_code == 200

        # Access protected route
        dashboard_response = client.get("/dashboard")
        assert dashboard_response.status_code == 200
        assert b"admin" in dashboard_response.data
