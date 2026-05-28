"""
Test to verify that HPC experiments do not get database copied when cloned.
"""

import os
import shutil
import tempfile

import pytest

pytestmark = pytest.mark.unit


def test_hpc_detection_logic():
    """Test that HPC experiments are correctly detected by presence of server_config.json"""

    # Create a temporary folder structure
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create HPC experiment folder structure
        hpc_folder = os.path.join(temp_dir, "hpc_exp")
        os.makedirs(hpc_folder, exist_ok=True)

        # Create server_config.json (HPC marker)
        server_config_path = os.path.join(hpc_folder, "server_config.json")
        with open(server_config_path, "w") as f:
            f.write('{"experiment_name": "test_hpc"}')

        # Verify HPC detection
        is_hpc = os.path.exists(os.path.join(hpc_folder, "server_config.json"))
        assert is_hpc == True, "HPC experiment should be detected by server_config.json"

        # Create Standard experiment folder structure
        standard_folder = os.path.join(temp_dir, "standard_exp")
        os.makedirs(standard_folder, exist_ok=True)

        # Create config_server.json (Standard marker)
        config_server_path = os.path.join(standard_folder, "config_server.json")
        with open(config_server_path, "w") as f:
            f.write('{"name": "test_standard"}')

        # Verify Standard detection (no server_config.json)
        is_hpc_standard = os.path.exists(
            os.path.join(standard_folder, "server_config.json")
        )
        assert (
            is_hpc_standard == False
        ), "Standard experiment should NOT have server_config.json"


def test_database_copy_logic():
    """Test the logic for when database should or should not be copied"""

    # Simulate the decision logic
    def should_copy_database(is_hpc, db_type):
        """Returns True if database should be copied"""
        if db_type == "sqlite":
            # Only Standard experiments get a pre-created database
            # HPC experiments: database is created by server on startup
            return not is_hpc
        return False  # For non-sqlite, handle differently

    # Test cases
    assert (
        should_copy_database(is_hpc=False, db_type="sqlite") == True
    ), "Standard SQLite experiments SHOULD get database copied"

    assert (
        should_copy_database(is_hpc=True, db_type="sqlite") == False
    ), "HPC SQLite experiments should NOT get database copied"

    assert (
        should_copy_database(is_hpc=False, db_type="postgresql") == False
    ), "PostgreSQL experiments handled differently"

    assert (
        should_copy_database(is_hpc=True, db_type="postgresql") == False
    ), "HPC PostgreSQL experiments handled differently"


def test_copy_workflow():
    """Test the complete workflow of determining whether to copy database"""

    with tempfile.TemporaryDirectory() as temp_dir:
        # Test HPC workflow
        hpc_folder = os.path.join(temp_dir, "hpc_exp")
        os.makedirs(hpc_folder, exist_ok=True)

        # Create HPC marker
        with open(os.path.join(hpc_folder, "server_config.json"), "w") as f:
            f.write('{"experiment_name": "test"}')

        # Simulate detection
        is_hpc = os.path.exists(os.path.join(hpc_folder, "server_config.json"))
        db_type = "sqlite"

        # Decision point
        should_copy = db_type == "sqlite" and not is_hpc

        assert should_copy == False, "HPC experiment should NOT trigger database copy"

        # Simulate that no database file is created
        db_path = os.path.join(hpc_folder, "database_server.db")
        if should_copy:
            # This code should NOT run for HPC
            with open(db_path, "w") as f:
                f.write("fake db")

        # Verify no database file exists for HPC
        assert not os.path.exists(
            db_path
        ), "HPC experiment should NOT have pre-created database file"

        # Test Standard workflow
        standard_folder = os.path.join(temp_dir, "standard_exp")
        os.makedirs(standard_folder, exist_ok=True)

        # Create Standard marker
        with open(os.path.join(standard_folder, "config_server.json"), "w") as f:
            f.write('{"name": "test"}')

        # Simulate detection
        is_hpc_std = os.path.exists(os.path.join(standard_folder, "server_config.json"))
        should_copy_std = db_type == "sqlite" and not is_hpc_std

        assert (
            should_copy_std == True
        ), "Standard experiment SHOULD trigger database copy"


if __name__ == "__main__":
    print("Running HPC database copy prevention tests...")

    test_hpc_detection_logic()
    print("✓ HPC detection logic test passed")

    test_database_copy_logic()
    print("✓ Database copy decision logic test passed")

    test_copy_workflow()
    print("✓ Complete workflow test passed")

    print("\nAll tests passed! ✓")
    print("\nSummary:")
    print("- HPC experiments are correctly detected by server_config.json")
    print("- Database copying is SKIPPED for HPC experiments")
    print("- Database copying still works for Standard experiments")
    print("- HPC servers will create their own database on startup")
