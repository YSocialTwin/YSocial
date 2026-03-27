"""
Test for bulk insert optimization in population generation.

Verifies that the generate_population function uses efficient bulk inserts
instead of individual inserts for each agent.
"""

from unittest.mock import MagicMock, patch

import pytest

from y_web.src.agents.population import generate_population

pytestmark = pytest.mark.unit


def test_generate_population_uses_bulk_insert():
    """Test that generate_population uses bulk_save_objects for efficiency."""

    # Create mock population
    mock_population = MagicMock()
    mock_population.id = 1
    mock_population.name = "test_pop"
    mock_population.size = 10
    mock_population.llm = "user"
    mock_population.nationalities = "American"
    mock_population.languages = "en"
    mock_population.frecsys = "default"
    mock_population.crecsys = "default"

    # Mock percentages
    mock_percentages = {
        "age_classes": {"1": 100.0},
        "education": {"1": 100.0},
        "political_leanings": {"1": 100.0},
        "toxicity_levels": {"1": 100.0},
        "gender": {"male": 50, "female": 50},
    }

    # Mock actions config
    mock_actions_config = {
        "min": "1",
        "max": "5",
        "distribution": "uniform",
    }

    with (
        patch("y_web.src.agents.population.Population") as mock_population_cls,
        patch(
            "y_web.src.agents.population.PopulationActivityProfile"
        ) as mock_profile_cls,
        patch("y_web.src.agents.population.db") as mock_db,
        patch("y_web.src.agents.population.AgeClass") as mock_age_class,
        patch("y_web.src.agents.population.Toxicity_Levels") as mock_toxicity,
        patch("y_web.src.agents.population.Leanings") as mock_leanings,
        patch("y_web.src.agents.population.Profession") as mock_profession,
        patch("y_web.src.agents.population.Education") as mock_education,
    ):
        mock_session = mock_db.session

        # Setup mocks
        mock_population_cls.query.filter_by.return_value.first.return_value = (
            mock_population
        )
        mock_profile_cls.query.filter_by.return_value.all.return_value = []

        # Mock existing agents query (db.session.query(Agent.name).all())
        mock_session.query.return_value.all.return_value = []

        # Mock all db.session.query(Model).filter_by(...).first() results.
        # The same mock chain is used for AgeClass, Toxicity_Levels and Leanings
        # lookups, so a single result object with all required attributes is enough.
        mock_query_result = MagicMock()
        mock_query_result.age_start = 20
        mock_query_result.age_end = 30
        mock_query_result.toxicity_level = "none"
        mock_query_result.leaning = "neutral"
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_query_result
        )

        # Mock age class (used for edu/profession sampling helpers)
        mock_age_obj = MagicMock()
        mock_age_obj.age_start = 20
        mock_age_obj.age_end = 30
        mock_age_class.query.filter_by.return_value.first.return_value = mock_age_obj

        # Mock toxicity
        mock_tox_obj = MagicMock()
        mock_tox_obj.toxicity_level = "none"
        mock_toxicity.query.filter_by.return_value.first.return_value = mock_tox_obj

        # Mock leanings
        mock_lean_obj = MagicMock()
        mock_lean_obj.leaning = "neutral"
        mock_leanings.query.filter_by.return_value.first.return_value = mock_lean_obj

        # Mock profession
        mock_prof_obj = MagicMock()
        mock_prof_obj.profession = "Engineer"
        mock_profession.query.filter_by.return_value.first.return_value = mock_prof_obj
        mock_profession.query.order_by.return_value.first.return_value = mock_prof_obj

        # Mock education
        mock_edu_obj = MagicMock()
        mock_edu_obj.education_level = "Bachelor"
        mock_education.query.filter_by.return_value.first.return_value = mock_edu_obj

        # Call the function
        generate_population("test_pop", mock_percentages, mock_actions_config)

        # Verify bulk_save_objects was called (should be called twice: once for agents, once for relationships)
        assert mock_session.bulk_save_objects.call_count == 2

        # Verify commit was called only once at the end (not per agent)
        assert mock_session.commit.call_count == 1

        # Verify flush was called once (after bulk inserting agents)
        assert mock_session.flush.call_count == 1


def test_bulk_insert_preserves_agent_count():
    """Test that bulk insert creates the correct number of agents."""

    # This test verifies the agents list has the expected size
    mock_population = MagicMock()
    mock_population.id = 1
    mock_population.name = "test_pop"
    mock_population.size = 5  # Small population for testing
    mock_population.llm = "user"
    mock_population.nationalities = "American"
    mock_population.languages = "en"
    mock_population.frecsys = "default"
    mock_population.crecsys = "default"

    mock_percentages = {
        "age_classes": {"1": 100.0},
        "education": {"1": 100.0},
        "political_leanings": {"1": 100.0},
        "toxicity_levels": {"1": 100.0},
        "gender": {"male": 50, "female": 50},
    }

    mock_actions_config = {
        "min": "1",
        "max": "5",
        "distribution": "uniform",
    }

    with (
        patch("y_web.src.agents.population.Population") as mock_population_cls,
        patch(
            "y_web.src.agents.population.PopulationActivityProfile"
        ) as mock_profile_cls,
        patch("y_web.src.agents.population.db") as mock_db,
        patch("y_web.src.agents.population.AgeClass") as mock_age_class,
        patch("y_web.src.agents.population.Toxicity_Levels") as mock_toxicity,
        patch("y_web.src.agents.population.Leanings") as mock_leanings,
        patch("y_web.src.agents.population.Profession") as mock_profession,
        patch("y_web.src.agents.population.Education") as mock_education,
    ):
        mock_session = mock_db.session

        # Setup mocks
        mock_population_cls.query.filter_by.return_value.first.return_value = (
            mock_population
        )
        mock_profile_cls.query.filter_by.return_value.all.return_value = []
        mock_session.query.return_value.all.return_value = []

        # Mock all db.session.query(Model).filter_by(...).first() results
        mock_query_result = MagicMock()
        mock_query_result.age_start = 20
        mock_query_result.age_end = 30
        mock_query_result.toxicity_level = "none"
        mock_query_result.leaning = "neutral"
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_query_result
        )

        # Mock objects
        mock_age_obj = MagicMock()
        mock_age_obj.age_start = 20
        mock_age_obj.age_end = 30
        mock_age_class.query.filter_by.return_value.first.return_value = mock_age_obj

        mock_tox_obj = MagicMock()
        mock_tox_obj.toxicity_level = "none"
        mock_toxicity.query.filter_by.return_value.first.return_value = mock_tox_obj

        mock_lean_obj = MagicMock()
        mock_lean_obj.leaning = "neutral"
        mock_leanings.query.filter_by.return_value.first.return_value = mock_lean_obj

        mock_prof_obj = MagicMock()
        mock_prof_obj.profession = "Engineer"
        mock_profession.query.filter_by.return_value.first.return_value = mock_prof_obj
        mock_profession.query.order_by.return_value.first.return_value = mock_prof_obj

        mock_edu_obj = MagicMock()
        mock_edu_obj.education_level = "Bachelor"
        mock_education.query.filter_by.return_value.first.return_value = mock_edu_obj

        # Call the function
        generate_population("test_pop", mock_percentages, mock_actions_config)

        # Get the first call to bulk_save_objects (agents)
        first_call = mock_session.bulk_save_objects.call_args_list[0]
        agents_list = first_call[0][0]  # First positional argument

        # Verify correct number of agents were created
        assert len(agents_list) == 5

        # Get the second call to bulk_save_objects (relationships)
        second_call = mock_session.bulk_save_objects.call_args_list[1]
        relationships_list = second_call[0][0]

        # Verify correct number of relationships were created
        assert len(relationships_list) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
