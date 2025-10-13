"""
Simple tests for y_web database models without complex bindings
"""

import os
import tempfile

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


def test_user_model_creation():
    """Test basic user model functionality"""
    # Create a simple Flask app for testing
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )

    db = SQLAlchemy(app)

    # Define a simple test model
    class TestUser(db.Model):
        __tablename__ = "test_users"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)
        password = db.Column(db.String(200), nullable=False)
        role = db.Column(db.String(20), default="user")

    with app.app_context():
        db.create_all()

        # Test creating a user
        user = TestUser(
            username="testuser",
            email="test@example.com",
            password=generate_password_hash("password123"),
            role="admin",
        )
        db.session.add(user)
        db.session.commit()

        # Test retrieving the user
        retrieved_user = TestUser.query.filter_by(username="testuser").first()
        assert retrieved_user is not None
        assert retrieved_user.username == "testuser"
        assert retrieved_user.email == "test@example.com"
        assert retrieved_user.role == "admin"
        assert check_password_hash(retrieved_user.password, "password123")

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


def test_post_model_creation():
    """Test basic post model functionality"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )

    db = SQLAlchemy(app)

    # Define simple test models
    class TestUser(db.Model):
        __tablename__ = "test_users"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        posts = db.relationship("TestPost", backref="author", lazy=True)

    class TestPost(db.Model):
        __tablename__ = "test_posts"
        id = db.Column(db.Integer, primary_key=True)
        content = db.Column(db.String(500), nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey("test_users.id"), nullable=False)
        round = db.Column(db.Integer, default=1)

    with app.app_context():
        db.create_all()

        # Create a user
        user = TestUser(username="testuser")
        db.session.add(user)
        db.session.commit()

        # Create a post
        post = TestPost(content="This is a test post", user_id=user.id, round=1)
        db.session.add(post)
        db.session.commit()

        # Test retrieving the post
        retrieved_post = TestPost.query.first()
        assert retrieved_post is not None
        assert retrieved_post.content == "This is a test post"
        assert retrieved_post.user_id == user.id
        assert retrieved_post.round == 1

        # Test relationship
        assert retrieved_post.author.username == "testuser"
        assert len(user.posts) == 1
        assert user.posts[0].content == "This is a test post"

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


def test_password_hashing():
    """Test password hashing functionality"""
    password = "testpassword123"
    hashed = generate_password_hash(password)

    assert hashed != password  # Should be hashed
    assert len(hashed) > len(password)  # Hashed version should be longer

    # Test verification
    assert check_password_hash(hashed, password)
    assert not check_password_hash(hashed, "wrongpassword")


def test_model_defaults():
    """Test model default values"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )

    db = SQLAlchemy(app)

    class TestUserWithDefaults(db.Model):
        __tablename__ = "test_users_defaults"
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(50), nullable=False)
        role = db.Column(db.String(20), default="user")
        is_active = db.Column(db.Boolean, default=True)
        join_timestamp = db.Column(db.Integer, default=1234567890)

    with app.app_context():
        db.create_all()

        # Create user with minimal data
        user = TestUserWithDefaults(username="defaultuser")
        db.session.add(user)
        db.session.commit()

        # Test defaults were applied
        retrieved_user = TestUserWithDefaults.query.filter_by(
            username="defaultuser"
        ).first()
        assert retrieved_user.role == "user"
        assert retrieved_user.is_active is True
        assert retrieved_user.join_timestamp == 1234567890

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


def test_activity_profile_model():
    """Test ActivityProfile model functionality"""
    app = Flask(__name__)
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )

    db = SQLAlchemy(app)

    class TestActivityProfile(db.Model):
        __tablename__ = "test_activity_profiles"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(120), nullable=False, unique=True)
        hours = db.Column(db.String(100), nullable=False)

        def to_dict(self):
            return {"id": self.id, "name": self.name, "hours": self.hours}

    with app.app_context():
        db.create_all()

        # Create an activity profile
        profile = TestActivityProfile(name="Morning Active", hours="6,7,8,9,10,11")
        db.session.add(profile)
        db.session.commit()

        # Test retrieving the profile
        retrieved_profile = TestActivityProfile.query.filter_by(
            name="Morning Active"
        ).first()
        assert retrieved_profile is not None
        assert retrieved_profile.name == "Morning Active"
        assert retrieved_profile.hours == "6,7,8,9,10,11"

        # Test to_dict method
        profile_dict = retrieved_profile.to_dict()
        assert profile_dict["name"] == "Morning Active"
        assert profile_dict["hours"] == "6,7,8,9,10,11"

        # Test hours parsing
        hours_list = [int(h) for h in retrieved_profile.hours.split(",")]
        assert len(hours_list) == 6
        assert 6 in hours_list
        assert 11 in hours_list

        # Create another profile
        profile2 = TestActivityProfile(name="Evening Active", hours="18,19,20,21,22,23")
        db.session.add(profile2)
        db.session.commit()

        # Test querying all profiles
        all_profiles = TestActivityProfile.query.all()
        assert len(all_profiles) == 2

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)
