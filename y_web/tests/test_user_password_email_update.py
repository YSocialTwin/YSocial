"""
Tests for user password and email update functionality
"""

import os
import tempfile

import pytest
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


@pytest.fixture
def app():
    """Create a test app for user password and email update testing"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "WTF_CSRF_ENABLED": False,
        }
    )

    db = SQLAlchemy(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Define models for testing
    class Admin_users(db.Model):
        __tablename__ = "admin_users"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)
        password = db.Column(db.String(200), nullable=False)
        role = db.Column(db.String(20), default="user")
        last_seen = db.Column(db.String(30), default="")
        llm = db.Column(db.String(50), default="")
        llm_url = db.Column(db.String(200), default="")
        profile_pic = db.Column(db.String(400), default="")
        perspective_api = db.Column(db.String(300), default=None)

        def is_authenticated(self):
            return True

        def is_active(self):
            return True

        def is_anonymous(self):
            return False

        def get_id(self):
            return str(self.id)

    class User_mgmt(db.Model):
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
        return User_mgmt.query.get(int(user_id))

    # Create users blueprint with password and email update functionality
    from flask import Blueprint, flash, redirect, render_template_string, request
    from flask_login import current_user, login_required
    import re

    users = Blueprint("users", __name__)

    def check_privileges(username):
        """Mock privilege check function"""
        user = Admin_users.query.filter_by(username=username).first()
        if not user or user.role != "admin":
            raise PermissionError("Access denied")

    def validate_password(password):
        """Validate password complexity requirements."""
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"
        
        if not re.search(r"\d", password):
            return False, "Password must contain at least one number"
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\\/;'`~]", password):
            return False, "Password must contain at least one special symbol"
        
        return True, None

    def validate_email(email):
        """Validate email format."""
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        
        if not email or not email.strip():
            return False, "Email cannot be empty"
        
        if not re.match(email_pattern, email):
            return False, "Invalid email format"
        
        return True, None

    @users.route("/admin/user_details/<int:uid>")
    @login_required
    def user_details(uid):
        try:
            check_privileges(current_user.username)
        except PermissionError:
            return "Access denied", 403

        user = Admin_users.query.filter_by(id=uid).first()
        if not user:
            return "User not found", 404

        # Get flashed messages for the test
        messages = []
        with app.app_context():
            from flask import get_flashed_messages
            messages = get_flashed_messages(with_categories=True)

        return render_template_string(
            """
        <h1>User Details: {{ user.username }}</h1>
        <p>Email: {{ user.email }}</p>
        {% for category, message in messages %}
        <div class="flash-{{ category }}">{{ message }}</div>
        {% endfor %}
        """,
            user=user,
            messages=messages,
        )

    @users.route("/admin/update_user_password", methods=["POST"])
    @login_required
    def update_user_password():
        try:
            check_privileges(current_user.username)
        except PermissionError:
            return "Access denied", 403

        user_id = request.form.get("user_id")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
            flash("Passwords do not match", "error")
            return user_details(user_id)

        is_valid, error_message = validate_password(new_password)
        if not is_valid:
            flash(error_message, "error")
            return user_details(user_id)

        user = Admin_users.query.filter_by(id=user_id).first()
        if not user:
            flash("User not found", "error")
            return user_details(user_id)

        user.password = generate_password_hash(new_password)
        db.session.commit()

        flash("Password updated successfully", "success")
        return user_details(user_id)

    @users.route("/admin/update_user_email", methods=["POST"])
    @login_required
    def update_user_email():
        try:
            check_privileges(current_user.username)
        except PermissionError:
            return "Access denied", 403

        user_id = request.form.get("user_id")
        new_email = request.form.get("new_email")

        is_valid, error_message = validate_email(new_email)
        if not is_valid:
            flash(error_message, "error")
            return user_details(user_id)

        existing_user = Admin_users.query.filter_by(email=new_email).first()
        if existing_user and existing_user.id != int(user_id):
            flash("Email is already in use by another user", "error")
            return user_details(user_id)

        user = Admin_users.query.filter_by(id=user_id).first()
        if not user:
            flash("User not found", "error")
            return user_details(user_id)

        user.email = new_email
        db.session.commit()

        flash("Email updated successfully", "success")
        return user_details(user_id)

    app.register_blueprint(users)

    # Auth blueprint for login testing
    from flask import Blueprint
    from flask_login import login_user

    auth = Blueprint("auth", __name__)

    @auth.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email")
            password = request.form.get("password")

            from werkzeug.security import check_password_hash

            user = Admin_users.query.filter_by(email=email).first()

            if user and check_password_hash(user.password, password):
                user_mgmt = User_mgmt.query.filter_by(username=user.username).first()
                if user_mgmt:
                    login_user(user_mgmt)
                    return redirect("/admin/user_details/1")

            return "Login failed", 401

        return render_template_string(
            """
        <form method="post">
            <input name="email" type="email" required>
            <input name="password" type="password" required>
            <button type="submit">Login</button>
        </form>
        """
        )

    app.register_blueprint(auth)

    with app.app_context():
        db.create_all()

        # Create test admin user
        admin_user = Admin_users(
            username="admin",
            email="admin@test.com",
            password=generate_password_hash("admin123"),
            role="admin",
            last_seen="2024-01-01",
        )
        db.session.add(admin_user)

        admin_user_mgmt = User_mgmt(
            username="admin",
            email="admin@test.com",
            password=generate_password_hash("admin123"),
            joined_on=1234567890,
        )
        db.session.add(admin_user_mgmt)

        # Create test user
        test_user = Admin_users(
            username="testuser",
            email="testuser@test.com",
            password=generate_password_hash("Test123!"),
            role="user",
            last_seen="2024-01-01",
        )
        db.session.add(test_user)

        db.session.commit()

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Test client for the app"""
    return app.test_client()


class TestPasswordUpdate:
    """Test password update functionality"""

    def test_password_update_successful(self, client):
        """Test successful password update"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Update password with valid input
        response = client.post(
            "/admin/update_user_password",
            data={
                "user_id": "1",
                "new_password": "NewPass123!",
                "confirm_password": "NewPass123!",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Password updated successfully" in response.data

    def test_password_update_mismatch(self, client):
        """Test password update with mismatched passwords"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Try to update with mismatched passwords
        response = client.post(
            "/admin/update_user_password",
            data={
                "user_id": "1",
                "new_password": "NewPass123!",
                "confirm_password": "DifferentPass123!",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Passwords do not match" in response.data

    def test_password_too_short(self, client):
        """Test password validation: too short"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Try with short password
        response = client.post(
            "/admin/update_user_password",
            data={
                "user_id": "1",
                "new_password": "Pass1!",
                "confirm_password": "Pass1!",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"at least 8 characters" in response.data

    def test_password_no_uppercase(self, client):
        """Test password validation: no uppercase letter"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Try with no uppercase
        response = client.post(
            "/admin/update_user_password",
            data={
                "user_id": "1",
                "new_password": "password123!",
                "confirm_password": "password123!",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"uppercase letter" in response.data

    def test_password_no_number(self, client):
        """Test password validation: no number"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Try with no number
        response = client.post(
            "/admin/update_user_password",
            data={
                "user_id": "1",
                "new_password": "Password!",
                "confirm_password": "Password!",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"one number" in response.data

    def test_password_no_symbol(self, client):
        """Test password validation: no special symbol"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Try with no symbol
        response = client.post(
            "/admin/update_user_password",
            data={
                "user_id": "1",
                "new_password": "Password123",
                "confirm_password": "Password123",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"special symbol" in response.data


class TestEmailUpdate:
    """Test email update functionality"""

    def test_email_update_successful(self, client):
        """Test successful email update"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Update email with valid input
        response = client.post(
            "/admin/update_user_email",
            data={"user_id": "1", "new_email": "newemail@test.com"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Email updated successfully" in response.data
        assert b"newemail@test.com" in response.data

    def test_email_update_invalid_format(self, client):
        """Test email update with invalid format"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Try with invalid email
        response = client.post(
            "/admin/update_user_email",
            data={"user_id": "1", "new_email": "not-an-email"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Invalid email format" in response.data

    def test_email_update_empty(self, client):
        """Test email update with empty email"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Try with empty email
        response = client.post(
            "/admin/update_user_email",
            data={"user_id": "1", "new_email": ""},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Email cannot be empty" in response.data

    def test_email_update_already_exists(self, client):
        """Test email update with email already in use"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Try to update to an email that already exists (testuser's email)
        response = client.post(
            "/admin/update_user_email",
            data={"user_id": "1", "new_email": "testuser@test.com"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"already in use" in response.data
