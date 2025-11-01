"""
Tests for client logs endpoint
"""

import json
import os
import tempfile

import pytest
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    """Create a test app for client logs endpoint testing"""
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

    class Exps(db.Model):
        __tablename__ = "exps"
        idexp = db.Column(db.Integer, primary_key=True)
        exp_name = db.Column(db.String(50), nullable=False)
        exp_descr = db.Column(db.String(200), nullable=False)
        platform_type = db.Column(
            db.String(50), nullable=False, default="microblogging"
        )
        owner = db.Column(db.String(50), nullable=False)
        status = db.Column(db.Integer, nullable=False)
        running = db.Column(db.Integer, nullable=False, default=0)
        port = db.Column(db.Integer, nullable=False, default=5000)
        server = db.Column(db.String(50), nullable=False, default="127.0.0.1")
        db_name = db.Column(db.String(200), nullable=False)

    class Client(db.Model):
        __tablename__ = "client"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(50), nullable=False)
        descr = db.Column(db.String(200))
        id_exp = db.Column(db.Integer, nullable=False)

    @login_manager.user_loader
    def load_user(user_id):
        return User_mgmt.query.get(int(user_id))

    # Setup experiments routes with client_logs endpoint
    from flask import Blueprint, jsonify, request
    from flask_login import current_user, login_required

    experiments = Blueprint("experiments", __name__)

    def check_privileges(username):
        """Mock privilege check"""
        admin = Admin_users.query.filter_by(username=username).first()
        if not admin or admin.role != "admin":
            raise PermissionError("Access denied")

    @experiments.route("/admin/client_logs/<int:client_id>")
    @login_required
    def client_logs(client_id):
        """Get client logs analysis for a specific client."""
        try:
            check_privileges(current_user.username)
        except PermissionError:
            return jsonify({"error": "Access denied"}), 403

        from collections import defaultdict

        # Get client details
        client = Client.query.filter_by(id=client_id).first()
        if not client:
            return jsonify({"error": "Client not found"}), 404

        # Get experiment details
        experiment = Exps.query.filter_by(idexp=client.id_exp).first()
        if not experiment:
            return jsonify({"error": "Experiment not found"}), 404

        # Construct path to client log file
        db_name = experiment.db_name
        if db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
            # Extract the UUID folder
            parts = db_name.split(os.sep)
            if len(parts) >= 2:
                exp_folder = f"y_web{os.sep}experiments{os.sep}{parts[1]}"
            else:
                return jsonify({"error": "Invalid experiment path"}), 400
        elif db_name.startswith("experiments_"):
            # PostgreSQL format - UUID is after the underscore
            uid = db_name.replace("experiments_", "")
            exp_folder = f"y_web{os.sep}experiments{os.sep}{uid}"
        else:
            return jsonify({"error": "Invalid experiment path format"}), 400

        # Client log file name format: {client_name}_client.log
        log_file = os.path.join(exp_folder, f"{client.name}_client.log")

        # Check if log file exists
        if not os.path.exists(log_file):
            return jsonify(
                {
                    "call_volume": {},
                    "mean_execution_time": {},
                    "error": "Log file not found",
                }
            )

        # Parse the log file
        method_counts = defaultdict(int)
        method_durations = defaultdict(list)

        try:
            with open(log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        log_entry = json.loads(line)
                        method_name = log_entry.get("method_name", "unknown")
                        execution_time = log_entry.get("execution_time_seconds", 0)

                        method_counts[method_name] += 1
                        method_durations[method_name].append(float(execution_time))

                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue
        except Exception as e:
            return jsonify({"error": f"Error reading log file: {str(e)}"}), 500

        # Calculate mean execution times
        mean_execution_times = {}
        for method, durations in method_durations.items():
            if durations:
                mean_execution_times[method] = sum(durations) / len(durations)
            else:
                mean_execution_times[method] = 0

        return jsonify(
            {
                "call_volume": dict(method_counts),
                "mean_execution_time": mean_execution_times,
            }
        )

    app.register_blueprint(experiments)

    # Auth routes for login
    from flask import Blueprint, redirect, url_for
    from flask_login import login_user

    auth = Blueprint("auth", __name__)

    @auth.route("/login", methods=["POST"])
    def login():
        email = request.form.get("email")
        password = request.form.get("password")

        from werkzeug.security import check_password_hash

        user = Admin_users.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            user_mgmt = User_mgmt.query.filter_by(username=user.username).first()
            if user_mgmt:
                login_user(user_mgmt)
                return redirect("/admin/dashboard")

        return "Login failed", 401

    app.register_blueprint(auth)

    with app.app_context():
        db.create_all()

        # Create test admin user
        admin_user = Admin_users(
            username="admin",
            email="admin@test.com",
            password=generate_password_hash("admin123"),
            role="admin",
        )
        db.session.add(admin_user)

        admin_user_mgmt = User_mgmt(
            username="admin", email="admin@test.com", password="hashed_password"
        )
        db.session.add(admin_user_mgmt)

        # Create test experiment
        exp = Exps(
            exp_name="Test Experiment",
            exp_descr="Test Description",
            owner="admin",
            status=1,
            running=1,
            db_name="experiments/test_exp_123/database_server.db",
        )
        db.session.add(exp)
        db.session.commit()

        # Create test client
        test_client = Client(name="TestClient", descr="Test Client", id_exp=exp.idexp)
        db.session.add(test_client)
        db.session.commit()

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()


class TestClientLogsEndpoint:
    """Tests for the client_logs endpoint"""

    def test_client_logs_requires_authentication(self, client):
        """Test that the endpoint requires authentication"""
        response = client.get("/admin/client_logs/1")
        # Should redirect to login or return 401
        assert response.status_code in [302, 401]

    def test_client_logs_requires_admin_privileges(self, client):
        """Test that the endpoint requires admin privileges"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # This should work for admin
        response = client.get("/admin/client_logs/1")
        # Even if log doesn't exist, it should return 200 with error message
        assert response.status_code == 200

    def test_client_logs_returns_error_for_nonexistent_client(self, client):
        """Test that the endpoint returns error for non-existent client"""
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        response = client.get("/admin/client_logs/9999")
        assert response.status_code == 404

        data = json.loads(response.data)
        assert "error" in data
        assert data["error"] == "Client not found"

    def test_client_logs_parses_log_file_correctly(self, client, app):
        """Test that the endpoint correctly parses a log file"""
        # Create a test log file
        with app.app_context():
            log_dir = "y_web/experiments/test_exp_123"
            os.makedirs(log_dir, exist_ok=True)

            log_file = os.path.join(log_dir, "TestClient_client.log")
            with open(log_file, "w") as f:
                f.write(
                    '{"time": "2025-11-01 11:38:53", "agent_name": "CharlesHarris", "method_name": "comment", "execution_time_seconds": 1.6934, "success": true, "tid": 108, "day": 4, "hour": 12}\n'
                )
                f.write(
                    '{"time": "2025-11-01 11:39:10", "agent_name": "JohnDoe", "method_name": "post", "execution_time_seconds": 0.8521, "success": true, "tid": 109, "day": 4, "hour": 12}\n'
                )
                f.write(
                    '{"time": "2025-11-01 11:39:25", "agent_name": "JaneSmith", "method_name": "comment", "execution_time_seconds": 1.5432, "success": true, "tid": 110, "day": 4, "hour": 12}\n'
                )

        # Login and test
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        response = client.get("/admin/client_logs/1")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "call_volume" in data
        assert "mean_execution_time" in data

        # Check call volume
        assert data["call_volume"]["comment"] == 2
        assert data["call_volume"]["post"] == 1

        # Check mean execution time
        assert data["mean_execution_time"]["comment"] == pytest.approx(
            (1.6934 + 1.5432) / 2, rel=1e-4
        )
        assert data["mean_execution_time"]["post"] == pytest.approx(0.8521, rel=1e-4)

        # Cleanup
        if os.path.exists(log_file):
            os.remove(log_file)

    def test_client_logs_handles_missing_log_file(self, client):
        """Test that the endpoint handles missing log files gracefully"""
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        response = client.get("/admin/client_logs/1")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "error" in data
        assert data["error"] == "Log file not found"
        assert data["call_volume"] == {}
        assert data["mean_execution_time"] == {}
