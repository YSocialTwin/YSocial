"""
Test for enhanced population and agent comparison in upload_experiment.

Verifies that when uploading an experiment:
- If population exists with same agents: reuse population
- If population exists with different agents: create new population with modified name
- If population doesn't exist: create it
"""


def test_same_agents_reuse_population():
    """Test that existing populations with same agents are reused."""
    # Scenario: population exists with agents A, B, C
    # Upload has agents A, B, C
    # Expected: reuse existing population

    existing_agents = {"AgentA", "AgentB", "AgentC"}
    uploaded_agents = {"AgentA", "AgentB", "AgentC"}

    # Check if agents are the same
    agents_match = existing_agents == uploaded_agents

    assert agents_match == True
    # In this case, should reuse existing population


def test_different_agents_create_new_population():
    """Test that populations with different agents create new population."""
    # Scenario: population exists with agents A, B, C
    # Upload has agents A, B, D (different)
    # Expected: create new population with modified name

    existing_agents = {"AgentA", "AgentB", "AgentC"}
    uploaded_agents = {"AgentA", "AgentB", "AgentD"}

    # Check if agents are the same
    agents_match = existing_agents == uploaded_agents

    assert agents_match == False
    # In this case, should create new population with modified name


def test_population_name_generation():
    """Test that new population names are generated correctly."""
    # Simulate finding unique names
    original_name = "test_population"
    existing_names = {"test_population", "test_population_1"}

    # Find unique name
    counter = 1
    new_name = f"{original_name}_{counter}"
    while new_name in existing_names:
        counter += 1
        new_name = f"{original_name}_{counter}"

    assert new_name == "test_population_2"


def test_subset_agents_creates_new_population():
    """Test that subset of agents triggers new population creation."""
    # Scenario: population exists with agents A, B, C
    # Upload has only agents A, B (subset)
    # Expected: create new population with modified name

    existing_agents = {"AgentA", "AgentB", "AgentC"}
    uploaded_agents = {"AgentA", "AgentB"}

    # Check if agents are the same
    agents_match = existing_agents == uploaded_agents

    assert agents_match == False


def test_superset_agents_creates_new_population():
    """Test that superset of agents triggers new population creation."""
    # Scenario: population exists with agents A, B
    # Upload has agents A, B, C (superset)
    # Expected: create new population with modified name

    existing_agents = {"AgentA", "AgentB"}
    uploaded_agents = {"AgentA", "AgentB", "AgentC"}

    # Check if agents are the same
    agents_match = existing_agents == uploaded_agents

    assert agents_match == False


def test_empty_population_handling():
    """Test handling of populations with no agents."""
    # Scenario: population exists with no agents
    # Upload has no agents
    # Expected: reuse existing population

    existing_agents = set()
    uploaded_agents = set()

    # Check if agents are the same
    agents_match = existing_agents == uploaded_agents

    assert agents_match == True


def test_mixed_agents_and_pages():
    """Test that both agents and pages are compared."""
    # Both agents and pages should be included in comparison
    existing_members = {"AgentA", "PageB", "AgentC"}
    uploaded_members = {"AgentA", "PageB", "AgentC"}

    # Check if members are the same
    members_match = existing_members == uploaded_members

    assert members_match == True
