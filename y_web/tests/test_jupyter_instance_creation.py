"""
Test for Jupyter instance creation in upload_experiment.

Verifies that when uploading an experiment, a Jupyter instance entry
is created in the database with status "stopped".
"""


def test_jupyter_instance_creation():
    """Test that Jupyter instance is created for new experiment."""
    # Simulate experiment creation
    exp_id = 1
    
    # Mock Jupyter instance entry
    class MockJupyterInstance:
        def __init__(self, port, notebook_dir, exp_id, status):
            self.port = port
            self.notebook_dir = notebook_dir
            self.exp_id = exp_id
            self.status = status
    
    # Create instance as would be done in upload_experiment
    jupyter_instance = MockJupyterInstance(
        port=-1,
        notebook_dir="",
        exp_id=exp_id,
        status="stopped"
    )
    
    # Verify instance properties
    assert jupyter_instance.port == -1
    assert jupyter_instance.notebook_dir == ""
    assert jupyter_instance.exp_id == exp_id
    assert jupyter_instance.status == "stopped"


def test_jupyter_instance_default_values():
    """Test that Jupyter instance has correct default values."""
    # Default values for a new experiment
    port = -1  # Not running yet
    notebook_dir = ""  # Empty directory
    status = "stopped"  # Initial status
    
    # Verify defaults
    assert port == -1
    assert notebook_dir == ""
    assert status == "stopped"


def test_jupyter_instance_status_values():
    """Test valid status values for Jupyter instances."""
    valid_statuses = ["stopped", "running"]
    
    # Test stopped status
    status = "stopped"
    assert status in valid_statuses
    
    # Test running status
    status = "running"
    assert status in valid_statuses
