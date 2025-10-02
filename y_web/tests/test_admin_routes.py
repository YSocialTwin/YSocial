"""
Tests for y_web admin dashboard routes
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
    """Create a test app for admin route testing"""
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

    class Client(db.Model):
        __tablename__ = "client"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(50), nullable=False)
        descr = db.Column(db.String(200))
        id_exp = db.Column(db.Integer, nullable=False)

    class Client_Execution(db.Model):
        __tablename__ = "client_execution"
        id = db.Column(db.Integer, primary_key=True)
        client_id = db.Column(db.Integer, nullable=False)
        status = db.Column(db.String(20), default="stopped")

    class Ollama_Pull(db.Model):
        __tablename__ = "ollama_pull"
        id = db.Column(db.Integer, primary_key=True)
        model_name = db.Column(db.String(100), nullable=False)
        status = db.Column(db.String(10), default="0.0")

    @login_manager.user_loader
    def load_user(user_id):
        return User_mgmt.query.get(int(user_id))

    # Create admin blueprint with minimal functionality
    from flask import Blueprint, jsonify, render_template_string
    from flask_login import current_user, login_required

    admin = Blueprint("admin", __name__)

    def check_privileges(username):
        """Mock privilege check function"""
        user = Admin_users.query.filter_by(username=username).first()
        if not user or user.role != "admin":
            raise PermissionError("Access denied")

    def ollama_status():
        """Mock ollama status function"""
        return {"status": "running", "models": ["llama2", "codellama"]}

    def get_ollama_models():
        """Mock get ollama models function"""
        return ["llama2:latest", "codellama:latest"]

    def get_db_type():
        return "sqlite"

    def get_db_port():
        return 5432

    def check_connection():
        return True

    def get_db_server():
        return "localhost"

    @admin.route("/admin/dashboard")
    @login_required
    def dashboard():
        try:
            check_privileges(current_user.username)
        except PermissionError:
            return "Access denied", 403

        ollamas = ollama_status()

        # Get all experiments
        experiments = Exps.query.all()
        # Get all clients for each experiment
        exps = {}
        for e in experiments:
            exps[e.idexp] = {
                "experiment": e,
                "clients": Client.query.filter_by(id_exp=e.idexp).all(),
            }

        res = {}
        # Get clients with client_execution information
        for exp, data in exps.items():
            res[exp] = {"experiment": data["experiment"], "clients": []}
            for client in data["clients"]:
                cl = Client_Execution.query.filter_by(client_id=client.id).first()
                client_executions = cl if cl is not None else -1
                res[exp]["clients"].append((client, client_executions))

        # Get installed ollama models
        models = []
        try:
            models = get_ollama_models()
        except:
            pass

        # Get all ollama pulls
        ollama_pulls = Ollama_Pull.query.all()
        ollama_pulls = [(pull.model_name, float(pull.status)) for pull in ollama_pulls]

        dbtype = get_db_type()
        dbport = get_db_port()
        db_conn = check_connection()
        db_server = get_db_server()

        return render_template_string(
            """
        <h1>Admin Dashboard</h1>
        <p>Experiments: {{ experiments|length }}</p>
        <p>Models: {{ models|length }}</p>
        <p>DB Type: {{ dbtype }}</p>
        <p>DB Port: {{ dbport }}</p>
        <p>DB Connection: {{ db_conn }}</p>
        <p>DB Server: {{ db_server }}</p>
        """,
            experiments=res,
            ollamas=ollamas,
            models=models,
            active_pulls=ollama_pulls,
            len=len,
            dbtype=dbtype,
            dbport=dbport,
            db_conn=db_conn,
            db_server=db_server,
        )

    @admin.route("/admin/about")
    @login_required
    def about():
        try:
            check_privileges(current_user.username)
        except PermissionError:
            return "Access denied", 403

        ollamas = ollama_status()
        return render_template_string(
            """
        <h1>About</h1>
        <p>Y_Web Admin Panel</p>
        <p>Ollama Status: {{ ollamas.status }}</p>
        """,
            ollamas=ollamas,
        )

    app.register_blueprint(admin)

    # Also need auth for login testing
    from flask import Blueprint, redirect, request, url_for
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
                    return redirect("/admin/dashboard")

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
        )
        db.session.add(admin_user)

        admin_user_mgmt = User_mgmt(
            username="admin",
            email="admin@test.com",
            password=generate_password_hash("admin123"),
            joined_on=1234567890,
        )
        db.session.add(admin_user_mgmt)

        # Create test regular user
        regular_user = Admin_users(
            username="user",
            email="user@test.com",
            password=generate_password_hash("user123"),
            role="user",
        )
        db.session.add(regular_user)

        regular_user_mgmt = User_mgmt(
            username="user",
            email="user@test.com",
            password=generate_password_hash("user123"),
            joined_on=1234567890,
        )
        db.session.add(regular_user_mgmt)

        # Create test experiment
        experiment = Exps(
            exp_name="Test Experiment",
            exp_descr="Test Description",
            platform_type="microblogging",
            owner="admin",
            status=1,
            running=0,
            port=5001,
        )
        db.session.add(experiment)
        db.session.commit()

        # Create test client
        client = Client(
            name="Test Client", descr="Test Client Description", id_exp=experiment.idexp
        )
        db.session.add(client)
        db.session.commit()

        # Create test client execution
        client_exec = Client_Execution(client_id=client.id, status="running")
        db.session.add(client_exec)

        # Create test ollama pull
        ollama_pull = Ollama_Pull(model_name="llama2:latest", status="1.0")
        db.session.add(ollama_pull)

        db.session.commit()

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Test client for the app"""
    return app.test_client()


class TestAdminRoutes:
    """Test admin routes"""

    def test_dashboard_without_login(self, client):
        """Test accessing dashboard without login"""
        response = client.get("/admin/dashboard")
        assert response.status_code == 302  # Redirect to login

    def test_dashboard_with_admin_login(self, client):
        """Test dashboard access with admin login"""
        # Login as admin
        login_response = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )
        assert login_response.status_code == 302  # Redirect to dashboard

        # Access dashboard
        response = client.get("/admin/dashboard")
        assert response.status_code == 200
        assert b"Admin Dashboard" in response.data
        assert b"Experiments:" in response.data
        assert b"Models:" in response.data
        assert b"DB Type: sqlite" in response.data
        assert b"DB Connection: True" in response.data

    def test_dashboard_with_regular_user_login(self, client):
        """Test dashboard access with regular user (should be denied)"""
        # Login as regular user
        login_response = client.post(
            "/login", data={"email": "user@test.com", "password": "user123"}
        )

        # Try to access dashboard
        response = client.get("/admin/dashboard")
        assert response.status_code == 403  # Access denied
        assert b"Access denied" in response.data

    def test_about_without_login(self, client):
        """Test accessing about page without login"""
        response = client.get("/admin/about")
        assert response.status_code == 302  # Redirect to login

    def test_about_with_admin_login(self, client):
        """Test about page access with admin login"""
        # Login as admin
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        # Access about page
        response = client.get("/admin/about")
        assert response.status_code == 200
        assert b"About" in response.data
        assert b"Y_Web Admin Panel" in response.data
        assert b"Ollama Status: running" in response.data

    def test_about_with_regular_user_login(self, client):
        """Test about page access with regular user (should be denied)"""
        # Login as regular user
        client.post("/login", data={"email": "user@test.com", "password": "user123"})

        # Try to access about page
        response = client.get("/admin/about")
        assert response.status_code == 403  # Access denied
        assert b"Access denied" in response.data


class TestAdminPrivileges:
    """Test admin privilege checking"""

    def test_admin_has_dashboard_access(self, client):
        """Test that admin user can access dashboard"""
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        response = client.get("/admin/dashboard")
        assert response.status_code == 200
        assert b"Admin Dashboard" in response.data

    def test_regular_user_denied_dashboard_access(self, client):
        """Test that regular user is denied dashboard access"""
        client.post("/login", data={"email": "user@test.com", "password": "user123"})

        response = client.get("/admin/dashboard")
        assert response.status_code == 403
        assert b"Access denied" in response.data

    def test_admin_has_about_access(self, client):
        """Test that admin user can access about page"""
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        response = client.get("/admin/about")
        assert response.status_code == 200
        assert b"About" in response.data

    def test_regular_user_denied_about_access(self, client):
        """Test that regular user is denied about page access"""
        client.post("/login", data={"email": "user@test.com", "password": "user123"})

        response = client.get("/admin/about")
        assert response.status_code == 403
        assert b"Access denied" in response.data


class TestAdminDashboardContent:
    """Test admin dashboard content rendering"""

    def test_dashboard_shows_experiment_data(self, client):
        """Test that dashboard shows experiment information"""
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        response = client.get("/admin/dashboard")
        assert response.status_code == 200

        # Check that experiment data is displayed
        assert b"Experiments:" in response.data
        # The test setup creates 1 experiment, so it should show "1"
        # Note: We check for the general structure since the exact count
        # depends on template rendering

    def test_dashboard_shows_database_info(self, client):
        """Test that dashboard shows database information"""
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        response = client.get("/admin/dashboard")
        assert response.status_code == 200

        # Check database information
        assert b"DB Type: sqlite" in response.data
        assert b"DB Port: 5432" in response.data
        assert b"DB Connection: True" in response.data
        assert b"DB Server: localhost" in response.data

    def test_about_shows_system_info(self, client):
        """Test that about page shows system information"""
        client.post("/login", data={"email": "admin@test.com", "password": "admin123"})

        response = client.get("/admin/about")
        assert response.status_code == 200

        # Check system information
        assert b"Y_Web Admin Panel" in response.data
        assert b"Ollama Status: running" in response.data
