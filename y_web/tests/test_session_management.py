"""
Test database session management to prevent connection leaks and hangs.
This test ensures that each request properly creates and cleans up its database session,
which is critical for preventing random hangs especially with SQLite.
"""

import os
import tempfile

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy


def test_session_cleanup_on_request():
    """Test that database sessions are properly cleaned up after each request"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "connect_args": {"check_same_thread": False},
            },
        }
    )

    db = SQLAlchemy(app)

    class TestModel(db.Model):
        __tablename__ = "test_model"
        id = db.Column(db.Integer, primary_key=True)
        value = db.Column(db.String(50))

    @app.teardown_request
    def cleanup_session(exception=None):
        """Ensure session is removed after each request"""
        db.session.remove()

    @app.route("/test")
    def test_route():
        # Create a test object
        obj = TestModel(value="test")
        db.session.add(obj)
        db.session.commit()
        return "OK"

    with app.app_context():
        db.create_all()

        # Simulate multiple requests to test session cleanup
        with app.test_client() as client:
            for i in range(10):
                response = client.get("/test")
                assert response.status_code == 200

            # Verify all objects were created
            count = TestModel.query.count()
            assert count == 10

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


def test_session_with_nullpool():
    """Test that NullPool prevents connection pooling issues with SQLite"""
    from sqlalchemy.pool import NullPool

    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "connect_args": {"check_same_thread": False},
                "poolclass": NullPool,
            },
        }
    )

    db = SQLAlchemy(app)

    class TestModel(db.Model):
        __tablename__ = "test_model"
        id = db.Column(db.Integer, primary_key=True)
        value = db.Column(db.String(50))

    @app.teardown_request
    def cleanup_session(exception=None):
        """Ensure session is removed after each request"""
        db.session.remove()

    @app.route("/test")
    def test_route():
        # Create a test object
        obj = TestModel(value="test")
        db.session.add(obj)
        db.session.commit()
        return "OK"

    with app.app_context():
        db.create_all()

        # Simulate a stream of requests to test that hangs don't occur
        with app.test_client() as client:
            for i in range(50):
                response = client.get("/test")
                assert response.status_code == 200

            # Verify all objects were created
            count = TestModel.query.count()
            assert count == 50

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


def test_session_removal_after_exception():
    """Test that sessions are cleaned up even when exceptions occur"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "connect_args": {"check_same_thread": False},
            },
        }
    )

    db = SQLAlchemy(app)

    class TestModel(db.Model):
        __tablename__ = "test_model"
        id = db.Column(db.Integer, primary_key=True)
        value = db.Column(db.String(50))

    @app.teardown_request
    def cleanup_session(exception=None):
        """Ensure session is removed after each request, even on exception"""
        db.session.remove()

    @app.errorhandler(500)
    def handle_error(e):
        return "Error occurred", 500

    @app.route("/error")
    def error_route():
        # Create a test object
        obj = TestModel(value="test")
        db.session.add(obj)
        db.session.commit()
        raise ValueError("Test error")

    @app.route("/success")
    def success_route():
        # This should work even after the error
        obj = TestModel(value="success")
        db.session.add(obj)
        db.session.commit()
        return "OK"

    with app.app_context():
        db.create_all()

        # Don't use test_client in testing mode to properly test error handling
        app.config["TESTING"] = False

        with app.test_client() as client:
            # Make a request that causes an error
            response = client.get("/error")
            # Error handler should catch it and return 500
            assert response.status_code == 500

            # Make a successful request to ensure session was cleaned up
            response = client.get("/success")
            assert response.status_code == 200

            # Verify that the success object was created
            # The error route committed before raising, so both objects should exist
            count = TestModel.query.count()
            assert count == 2

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


def test_concurrent_requests():
    """Test that session management works correctly with concurrent requests"""
    import threading

    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "connect_args": {"check_same_thread": False},
            },
        }
    )

    db = SQLAlchemy(app)

    class TestModel(db.Model):
        __tablename__ = "test_model"
        id = db.Column(db.Integer, primary_key=True)
        value = db.Column(db.String(50))

    @app.teardown_request
    def cleanup_session(exception=None):
        """Ensure session is removed after each request"""
        db.session.remove()

    @app.route("/test")
    def test_route():
        # Create a test object
        obj = TestModel(value="test")
        db.session.add(obj)
        db.session.commit()
        return "OK"

    with app.app_context():
        db.create_all()

    # Simulate concurrent requests
    def make_request():
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 200

    threads = []
    for i in range(10):
        t = threading.Thread(target=make_request)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Verify all objects were created
    with app.app_context():
        count = TestModel.query.count()
        assert count == 10

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)
