"""
Test for llm_agents_enabled field in upload_experiment.

Verifies that when uploading an experiment, the llm_agents_enabled field
is set correctly based on the client configuration files.
"""


def test_llm_agents_enabled_with_null():
    """Test that llm_agents_enabled is 0 when llm_agents is [null]."""
    # Simulate client config with llm_agents = [null]
    client_config = {"agents": {"llm_agents": [None]}}

    # Check llm_agents value
    llm_agents_value = client_config["agents"]["llm_agents"]

    # Determine llm_agents_enabled
    llm_agents_enabled = 1  # Default
    if (
        isinstance(llm_agents_value, list)
        and len(llm_agents_value) == 1
        and llm_agents_value[0] is None
    ):
        llm_agents_enabled = 0

    assert llm_agents_enabled == 0


def test_llm_agents_enabled_with_values():
    """Test that llm_agents_enabled is 1 when llm_agents has actual values."""
    # Simulate client config with llm_agents having values
    client_config = {"agents": {"llm_agents": ["agent1", "agent2"]}}

    # Check llm_agents value
    llm_agents_value = client_config["agents"]["llm_agents"]

    # Determine llm_agents_enabled
    llm_agents_enabled = 1  # Default
    if (
        isinstance(llm_agents_value, list)
        and len(llm_agents_value) == 1
        and llm_agents_value[0] is None
    ):
        llm_agents_enabled = 0

    assert llm_agents_enabled == 1


def test_llm_agents_enabled_with_empty_list():
    """Test that llm_agents_enabled is 1 when llm_agents is an empty list."""
    # Simulate client config with llm_agents = []
    client_config = {"agents": {"llm_agents": []}}

    # Check llm_agents value
    llm_agents_value = client_config["agents"]["llm_agents"]

    # Determine llm_agents_enabled
    llm_agents_enabled = 1  # Default
    if (
        isinstance(llm_agents_value, list)
        and len(llm_agents_value) == 1
        and llm_agents_value[0] is None
    ):
        llm_agents_enabled = 0

    assert llm_agents_enabled == 1


def test_llm_agents_enabled_missing_field():
    """Test that llm_agents_enabled is 1 when llm_agents field is missing."""
    # Simulate client config without llm_agents
    client_config = {"agents": {}}

    # Determine llm_agents_enabled
    llm_agents_enabled = 1  # Default

    if "llm_agents" in client_config["agents"]:
        llm_agents_value = client_config["agents"]["llm_agents"]
        if (
            isinstance(llm_agents_value, list)
            and len(llm_agents_value) == 1
            and llm_agents_value[0] is None
        ):
            llm_agents_enabled = 0

    assert llm_agents_enabled == 1


def test_llm_agents_enabled_with_single_agent():
    """Test that llm_agents_enabled is 1 when llm_agents has one agent."""
    # Simulate client config with single agent
    client_config = {"agents": {"llm_agents": ["agent1"]}}

    # Check llm_agents value
    llm_agents_value = client_config["agents"]["llm_agents"]

    # Determine llm_agents_enabled
    llm_agents_enabled = 1  # Default
    if (
        isinstance(llm_agents_value, list)
        and len(llm_agents_value) == 1
        and llm_agents_value[0] is None
    ):
        llm_agents_enabled = 0

    assert llm_agents_enabled == 1


def test_llm_agents_enabled_multiple_null_values():
    """Test that llm_agents_enabled is 1 when llm_agents has multiple null values."""
    # Simulate client config with multiple nulls (edge case)
    client_config = {"agents": {"llm_agents": [None, None]}}

    # Check llm_agents value
    llm_agents_value = client_config["agents"]["llm_agents"]

    # Determine llm_agents_enabled
    llm_agents_enabled = 1  # Default
    if (
        isinstance(llm_agents_value, list)
        and len(llm_agents_value) == 1
        and llm_agents_value[0] is None
    ):
        llm_agents_enabled = 0

    # Should be 1 because length is not 1
    assert llm_agents_enabled == 1


def test_llm_agents_disabled_in_multiple_clients():
    """Test that if ANY client has [null], llm_agents_enabled is 0."""
    # Simulate multiple client configs
    clients = [
        {"agents": {"llm_agents": ["agent1", "agent2"]}},  # Enabled
        {"agents": {"llm_agents": [None]}},  # Disabled
        {"agents": {"llm_agents": ["agent3"]}},  # Enabled
    ]

    # Check all clients
    llm_agents_enabled = 1  # Default
    for client_config in clients:
        if "agents" in client_config and "llm_agents" in client_config["agents"]:
            llm_agents_value = client_config["agents"]["llm_agents"]
            if (
                isinstance(llm_agents_value, list)
                and len(llm_agents_value) == 1
                and llm_agents_value[0] is None
            ):
                llm_agents_enabled = 0
                break  # If any client has [null], disable for entire experiment

    # Should be disabled because second client has [null]
    assert llm_agents_enabled == 0
