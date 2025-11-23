"""
Tests for incremental log reading functionality.

Tests the database-backed incremental log reading and metric aggregation.
"""

import json
import os
import tempfile

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from y_web.models import (
    ClientLogMetrics,
    LogFileOffset,
    ServerLogMetrics,
)
from y_web.utils.log_metrics import (
    get_log_file_offset,
    parse_client_log_incremental,
    parse_server_log_incremental,
    update_log_file_offset,
)


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


class TestIncrementalLogReading:
    """Tests for incremental log reading functionality."""
    
    def test_log_file_offset_tracking(self, app, db):
        """Test that log file offsets are tracked correctly."""
        with app.app_context():
            exp_id = 1
            log_file_type = "server"
            file_path = "_server.log"
            
            # Initially, offset should be 0
            offset = get_log_file_offset(exp_id, log_file_type, file_path)
            assert offset == 0
            
            # Update offset
            update_log_file_offset(exp_id, log_file_type, file_path, 1000)
            
            # Check that offset was updated
            offset = get_log_file_offset(exp_id, log_file_type, file_path)
            assert offset == 1000
            
            # Update offset again
            update_log_file_offset(exp_id, log_file_type, file_path, 2000)
            offset = get_log_file_offset(exp_id, log_file_type, file_path)
            assert offset == 2000
    
    def test_server_log_incremental_parsing(self, app, db):
        """Test that server logs are parsed incrementally."""
        with app.app_context():
            # Create a temporary log file
            fd, log_file = tempfile.mkstemp(suffix=".log")
            
            try:
                # Write some log entries
                with os.fdopen(fd, "w") as f:
                    f.write('{"time": "2024-11-23 10:00:00", "path": "/api/feed", "duration": 0.5, "day": 0, "hour": 0}\n')
                    f.write('{"time": "2024-11-23 10:00:01", "path": "/api/post", "duration": 0.3, "day": 0, "hour": 0}\n')
                    f.write('{"time": "2024-11-23 10:00:02", "path": "/api/feed", "duration": 0.6, "day": 0, "hour": 0}\n')
                
                exp_id = 1
                
                # Parse the log file
                new_offset, metrics = parse_server_log_incremental(log_file, exp_id, 0)
                
                # Check that offset was updated
                assert new_offset > 0
                
                # Check that metrics were stored in database
                daily_metrics = ServerLogMetrics.query.filter_by(
                    exp_id=exp_id, aggregation_level="daily", day=0
                ).all()
                
                assert len(daily_metrics) > 0
                
                # Find feed and post metrics
                feed_metric = next((m for m in daily_metrics if m.path == "/api/feed"), None)
                post_metric = next((m for m in daily_metrics if m.path == "/api/post"), None)
                
                assert feed_metric is not None
                assert feed_metric.call_count == 2
                assert feed_metric.total_duration == pytest.approx(1.1, rel=1e-4)
                
                assert post_metric is not None
                assert post_metric.call_count == 1
                assert post_metric.total_duration == pytest.approx(0.3, rel=1e-4)
                
            finally:
                # Cleanup
                if os.path.exists(log_file):
                    os.remove(log_file)
    
    def test_incremental_reading_only_reads_new_entries(self, app, db):
        """Test that incremental reading only processes new log entries."""
        with app.app_context():
            # Create a temporary log file
            fd, log_file = tempfile.mkstemp(suffix=".log")
            
            try:
                # Write initial log entries
                with os.fdopen(fd, "w") as f:
                    f.write('{"time": "2024-11-23 10:00:00", "path": "/api/feed", "duration": 0.5, "day": 0, "hour": 0}\n')
                    f.write('{"time": "2024-11-23 10:00:01", "path": "/api/post", "duration": 0.3, "day": 0, "hour": 0}\n')
                
                exp_id = 1
                
                # Parse the log file (first time)
                new_offset, _ = parse_server_log_incremental(log_file, exp_id, 0)
                
                # Append more log entries
                with open(log_file, "a") as f:
                    f.write('{"time": "2024-11-23 10:00:02", "path": "/api/feed", "duration": 0.7, "day": 0, "hour": 0}\n')
                
                # Parse again from the new offset
                newer_offset, _ = parse_server_log_incremental(log_file, exp_id, new_offset)
                
                # Check that we only read the new entry
                assert newer_offset > new_offset
                
                # Check metrics - should have 3 feed calls total
                feed_metric = ServerLogMetrics.query.filter_by(
                    exp_id=exp_id, aggregation_level="daily", day=0, path="/api/feed"
                ).first()
                
                assert feed_metric is not None
                assert feed_metric.call_count == 3
                assert feed_metric.total_duration == pytest.approx(1.9, rel=1e-4)
                
            finally:
                # Cleanup
                if os.path.exists(log_file):
                    os.remove(log_file)
    
    def test_client_log_incremental_parsing(self, app, db):
        """Test that client logs are parsed incrementally."""
        with app.app_context():
            # Create a temporary log file
            fd, log_file = tempfile.mkstemp(suffix=".log")
            
            try:
                # Write some log entries
                with os.fdopen(fd, "w") as f:
                    f.write('{"method_name": "post", "execution_time_seconds": 1.5, "day": 0, "hour": 0}\n')
                    f.write('{"method_name": "comment", "execution_time_seconds": 0.8, "day": 0, "hour": 0}\n')
                    f.write('{"method_name": "post", "execution_time_seconds": 1.2, "day": 0, "hour": 0}\n')
                
                exp_id = 1
                client_id = 1
                
                # Parse the log file
                new_offset, metrics = parse_client_log_incremental(log_file, exp_id, client_id, 0)
                
                # Check that offset was updated
                assert new_offset > 0
                
                # Check that metrics were stored in database
                daily_metrics = ClientLogMetrics.query.filter_by(
                    exp_id=exp_id, client_id=client_id, aggregation_level="daily", day=0
                ).all()
                
                assert len(daily_metrics) > 0
                
                # Find post and comment metrics
                post_metric = next((m for m in daily_metrics if m.method_name == "post"), None)
                comment_metric = next((m for m in daily_metrics if m.method_name == "comment"), None)
                
                assert post_metric is not None
                assert post_metric.call_count == 2
                assert post_metric.total_execution_time == pytest.approx(2.7, rel=1e-4)
                
                assert comment_metric is not None
                assert comment_metric.call_count == 1
                assert comment_metric.total_execution_time == pytest.approx(0.8, rel=1e-4)
                
            finally:
                # Cleanup
                if os.path.exists(log_file):
                    os.remove(log_file)
    
    def test_handles_invalid_json_gracefully(self, app, db):
        """Test that invalid JSON lines are skipped gracefully."""
        with app.app_context():
            # Create a temporary log file with invalid JSON
            fd, log_file = tempfile.mkstemp(suffix=".log")
            
            try:
                # Write log entries with some invalid JSON
                with os.fdopen(fd, "w") as f:
                    f.write('{"path": "/api/feed", "duration": 0.5, "day": 0, "hour": 0}\n')
                    f.write('invalid json line\n')
                    f.write('{"path": "/api/post", "duration": 0.3, "day": 0, "hour": 0}\n')
                
                exp_id = 1
                
                # Parse should succeed and skip invalid line
                new_offset, metrics = parse_server_log_incremental(log_file, exp_id, 0)
                
                # Should have parsed 2 valid entries
                daily_metrics = ServerLogMetrics.query.filter_by(
                    exp_id=exp_id, aggregation_level="daily", day=0
                ).all()
                
                # We should have metrics for both valid entries
                assert len(daily_metrics) == 2
                
            finally:
                # Cleanup
                if os.path.exists(log_file):
                    os.remove(log_file)
