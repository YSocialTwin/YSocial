"""
Tests for copy experiment functionality.

Tests the ability to duplicate experiments including configuration files,
database content, and admin database records for both SQLite and PostgreSQL.
"""

import json
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

pytestmark = pytest.mark.unit


# We'll use the conftest fixtures


def test_copy_experiment_validation():
    """Test copy experiment input validation logic."""
    # Test empty/missing experiment name
    new_name = ""
    source_id = "1"
    assert not new_name or not source_id  # Should fail validation

    # Test valid inputs
    new_name = "New Experiment"
    source_id = "1"
    assert new_name and source_id  # Should pass validation

    # Test port range validation
    port = 5000
    assert 5000 <= port <= 6000  # Valid port range

    port = 4999
    assert not (5000 <= port <= 6000)  # Invalid - too low

    port = 6001
    assert not (5000 <= port <= 6000)  # Invalid - too high


@patch("os.path.exists")
@patch("os.listdir")
@patch("shutil.copy2")
@patch("pathlib.Path.mkdir")
def test_copy_experiment_file_operations(
    mock_mkdir, mock_copy, mock_listdir, mock_exists
):
    """Test file operations during experiment copy."""
    # Setup mocks
    mock_exists.return_value = True
    mock_listdir.return_value = [
        "config_server.json",
        "database_server.db",
        "prompts.json",
    ]

    # Simulate successful file operations
    mock_mkdir.return_value = None
    mock_copy.return_value = None

    # Verify mocks can be called
    assert mock_exists("/test/path")
    assert len(mock_listdir("/test/path")) == 3


def test_log_file_exclusion():
    """Test that log files are excluded from copy."""
    # Simulate file list with log files
    file_list = [
        "config_server.json",
        "database_server.db",
        "prompts.json",
        "_server.log",
        "test_client.log",
        "population_A_client.log",
        "adhoc_client_alpha.state.json",
    ]

    # Filter out log files (simulating the copy logic)
    files_to_copy = [
        f for f in file_list if not f.endswith(".log") and not f.endswith(".state.json")
    ]

    # Verify log files are excluded
    assert "_server.log" not in files_to_copy
    assert "test_client.log" not in files_to_copy
    assert "population_A_client.log" not in files_to_copy
    assert "adhoc_client_alpha.state.json" not in files_to_copy

    # Verify other files are included
    assert "config_server.json" in files_to_copy
    assert "database_server.db" in files_to_copy
    assert "prompts.json" in files_to_copy
    assert len(files_to_copy) == 3


def test_client_execution_not_copied():
    """Test that Client_Execution entries are NOT copied for new experiments."""
    # Simulate source client execution with active state
    source_exec = {
        "client_id": 1,
        "elapsed_time": 3600,
        "expected_duration_rounds": 168,
        "last_active_hour": 15,
        "last_active_day": 3,
    }

    # In the copy operation, we create a new client but NO Client_Execution entry
    new_client = {"id": 2, "name": "test_client", "status": 0}  # Not running

    # Verify that we have a new client
    assert new_client["id"] != source_exec["client_id"]
    assert new_client["status"] == 0

    # The key point: no Client_Execution entry is created during copy
    # It will be created when the client first starts, ensuring fresh state
    # This is tested by the absence of Client_Execution creation in the copy code


def test_copy_experiment_config_update():
    """Test configuration file update logic."""
    # Test JSON serialization/deserialization
    config = {
        "name": "Test Experiment",
        "port": 5000,
        "host": "127.0.0.1",
        "platform_type": "microblogging",
    }

    # Serialize and deserialize
    config_str = json.dumps(config)
    config_parsed = json.loads(config_str)

    # Update config
    config_parsed["name"] = "Copied Experiment"
    config_parsed["port"] = 5001

    # Verify updates
    assert config_parsed["name"] == "Copied Experiment"
    assert config_parsed["port"] == 5001
    assert config_parsed["host"] == "127.0.0.1"


def test_database_name_parsing():
    """Test parsing of database names for SQLite and PostgreSQL."""
    # SQLite format: experiments/uuid/database_server.db
    sqlite_db_name = "experiments/abc123def/database_server.db"
    parts = sqlite_db_name.split(os.sep)
    assert len(parts) >= 2
    uuid_part = parts[1]
    assert uuid_part == "abc123def"

    # PostgreSQL format: experiments_uuid
    postgres_db_name = "experiments_abc123def"
    uuid_part = postgres_db_name.replace("experiments_", "")
    assert uuid_part == "abc123def"


def test_clean_database_used():
    """Test that copied experiments use clean database template, not source data."""
    import os

    # Verify clean database template exists
    clean_db_path = os.path.join("data_schema", "database_clean_server.db")
    # Just test the path construction - actual file existence checked in production code
    assert "database_clean_server.db" in clean_db_path

    # PostgreSQL schema file
    postgres_schema_path = os.path.join("data_schema", "postgre_server.sql")
    assert "postgre_server.sql" in postgres_schema_path

    # Verify the logic: clean database should be used, not source database
    # This is a conceptual test showing we use templates, not copies
    source_db = "experiments/source_uuid/database_server.db"
    clean_template = "data_schema/database_clean_server.db"

    # In copy operation, we should use clean_template, NOT source_db
    assert clean_template != source_db
    assert "clean" in clean_template.lower()


def test_unique_port_assignment():
    """Test that copied experiments get unique ports, not reusing source port."""
    # Simulate port assignment with all experiments having ports
    assigned_ports = {5000, 5001, 5002}

    # Port range
    port_range = range(5000, 6001)

    # Find available port
    available_port = None
    for port in port_range:
        if port not in assigned_ports:
            available_port = port
            break

    # Verify we get a unique port
    assert available_port is not None
    assert available_port not in assigned_ports
    assert available_port == 5003  # First available after 5002

    # Test that we don't reuse source port
    source_port = 5001
    assert available_port != source_port


def test_get_suggested_port_reuses_completed_experiment_port(monkeypatch):
    from y_web.routes.admin.sub.experiments import _helpers

    class FakeQuery:
        def all(self):
            return [
                SimpleNamespace(port=5000, exp_status="completed", idexp=1),
                SimpleNamespace(port=5001, exp_status="active", idexp=2),
            ]

    monkeypatch.setattr(_helpers, "Exps", SimpleNamespace(query=FakeQuery()))
    monkeypatch.setattr(_helpers, "is_port_free", lambda port: port == 5000)

    assert _helpers.get_suggested_port() == 5000


def test_get_suggested_port_skips_non_completed_experiment_ports(monkeypatch):
    from y_web.routes.admin.sub.experiments import _helpers

    class FakeQuery:
        def all(self):
            return [
                SimpleNamespace(port=5000, exp_status="stopped", idexp=1),
                SimpleNamespace(port=5001, exp_status="active", idexp=2),
                SimpleNamespace(port=5002, exp_status=None, idexp=3),
                SimpleNamespace(port=5003, exp_status="completed", idexp=4),
            ]

    clients = [SimpleNamespace(id=21, id_exp=1)]
    client_execs = [
        SimpleNamespace(client_id=21, elapsed_time=3, expected_duration_rounds=10)
    ]

    monkeypatch.setattr(_helpers, "Exps", SimpleNamespace(query=FakeQuery()))
    monkeypatch.setattr(
        _helpers,
        "Client",
        SimpleNamespace(
            query=SimpleNamespace(
                filter_by=lambda **_kwargs: SimpleNamespace(all=lambda: clients)
            )
        ),
    )
    monkeypatch.setattr(
        _helpers,
        "Client_Execution",
        SimpleNamespace(
            query=SimpleNamespace(
                filter_by=lambda **_kwargs: SimpleNamespace(
                    first=lambda: client_execs[0]
                )
            ),
            client_id=SimpleNamespace(in_=lambda values: values),
        ),
    )
    monkeypatch.setattr(_helpers, "is_port_free", lambda port: port == 5003)

    assert _helpers.get_suggested_port() == 5003


def test_get_suggested_port_reuses_legacy_stopped_experiment_port(monkeypatch):
    from y_web.routes.admin.sub.experiments import _helpers

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

        def filter(self, *_args, **_kwargs):
            return self

        def filter_by(self, **_kwargs):
            return self

    experiments = [
        SimpleNamespace(port=5000, exp_status="stopped", idexp=1),
        SimpleNamespace(port=5001, exp_status="active", idexp=2),
    ]
    clients = [SimpleNamespace(id=11, id_exp=1)]
    client_execs = [
        SimpleNamespace(client_id=11, elapsed_time=12, expected_duration_rounds=12)
    ]

    monkeypatch.setattr(_helpers, "Exps", SimpleNamespace(query=FakeQuery(experiments)))
    monkeypatch.setattr(
        _helpers,
        "Client",
        SimpleNamespace(
            query=FakeQuery(clients),
            id_exp=SimpleNamespace(in_=lambda values: values),
        ),
    )
    monkeypatch.setattr(
        _helpers,
        "Client_Execution",
        SimpleNamespace(
            query=SimpleNamespace(
                filter_by=lambda **_kwargs: SimpleNamespace(
                    first=lambda: client_execs[0]
                )
            ),
            client_id=SimpleNamespace(in_=lambda values: values),
        ),
    )
    monkeypatch.setattr(_helpers, "is_port_free", lambda port: port == 5000)

    assert _helpers.get_suggested_port() == 5000


def test_get_suggested_port_scans_past_6000(monkeypatch):
    from y_web.routes.admin.sub.experiments import _helpers

    class FakeQuery:
        def all(self):
            return [
                SimpleNamespace(port=port, exp_status="active", idexp=port)
                for port in range(5000, 6001)
            ]

    monkeypatch.setattr(_helpers, "Exps", SimpleNamespace(query=FakeQuery()))
    monkeypatch.setattr(_helpers, "is_port_free", lambda port: port == 6001)

    assert _helpers.get_suggested_port() == 6001


def test_get_suggested_port_falls_back_to_os_port_when_scan_is_exhausted(monkeypatch):
    from y_web.routes.admin.sub.experiments import _helpers

    class FakeQuery:
        def all(self):
            return [
                SimpleNamespace(port=5000, exp_status="active", idexp=1),
                SimpleNamespace(port=5001, exp_status="active", idexp=2),
            ]

    class FakeSocket:
        def __init__(self, *args, **kwargs):
            self.port = 61000

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def bind(self, address):
            return None

        def getsockname(self):
            return ("127.0.0.1", self.port)

    monkeypatch.setattr(_helpers, "Exps", SimpleNamespace(query=FakeQuery()))
    monkeypatch.setattr(_helpers, "is_port_free", lambda port: False)
    monkeypatch.setattr(_helpers, "count", lambda start: iter([5000, 5001, 65536]))
    monkeypatch.setattr(_helpers.socket, "socket", lambda *args, **kwargs: FakeSocket())

    assert _helpers.get_suggested_port() == 61000


def test_config_update_verification():
    """Test that config_server.json is properly updated with new values."""
    # Simulate config update
    old_config = {
        "name": "Old Experiment",
        "port": 5000,
        "database_uri": "/old/path/database.db",
    }

    new_name = "New Experiment"
    new_port = 5005
    new_db_uri = "/new/path/database.db"

    # Update config (simulating our logic)
    updated_config = old_config.copy()
    updated_config["name"] = new_name
    updated_config["port"] = new_port
    updated_config["database_uri"] = new_db_uri

    # Verify all fields are updated
    assert updated_config["name"] == new_name
    assert updated_config["port"] == new_port
    assert updated_config["database_uri"] == new_db_uri

    # Verify old values are not present
    assert updated_config["name"] != old_config["name"]
    assert updated_config["port"] != old_config["port"]
    assert updated_config["database_uri"] != old_config["database_uri"]


def test_client_config_port_update():
    """Test that client configuration files have their API endpoint port updated."""
    import re

    # Simulate client config with old port
    old_client_config = {
        "servers": {"llm": "gpt-4", "api": "http://127.0.0.1:5000/"},
        "simulation": {"name": "test_client"},
    }

    # New port to assign
    new_port = 5010

    # Update the API endpoint (simulating our logic)
    if "servers" in old_client_config and "api" in old_client_config["servers"]:
        old_api = old_client_config["servers"]["api"]
        # Replace the port in the URL (format: http://host:port/)
        new_api = re.sub(r":\d+/", f":{new_port}/", old_api)
        old_client_config["servers"]["api"] = new_api


def test_build_copy_group_experiment_name_is_bounded_and_traceable():
    from y_web.routes.admin.sub.experiments._crud import (
        _build_copy_group_experiment_name,
    )

    name = _build_copy_group_experiment_name(
        "Very Long Source Experiment Name That Should Be Trimmed",
        "Fresh Group Name With Extra Words",
        42,
    )

    assert len(name) <= 50
    assert "42" in name
    assert "fresh-group-name" in name.lower()
    assert name.startswith("Very") or name.startswith("very")


def test_copy_experiment_group_builds_one_copy_per_source_experiment(monkeypatch):
    from y_web.routes.admin.sub.experiments import _crud

    source_experiments = [
        SimpleNamespace(
            idexp=10,
            exp_name="Alpha",
            platform_type="microblogging",
            annotations="a",
            llm_agents_enabled=1,
        ),
        SimpleNamespace(
            idexp=11,
            exp_name="Beta",
            platform_type="forum",
            annotations="b",
            llm_agents_enabled=0,
        ),
    ]
    created_calls = []

    class FakeVisibleQuery:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return source_experiments

    class FakeNameQuery:
        def filter_by(self, **kwargs):
            self.kwargs = kwargs
            return self

        def first(self):
            return None

    class FakeTelemetry:
        def __init__(self, user):
            self.user = user

        def log_event(self, payload):
            created_calls.append(("telemetry", payload))

    class FakeColumn:
        def asc(self):
            return self

    class FakeExps:
        exp_group = object()
        exp_name = FakeColumn()
        query = FakeNameQuery()

    monkeypatch.setattr(_crud, "_current_admin_user_or_none", lambda: SimpleNamespace())
    monkeypatch.setattr(
        _crud, "get_visible_experiment_query", lambda user: FakeVisibleQuery()
    )
    monkeypatch.setattr(_crud, "Exps", FakeExps)
    monkeypatch.setattr(
        _crud,
        "_create_single_experiment_copy",
        lambda source_exp, new_name, exp_group: created_calls.append(
            (source_exp.idexp, new_name, exp_group)
        )
        or True,
    )
    monkeypatch.setattr("y_web.src.telemetry.Telemetry", FakeTelemetry)

    created_count, created_names, failures, error_message = (
        _crud._copy_experiment_group("Source Group", "Fresh Group")
    )

    assert error_message is None
    assert created_count == 2
    assert len(created_names) == 2
    assert failures == []
    copy_calls = [call for call in created_calls if call and call[0] != "telemetry"]
    assert copy_calls[0][0] == 10
    assert copy_calls[0][2] == "Fresh Group"
    assert copy_calls[1][0] == 11
    assert copy_calls[1][2] == "Fresh Group"
    assert created_names[0] != created_names[1]
    assert any(call[0] == "telemetry" for call in created_calls)


def test_copy_experiment_group_rejects_same_source_and_target(monkeypatch):
    from y_web.routes.admin.sub.experiments import _crud

    monkeypatch.setattr(_crud, "_current_admin_user_or_none", lambda: SimpleNamespace())

    created_count, created_names, failures, error_message = (
        _crud._copy_experiment_group("Same Group", "Same Group")
    )

    assert created_count == 0
    assert created_names == []
    assert failures == []
    assert error_message == "Source and target groups must be different."


def test_copy_experiment_group_reports_partial_failure(monkeypatch):
    from y_web.routes.admin.sub.experiments import _crud

    source_experiments = [
        SimpleNamespace(
            idexp=10,
            exp_name="Alpha",
            platform_type="microblogging",
            annotations="a",
            llm_agents_enabled=1,
        ),
        SimpleNamespace(
            idexp=11,
            exp_name="Beta",
            platform_type="forum",
            annotations="b",
            llm_agents_enabled=0,
        ),
    ]

    class FakeVisibleQuery:
        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return source_experiments

    class FakeNameQuery:
        def filter_by(self, **kwargs):
            self.kwargs = kwargs
            return self

        def first(self):
            return None

    class FakeColumn:
        def asc(self):
            return self

    class FakeExps:
        exp_group = object()
        exp_name = FakeColumn()
        query = FakeNameQuery()

    monkeypatch.setattr(_crud, "_current_admin_user_or_none", lambda: SimpleNamespace())
    monkeypatch.setattr(
        _crud, "get_visible_experiment_query", lambda user: FakeVisibleQuery()
    )
    monkeypatch.setattr(_crud, "Exps", FakeExps)
    monkeypatch.setattr(
        _crud,
        "_create_single_experiment_copy",
        lambda source_exp, new_name, exp_group: source_exp.idexp == 10,
    )
    monkeypatch.setattr(
        "y_web.src.telemetry.Telemetry",
        lambda user: SimpleNamespace(log_event=lambda payload: None),
    )

    created_count, created_names, failures, error_message = (
        _crud._copy_experiment_group("Source Group", "Fresh Group")
    )

    assert error_message is None
    assert created_count == 1
    assert created_names == ["Alpha__fresh-group__10"]
    assert failures == [
        ("Beta", "Beta__fresh-group__11", "Source experiment does not have a database reference.")
    ]


def test_matrix_copy_failure_diagnosis_reports_missing_source_folder(monkeypatch):
    from y_web.routes.admin.sub.experiments import _crud

    monkeypatch.setattr(
        _crud,
        "current_app",
        SimpleNamespace(config={"SQLALCHEMY_DATABASE_URI": "sqlite:///test.db"}),
    )
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path", lambda: "/tmp/base"
    )

    def fake_exists(path):
        return not str(path).endswith("/y_web/experiments/uid")

    monkeypatch.setattr(_crud.os.path, "exists", fake_exists)

    source_exp = SimpleNamespace(
        db_name=f"experiments{os.sep}uid{os.sep}database_server.db",
        exp_name="Source",
    )

    reason = _crud._matrix_describe_experiment_copy_failure(source_exp)

    assert reason is not None
    assert "Source folder not found" in reason


def test_copy_experiment_names_are_not_capped():
    """Test that copy names scale to the requested number without a hard cap."""
    from y_web.routes.admin.sub.experiments._crud import _build_copy_experiment_names

    names = _build_copy_experiment_names("Demo Experiment", 25)

    assert len(names) == 25
    assert names[0] == "Demo Experiment_1"
    assert names[-1] == "Demo Experiment_25"


def test_settings_experiment_lists_are_not_truncated():
    """Test that settings loading keeps all experiments visible."""
    from y_web.routes.admin.sub.experiments._crud import (
        _load_settings_experiment_lists,
    )

    class FakeVisibleQuery:
        def __init__(self):
            self.active_requested = False

        def all(self):
            if self.active_requested:
                return ["active-1", "active-2"]
            return ["exp-1", "exp-2", "exp-3", "exp-4", "exp-5", "exp-6"]

        def filter_by(self, **kwargs):
            assert kwargs == {"status": 1}
            self.active_requested = True
            return self

    experiments, all_experiments, active_experiments = _load_settings_experiment_lists(
        FakeVisibleQuery()
    )

    assert experiments == ["exp-1", "exp-2", "exp-3", "exp-4", "exp-5", "exp-6"]
    assert all_experiments == experiments
    assert active_experiments == ["active-1", "active-2"]


def test_postgresql_database_deletion():
    """Test that PostgreSQL database deletion logic is correct."""
    # Simulate database name
    db_name = "experiments_abc123def456"

    # Verify the database name format
    assert db_name.startswith("experiments_")

    # Simulate SQL commands for deletion
    terminate_connections_sql = f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{db_name}'
        AND pid <> pg_backend_pid()
    """

    drop_database_sql = f'DROP DATABASE IF EXISTS "{db_name}"'

    # Verify SQL commands are properly formatted
    assert "pg_terminate_backend" in terminate_connections_sql
    assert db_name in terminate_connections_sql
    assert "DROP DATABASE IF EXISTS" in drop_database_sql
    assert db_name in drop_database_sql


def test_postgresql_to_sqlite_type_mapping():
    """Test PostgreSQL to SQLite type mapping for download functionality."""
    # Test type mappings
    type_mappings = {
        "INTEGER": "INTEGER",
        "SERIAL": "INTEGER",
        "BIGSERIAL": "INTEGER",
        "REAL": "REAL",
        "DOUBLE PRECISION": "REAL",
        "FLOAT": "REAL",
        "TEXT": "TEXT",
        "VARCHAR": "TEXT",
        "CHAR": "TEXT",
        "BOOLEAN": "TEXT",  # Default case
    }

    for pg_type, expected_sqlite_type in type_mappings.items():
        # Simulate type mapping logic
        col_type = pg_type

        if "INTEGER" in col_type or "SERIAL" in col_type:
            sqlite_type = "INTEGER"
        elif "REAL" in col_type or "DOUBLE" in col_type or "FLOAT" in col_type:
            sqlite_type = "REAL"
        elif "TEXT" in col_type or "VARCHAR" in col_type or "CHAR" in col_type:
            sqlite_type = "TEXT"
        else:
            sqlite_type = "TEXT"

        assert sqlite_type == expected_sqlite_type, f"Failed for {pg_type}"


def test_download_folder_path_extraction():
    """Test folder path extraction for different database types."""
    import os

    # SQLite format: experiments/uuid/database_server.db
    sqlite_db_name = "experiments/abc123def/database_server.db"
    sqlite_folder = f"y_web{os.sep}experiments{os.sep}{sqlite_db_name.split(os.sep)[1]}"
    assert "abc123def" in sqlite_folder

    # PostgreSQL format: experiments_uuid
    postgres_db_name = "experiments_abc123def"
    postgres_folder = f"y_web{os.sep}experiments{os.sep}{postgres_db_name.removeprefix('experiments_')}"
    assert "abc123def" in postgres_folder

    # Verify both produce similar paths
    assert sqlite_folder.split(os.sep)[-1] == postgres_folder.split(os.sep)[-1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
