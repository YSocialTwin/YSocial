"""
Tests for HPC client execution log monitoring functionality.

This module tests:
- Checking execution logs for shutdown complete message
- Marking clients as completed
- Terminating HPC experiments when all clients complete
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


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


class TestHPCExecutionLogMonitoring:
    """Test HPC execution log monitoring functionality."""

    def test_check_shutdown_message_found(self, app, db):
        """Test detecting 'Client shutdown complete' message in log."""
        from y_web.utils.log_metrics import check_hpc_client_execution_completion

        # Create a temporary log file with shutdown message
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_execution.log", delete=False
        ) as f:
            log_path = f.name
            # Write some log entries
            f.write(
                '{"timestamp": "2026-02-04T14:44:01.000000", "level": "INFO", "message": "Client starting"}\n'
            )
            f.write(
                '{"timestamp": "2026-02-04T14:44:02.000000", "level": "INFO", "message": "Processing round 1"}\n'
            )
            f.write(
                '{"timestamp": "2026-02-04T14:44:03.082126", "level": "INFO", "message": "Client shutdown complete", "module": "run_client", "function": "<module>", "line": 526}\n'
            )

        try:
            with app.app_context():
                result = check_hpc_client_execution_completion(1, 1, log_path)
                assert result is True
        finally:
            os.unlink(log_path)

    def test_check_shutdown_message_not_found(self, app, db):
        """Test when shutdown message is not present."""
        from y_web.utils.log_metrics import check_hpc_client_execution_completion

        # Create a temporary log file without shutdown message
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_execution.log", delete=False
        ) as f:
            log_path = f.name
            f.write(
                '{"timestamp": "2026-02-04T14:44:01.000000", "level": "INFO", "message": "Client starting"}\n'
            )
            f.write(
                '{"timestamp": "2026-02-04T14:44:02.000000", "level": "INFO", "message": "Processing round 1"}\n'
            )

        try:
            with app.app_context():
                result = check_hpc_client_execution_completion(1, 1, log_path)
                assert result is False
        finally:
            os.unlink(log_path)

    def test_check_shutdown_empty_file(self, app, db):
        """Test handling of empty log file."""
        from y_web.utils.log_metrics import check_hpc_client_execution_completion

        # Create an empty log file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_execution.log", delete=False
        ) as f:
            log_path = f.name

        try:
            with app.app_context():
                result = check_hpc_client_execution_completion(1, 1, log_path)
                assert result is False
        finally:
            os.unlink(log_path)

    def test_check_shutdown_invalid_json(self, app, db):
        """Test handling of invalid JSON in log."""
        from y_web.utils.log_metrics import check_hpc_client_execution_completion

        # Create a log file with invalid JSON
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_execution.log", delete=False
        ) as f:
            log_path = f.name
            f.write(
                '{"timestamp": "2026-02-04T14:44:01.000000", "level": "INFO", "message": "Client starting"}\n'
            )
            f.write("This is not valid JSON\n")

        try:
            with app.app_context():
                result = check_hpc_client_execution_completion(1, 1, log_path)
                assert result is False
        finally:
            os.unlink(log_path)

    def test_check_shutdown_missing_file(self, app, db):
        """Test handling of missing log file."""
        from y_web.utils.log_metrics import check_hpc_client_execution_completion

        with app.app_context():
            result = check_hpc_client_execution_completion(
                1, 1, "/nonexistent/path/log.log"
            )
            assert result is False

    def test_mark_client_as_completed(self, app, db):
        """Test marking a client as completed."""
        from y_web.models import Client, Client_Execution, Exps, Population
        from y_web.utils.log_metrics import mark_hpc_client_as_completed

        with app.app_context():
            # Create test data
            exp = Exps(
                exp_name="Test HPC",
                exp_descr="Test",
                platform_type="microblogging",
                owner="test",
                status=1,
                running=1,
                port=5000,
                db_name="experiments_test",
                simulator_type="HPC",
            )
            db.session.add(exp)
            db.session.commit()

            # Create a population for the client (minimal required fields)
            pop = Population(name="test_pop", descr="Test population", size=10)
            db.session.add(pop)
            db.session.commit()

            client = Client(
                name="test_client",
                descr="Test client",
                id_exp=exp.idexp,
                population_id=pop.id,
                status=1,
            )
            db.session.add(client)
            db.session.commit()

            client_exec = Client_Execution(
                client_id=client.id,
                elapsed_time=10,
                expected_duration_rounds=24,
                last_active_day=0,
                last_active_hour=9,
            )
            db.session.add(client_exec)
            db.session.commit()

            # Mark client as completed
            result = mark_hpc_client_as_completed(exp.idexp, client.id)
            assert result is True

            # Verify updates
            updated_exec = Client_Execution.query.filter_by(client_id=client.id).first()
            assert updated_exec.elapsed_time == 24
            # With 24 rounds: round 1 = day 0, hour 0; round 24 = day 0, hour 23
            assert updated_exec.last_active_day == 0
            assert updated_exec.last_active_hour == 23

            updated_client = Client.query.filter_by(id=client.id).first()
            assert updated_client.status == 0

    @patch("y_web.utils.external_processes.stop_hpc_server")
    def test_check_and_terminate_all_clients_completed(self, mock_stop, app, db):
        """Test terminating experiment when all clients are completed."""
        from y_web.models import Client, Exps, Population
        from y_web.utils.log_metrics import check_and_terminate_hpc_experiment

        with app.app_context():
            # Create test data
            exp = Exps(
                exp_name="Test HPC",
                exp_descr="Test",
                platform_type="microblogging",
                owner="test",
                status=1,
                running=1,
                port=5000,
                db_name="experiments_test",
                simulator_type="HPC",
                exp_status="active",
            )
            db.session.add(exp)
            db.session.commit()

            # Create a population for the clients
            pop = Population(name="test_pop", descr="Test population", size=10)
            db.session.add(pop)
            db.session.commit()

            # Create multiple clients, all completed (status=0)
            clients_created = []
            for i in range(3):
                client = Client(
                    name=f"client_{i}",
                    descr=f"Test client {i}",
                    id_exp=exp.idexp,
                    population_id=pop.id,
                    status=0,  # All completed
                )
                db.session.add(client)
                clients_created.append(client)
            db.session.commit()

            # Create Client_Execution records indicating each client truly completed
            from y_web.models import Client_Execution

            for client in clients_created:
                client_exec = Client_Execution(
                    client_id=client.id,
                    elapsed_time=10,
                    expected_duration_rounds=10,
                )
                db.session.add(client_exec)
            db.session.commit()

            # Check and terminate
            result = check_and_terminate_hpc_experiment(exp.idexp)
            assert result is True

            # Verify experiment was terminated
            updated_exp = Exps.query.filter_by(idexp=exp.idexp).first()
            assert updated_exp.running == 0
            assert updated_exp.exp_status == "completed"
            mock_stop.assert_called_once_with(exp.idexp)

    @patch("y_web.utils.external_processes.stop_hpc_server")
    def test_check_and_terminate_some_clients_running(self, mock_stop, app, db):
        """Test that experiment is not terminated when some clients are still running."""
        from y_web.models import Client, Exps, Population
        from y_web.utils.log_metrics import check_and_terminate_hpc_experiment

        with app.app_context():
            # Create test data
            exp = Exps(
                exp_name="Test HPC",
                exp_descr="Test",
                platform_type="microblogging",
                owner="test",
                status=1,
                running=1,
                port=5000,
                db_name="experiments_test",
                simulator_type="HPC",
            )
            db.session.add(exp)
            db.session.commit()

            # Create a population for the clients
            pop = Population(name="test_pop", descr="Test population", size=10)
            db.session.add(pop)
            db.session.commit()

            # Create clients with mixed status
            for i in range(3):
                client = Client(
                    name=f"client_{i}",
                    descr=f"Test client {i}",
                    id_exp=exp.idexp,
                    population_id=pop.id,
                    status=0 if i < 2 else 1,  # One still running
                )
                db.session.add(client)
            db.session.commit()

            # Check and terminate
            result = check_and_terminate_hpc_experiment(exp.idexp)
            assert result is False

            # Verify experiment was NOT terminated
            updated_exp = Exps.query.filter_by(idexp=exp.idexp).first()
            assert updated_exp.running == 1
            mock_stop.assert_not_called()
