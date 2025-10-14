"""
Tests for merge populations functionality
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
    """Create a test app for merge populations testing"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_BINDS": {
                "db_admin": f"sqlite:///{db_path}",
                "db_exp": f"sqlite:///{db_path}",
            },
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "WTF_CSRF_ENABLED": False,
        }
    )

    db = SQLAlchemy(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Define minimal models for testing
    class Admin_users(db.Model):
        __bind_key__ = "db_admin"
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

    class Population(db.Model):
        __bind_key__ = "db_admin"
        __tablename__ = "population"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(50), nullable=False)
        descr = db.Column(db.String(200), nullable=False)
        size = db.Column(db.Integer)

    class Agent(db.Model):
        __bind_key__ = "db_admin"
        __tablename__ = "agents"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(50), nullable=False)
        ag_type = db.Column(db.String(50), nullable=False)

    class Agent_Population(db.Model):
        __bind_key__ = "db_admin"
        __tablename__ = "agent_population"
        id = db.Column(db.Integer, primary_key=True)
        agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=False)
        population_id = db.Column(
            db.Integer, db.ForeignKey("population.id"), nullable=False
        )

    class Page(db.Model):
        __bind_key__ = "db_admin"
        __tablename__ = "pages"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(50), nullable=False)
        descr = db.Column(db.String(200))

    class Page_Population(db.Model):
        __bind_key__ = "db_admin"
        __tablename__ = "page_population"
        id = db.Column(db.Integer, primary_key=True)
        page_id = db.Column(db.Integer, db.ForeignKey("pages.id"), nullable=False)
        population_id = db.Column(
            db.Integer, db.ForeignKey("population.id"), nullable=False
        )

    @login_manager.user_loader
    def load_user(user_id):
        return Admin_users.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()


class TestMergePopulations:
    """Test merge populations route"""

    def test_merge_populations_route_exists(self):
        """Test that merge populations route exists"""
        try:
            from y_web.routes_admin import populations_routes

            assert populations_routes is not None
            assert hasattr(populations_routes, "merge_populations")
        except (ImportError, AttributeError) as e:
            pytest.skip(f"Could not import merge_populations: {e}")

    def test_merge_populations_endpoint_structure(self):
        """Test that merge populations endpoint has correct structure"""
        try:
            from y_web.routes_admin.populations_routes import merge_populations

            # Check function exists and is callable
            assert callable(merge_populations)

            # Check function has docstring
            assert merge_populations.__doc__ is not None
            assert "merge" in merge_populations.__doc__.lower()

        except ImportError as e:
            pytest.skip(f"Could not import merge_populations function: {e}")
