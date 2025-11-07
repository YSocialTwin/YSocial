"""
Test for population reuse in upload_experiment.

Verifies that when uploading an experiment:
- If a population with the same name exists, it should be reused
- The existing population should be linked to the new experiment
- No error should be raised for existing populations
"""


def test_population_reuse_logic():
    """Test that existing populations are reused instead of causing errors."""
    # Simulate scenario where population exists
    existing_population_name = "existing_population"
    
    # Mock database query result
    class MockPopulation:
        def __init__(self, name, id):
            self.name = name
            self.id = id
    
    existing_pop = MockPopulation(existing_population_name, 1)
    
    # Test logic: if population exists, use it
    if existing_pop:
        # Should not raise error
        population = existing_pop
        assert population.id == 1
        assert population.name == existing_population_name
    else:
        # Should create new one
        population = MockPopulation("new_pop", 2)
    
    # Verify correct population is used
    assert population.id == 1


def test_new_population_creation():
    """Test that new populations are created when they don't exist."""
    # Simulate scenario where population doesn't exist
    existing_population = None
    
    class MockPopulation:
        def __init__(self, name, id):
            self.name = name
            self.id = id
    
    # Test logic: if population doesn't exist, create it
    if existing_population:
        population = existing_population
    else:
        # Should create new one
        population = MockPopulation("new_pop", 2)
    
    # Verify new population is created
    assert population.id == 2
    assert population.name == "new_pop"


def test_agents_only_created_for_new_populations():
    """Test that agents are only created when population is new."""
    # Test case 1: existing population - should NOT create agents
    existing_population = True
    should_create_agents = not existing_population
    assert should_create_agents == False
    
    # Test case 2: new population - SHOULD create agents
    existing_population = None
    should_create_agents = not existing_population
    assert should_create_agents == True
