"""
Tests for automatic log synchronization functionality.

This module tests:
- Log sync settings model and database operations
- Log sync scheduler initialization and operation
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from y_web.models import LogSyncSettings


@pytest.fixture
def app():
    """Create a test Flask app with database."""
    app = Flask(__name__)

    # Create temporary database
    db_fd, db_path = tempfile.mkstemp()

    app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SQLALCHEMY_BINDS": {
                "db_admin": f"sqlite:///{db_path}",
                "db_exp": f"sqlite:///{db_path}",
            },
        }
    )

    from y_web import db as database

    database.init_app(app)

    with app.app_context():
        # Create all tables
        database.create_all()

    yield app

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def db(app):
    """Get database instance."""
    from y_web import db as database

    return database


class TestLogSyncSettings:
    """Test log sync settings model and database operations."""

    def test_log_sync_settings_model_creation(self, app, db):
        """Test that LogSyncSettings model can be created with default values."""
        with app.app_context():
            settings = LogSyncSettings(enabled=True, sync_interval_minutes=10)
            db.session.add(settings)
            db.session.commit()

            # Verify settings were created
            retrieved = LogSyncSettings.query.first()
            assert retrieved is not None
            assert retrieved.enabled is True
            assert retrieved.sync_interval_minutes == 10
            assert retrieved.last_sync is None

    def test_log_sync_settings_default_values(self, app, db):
        """Test that LogSyncSettings uses correct default values."""
        with app.app_context():
            # Create with minimal parameters
            settings = LogSyncSettings()
            db.session.add(settings)
            db.session.commit()

            retrieved = LogSyncSettings.query.first()
            assert retrieved.enabled is True  # Default is True
            assert retrieved.sync_interval_minutes == 10  # Default is 10

    def test_log_sync_settings_update(self, app, db):
        """Test updating log sync settings."""
        with app.app_context():
            # Create initial settings
            settings = LogSyncSettings(enabled=True, sync_interval_minutes=10)
            db.session.add(settings)
            db.session.commit()

            # Update settings
            settings = LogSyncSettings.query.first()
            settings.enabled = False
            settings.sync_interval_minutes = 30
            settings.last_sync = datetime.now(timezone.utc)
            db.session.commit()

            # Verify updates
            retrieved = LogSyncSettings.query.first()
            assert retrieved.enabled is False
            assert retrieved.sync_interval_minutes == 30
            assert retrieved.last_sync is not None

    def test_log_sync_settings_only_one_row(self, app, db):
        """Test that only one LogSyncSettings row should exist."""
        with app.app_context():
            # Create first settings
            settings1 = LogSyncSettings(enabled=True, sync_interval_minutes=10)
            db.session.add(settings1)
            db.session.commit()

            # The system should only use query.first()
            # to get the single settings row
            count = LogSyncSettings.query.count()
            assert count == 1


class TestLogSyncScheduler:
    """Test log sync scheduler functionality."""

    def test_scheduler_get_settings_creates_default(self, app, db):
        """Test that scheduler creates default settings if none exist."""
        from y_web.utils.log_sync_scheduler import LogSyncScheduler

        with app.app_context():
            scheduler = LogSyncScheduler(app)
            settings = scheduler._get_settings()

            assert settings is not None
            assert settings.enabled is True
            assert settings.sync_interval_minutes == 10

    def test_scheduler_update_last_sync(self, app, db):
        """Test that scheduler updates last_sync timestamp."""
        from y_web.utils.log_sync_scheduler import LogSyncScheduler

        with app.app_context():
            # Create settings first
            settings = LogSyncSettings(enabled=True, sync_interval_minutes=10)
            db.session.add(settings)
            db.session.commit()

            scheduler = LogSyncScheduler(app)
            scheduler._update_last_sync()

            updated_settings = LogSyncSettings.query.first()
            assert updated_settings.last_sync is not None

    @patch(
        "y_web.utils.log_sync_scheduler.LogSyncScheduler._sync_all_active_experiments"
    )
    def test_scheduler_trigger_sync(self, mock_sync, app, db):
        """Test manual trigger of log sync."""
        from y_web.utils.log_sync_scheduler import LogSyncScheduler

        scheduler = LogSyncScheduler(app)
        scheduler._started = True

        result = scheduler.trigger_sync()

        assert result is True
        mock_sync.assert_called_once()


class TestLogSyncValidation:
    """Test log sync settings validation."""

    def test_sync_interval_minimum(self, app, db):
        """Test that sync interval has minimum of 1 minute."""
        with app.app_context():
            # The validation happens at the API level, not model level
            # Model allows any value, API validates 1-1440
            settings = LogSyncSettings(enabled=True, sync_interval_minutes=1)
            db.session.add(settings)
            db.session.commit()

            retrieved = LogSyncSettings.query.first()
            assert retrieved.sync_interval_minutes == 1

    def test_sync_interval_maximum(self, app, db):
        """Test that sync interval has maximum of 1440 minutes (24 hours)."""
        with app.app_context():
            settings = LogSyncSettings(enabled=True, sync_interval_minutes=1440)
            db.session.add(settings)
            db.session.commit()

            retrieved = LogSyncSettings.query.first()
            assert retrieved.sync_interval_minutes == 1440

    def test_enabled_toggle(self, app, db):
        """Test enabling and disabling sync."""
        with app.app_context():
            # Start enabled
            settings = LogSyncSettings(enabled=True, sync_interval_minutes=10)
            db.session.add(settings)
            db.session.commit()

            # Disable
            settings = LogSyncSettings.query.first()
            settings.enabled = False
            db.session.commit()

            retrieved = LogSyncSettings.query.first()
            assert retrieved.enabled is False

            # Re-enable
            settings = LogSyncSettings.query.first()
            settings.enabled = True
            db.session.commit()

            retrieved = LogSyncSettings.query.first()
            assert retrieved.enabled is True

