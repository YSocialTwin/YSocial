"""
Pytest configuration and fixtures for y_web tests
"""
import os
import tempfile
import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

# Create minimal Flask app for testing without importing full y_web
db = SQLAlchemy()


@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Use a temporary database for testing
    db_fd, db_path = tempfile.mkstemp()
    
    # Create minimal Flask app
    app = Flask(__name__)
    app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_BINDS': {
            'db_admin': f'sqlite:///{db_path}',
            'db_exp': f'sqlite:///{db_path}',
        },
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SQLALCHEMY_ENGINE_OPTIONS': {
            'connect_args': {'check_same_thread': False}
        }
    })
    
    # Initialize extensions
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    
    with app.app_context():
        # Import models here to avoid circular imports
        # We need to patch the y_web.db reference to use our test db
        import y_web.models
        y_web.models.db = db
        
        from y_web.models import Admin_users, User_mgmt
        
        db.create_all()
        
        # Create test admin user
        admin_user = Admin_users(
            username='admin',
            email='admin@test.com',
            password=generate_password_hash('admin123'),
            role='admin',
            last_seen='2023-01-01'
        )
        db.session.add(admin_user)
        
        # Create test regular user
        regular_user = User_mgmt(
            username='testuser',
            email='testuser@test.com',
            password=generate_password_hash('test123'),
            joined_on=1234567890
        )
        db.session.add(regular_user)
        
        db.session.commit()
        
        # Set up user loader for flask-login
        @login_manager.user_loader
        def load_user(user_id):
            return User_mgmt.query.get(int(user_id))
    
    yield app
    
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture
def auth(client):
    """Authentication helper for tests."""
    class AuthActions:
        def __init__(self, client):
            self._client = client
        
        def login(self, username='admin', password='admin123'):
            return self._client.post(
                '/login',
                data={'email': 'admin@test.com', 'password': password}
            )
        
        def logout(self):
            return self._client.get('/logout')
    
    return AuthActions(client)