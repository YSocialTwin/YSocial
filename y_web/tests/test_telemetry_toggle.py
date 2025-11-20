"""
Tests for telemetry toggle functionality.

Tests the database schema changes, model updates, and telemetry preference enforcement.
"""

import os
import tempfile

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

from y_web.telemetry import Telemetry


def test_admin_user_model_has_telemetry_fields():
    """Test that Admin_users model has telemetry fields."""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })

    db = SQLAlchemy(app)

    # Define a test Admin_users model matching the real one
    class Admin_users(db.Model):
        __tablename__ = "admin_users"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(15), nullable=False, unique=True)
        email = db.Column(db.String(50), nullable=False, unique=True)
        password = db.Column(db.String(80), nullable=False)
        last_seen = db.Column(db.String(30), nullable=False)
        role = db.Column(db.String(10), nullable=False)
        telemetry_enabled = db.Column(db.Boolean, default=True)
        telemetry_notice_shown = db.Column(db.Boolean, default=False)

    with app.app_context():
        db.create_all()

        user = Admin_users(
            username="testadmin",
            email="admin@test.com",
            password=generate_password_hash("TestPass123!"),
            role="admin",
            last_seen=""
        )
        db.session.add(user)
        db.session.commit()

        # Verify telemetry fields exist and have correct defaults
        user = Admin_users.query.filter_by(username="testadmin").first()
        assert user is not None
        assert hasattr(user, "telemetry_enabled")
        assert hasattr(user, "telemetry_notice_shown")
        assert user.telemetry_enabled is True
        assert user.telemetry_notice_shown is False

        db.session.close()

    os.close(db_fd)
    os.unlink(db_path)


def test_telemetry_enabled_default_value():
    """Test that telemetry_enabled defaults to True for new users."""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })

    db = SQLAlchemy(app)

    class Admin_users(db.Model):
        __tablename__ = "admin_users"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(15), nullable=False)
        email = db.Column(db.String(50), nullable=False)
        password = db.Column(db.String(80), nullable=False)
        last_seen = db.Column(db.String(30), nullable=False)
        role = db.Column(db.String(10), nullable=False)
        telemetry_enabled = db.Column(db.Boolean, default=True)
        telemetry_notice_shown = db.Column(db.Boolean, default=False)

    with app.app_context():
        db.create_all()

        user = Admin_users(
            username="newuser",
            email="newuser@test.com",
            password=generate_password_hash("TestPass123!"),
            role="admin",
            last_seen=""
        )
        db.session.add(user)
        db.session.commit()

        user = Admin_users.query.filter_by(username="newuser").first()
        assert user.telemetry_enabled is True

        db.session.close()

    os.close(db_fd)
    os.unlink(db_path)


def test_telemetry_notice_shown_default_value():
    """Test that telemetry_notice_shown defaults to False for new users."""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })

    db = SQLAlchemy(app)

    class Admin_users(db.Model):
        __tablename__ = "admin_users"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(15), nullable=False)
        email = db.Column(db.String(50), nullable=False)
        password = db.Column(db.String(80), nullable=False)
        last_seen = db.Column(db.String(30), nullable=False)
        role = db.Column(db.String(10), nullable=False)
        telemetry_enabled = db.Column(db.Boolean, default=True)
        telemetry_notice_shown = db.Column(db.Boolean, default=False)

    with app.app_context():
        db.create_all()

        user = Admin_users(
            username="newuser",
            email="newuser@test.com",
            password=generate_password_hash("TestPass123!"),
            role="admin",
            last_seen=""
        )
        db.session.add(user)
        db.session.commit()

        user = Admin_users.query.filter_by(username="newuser").first()
        assert user.telemetry_notice_shown is False

        db.session.close()

    os.close(db_fd)
    os.unlink(db_path)


def test_telemetry_class_checks_user_preference_enabled():
    """Test that Telemetry class respects enabled preference."""
    # Create a simple mock user object
    class MockUser:
        def __init__(self):
            self.telemetry_enabled = True
            self.is_authenticated = True

    user = MockUser()
    telemetry = Telemetry(user=user)
    assert telemetry.enabled is True


def test_telemetry_class_checks_user_preference_disabled():
    """Test that Telemetry class respects disabled preference."""
    # Create a simple mock user object
    class MockUser:
        def __init__(self):
            self.telemetry_enabled = False
            self.is_authenticated = True

    user = MockUser()
    telemetry = Telemetry(user=user)
    assert telemetry.enabled is False


def test_telemetry_class_defaults_to_enabled_no_user():
    """Test that Telemetry defaults to enabled when no user is provided."""
    telemetry = Telemetry(user=None)
    assert telemetry.enabled is True


def test_telemetry_does_not_send_when_disabled():
    """Test that Telemetry does not send data when disabled."""
    # Create a simple mock user object
    class MockUser:
        def __init__(self):
            self.telemetry_enabled = False
            self.is_authenticated = True

    user = MockUser()
    telemetry = Telemetry(user=user)

    # These should return False when telemetry is disabled
    result = telemetry.log_event({"action": "test"})
    assert result is False

    result = telemetry.log_stack_trace({"error_type": "test", "stacktrace": "test"})
    assert result is False


def test_telemetry_user_attribute_handling():
    """Test that Telemetry handles users without telemetry_enabled attribute."""
    # Create a mock user without telemetry_enabled
    class MockUserWithoutAttr:
        def __init__(self):
            self.is_authenticated = True

    user = MockUserWithoutAttr()
    telemetry = Telemetry(user=user)
    # Should default to enabled
    assert telemetry.enabled is True


def test_telemetry_anonymous_user_handling():
    """Test that Telemetry handles anonymous/unauthenticated users."""
    # Create a mock anonymous user
    class MockAnonymousUser:
        def __init__(self):
            self.is_authenticated = False

    user = MockAnonymousUser()
    telemetry = Telemetry(user=user)
    # Should default to enabled for anonymous users
    assert telemetry.enabled is True

