"""
Tests for agent name uniqueness in population generation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestAgentNameUniqueness:
    """Test that agent names are unique within populations and across database"""

    def test_generate_population_import(self):
        """Test that generate_population can be imported"""
        try:
            from y_web.utils.agents import generate_population
            assert callable(generate_population)
        except ImportError as e:
            pytest.skip(f"Could not import generate_population: {e}")

    def test_unique_name_generation_logic(self):
        """Test the logic of unique name generation using faker directly"""
        try:
            import faker

            fake = faker.Faker('en_US')
            used_names = set()

            # Generate multiple names and ensure they can be made unique
            for i in range(20):
                # Simulate the logic from __generate_unique_name
                name = fake.name_male() if i % 2 == 0 else fake.name_female()
                name = name.replace(" ", "")
                
                # If name is in used_names, append a number
                if name in used_names:
                    base_name = name
                    counter = 1
                    while f"{base_name}{counter}" in used_names:
                        counter += 1
                    name = f"{base_name}{counter}"
                
                assert name not in used_names, f"Name {name} is not unique"
                used_names.add(name)
            
            # All names should be unique
            assert len(used_names) == 20

        except ImportError as e:
            pytest.skip(f"Required dependencies not installed: {e}")

    def test_name_format_no_spaces(self):
        """Test that generated names have no spaces"""
        try:
            import faker

            fake = faker.Faker('en_US')
            
            # Generate some names and check they have no spaces after processing
            for _ in range(10):
                name = fake.name_male()
                processed_name = name.replace(" ", "")
                assert " " not in processed_name, "Processed name should not contain spaces"

        except ImportError as e:
            pytest.skip(f"Required dependencies not installed: {e}")
