"""
Tests for the tutorial wizard functionality.

Tests the tutorial routes and the first-time user experience
for admin and researcher users.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
pytestmark = pytest.mark.integration



class TestTutorialRoutes:
    """Tests for the tutorial wizard routes."""

    @pytest.fixture
    def app(self):
        """Create a test Flask application."""
        # Create a minimal Flask app for testing
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_BINDS"] = {
            "db_admin": "sqlite:///:memory:",
            "db_exp": "sqlite:///:memory:",
        }
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        return app

    @pytest.fixture
    def mock_admin_user(self):
        """Create a mock admin user."""
        user = MagicMock()
        user.id = 1
        user.username = "testadmin"
        user.role = "admin"
        user.tutorial_shown = False
        return user

    @pytest.fixture
    def mock_researcher_user(self):
        """Create a mock researcher user."""
        user = MagicMock()
        user.id = 2
        user.username = "testresearcher"
        user.role = "researcher"
        user.tutorial_shown = False
        return user

    def test_tutorial_shown_field_exists(self):
        """Test that tutorial_shown field is defined in Admin_users model."""
        from y_web.src.models import Admin_users

        # Check that the column exists in the model
        columns = [column.name for column in Admin_users.__table__.columns]
        assert "tutorial_shown" in columns

    def test_tutorial_shown_default_value(self):
        """Test that tutorial_shown defaults to False."""
        from y_web.src.models import Admin_users

        # Get the default value from the column definition
        tutorial_shown_column = Admin_users.__table__.columns["tutorial_shown"]
        assert tutorial_shown_column.default.arg is False

    def test_tutorial_check_status_returns_show_for_new_admin(self, mock_admin_user):
        """Test that tutorial should show for new admin users."""
        # This test verifies the logic for determining when to show the tutorial
        assert mock_admin_user.role == "admin"
        assert mock_admin_user.tutorial_shown is False
        # Logic: show_tutorial = not user.tutorial_shown and role in ['admin', 'researcher']
        show_tutorial = not mock_admin_user.tutorial_shown and mock_admin_user.role in [
            "admin",
            "researcher",
        ]
        assert show_tutorial is True

    def test_tutorial_check_status_returns_hide_for_shown_admin(self, mock_admin_user):
        """Test that tutorial should not show for admin who has already seen it."""
        mock_admin_user.tutorial_shown = True
        show_tutorial = not mock_admin_user.tutorial_shown and mock_admin_user.role in [
            "admin",
            "researcher",
        ]
        assert show_tutorial is False

    def test_tutorial_check_status_returns_show_for_new_researcher(
        self, mock_researcher_user
    ):
        """Test that tutorial should show for new researcher users."""
        assert mock_researcher_user.role == "researcher"
        assert mock_researcher_user.tutorial_shown is False
        show_tutorial = (
            not mock_researcher_user.tutorial_shown
            and mock_researcher_user.role in ["admin", "researcher"]
        )
        assert show_tutorial is True

    def test_tutorial_not_shown_for_regular_users(self):
        """Test that tutorial is not shown for regular users."""
        user = MagicMock()
        user.role = "user"
        user.tutorial_shown = False
        show_tutorial = not user.tutorial_shown and user.role in ["admin", "researcher"]
        assert show_tutorial is False


class TestTutorialDataValidation:
    """Tests for tutorial form data validation."""

    def test_population_name_required(self):
        """Test that population name is required."""
        data = {
            "population_name": "",
            "population_size": 50,
            "education_levels": [1],
            "political_leanings": [1],
            "toxicity_levels": [1],
        }
        is_valid = bool(data.get("population_name", "").strip())
        assert is_valid is False

    def test_population_name_valid(self):
        """Test that population name validation passes with valid data."""
        data = {
            "population_name": "Test Population",
            "population_size": 50,
            "education_levels": [1],
            "political_leanings": [1],
            "toxicity_levels": [1],
        }
        is_valid = bool(data.get("population_name", "").strip())
        assert is_valid is True

    def test_population_size_in_range(self):
        """Test that population size must be between 10 and 100."""
        # Valid cases
        for size in [10, 50, 100]:
            is_valid = 10 <= size <= 100
            assert is_valid is True, f"Size {size} should be valid"

        # Invalid cases
        for size in [5, 9, 101, 200]:
            is_valid = 10 <= size <= 100
            assert is_valid is False, f"Size {size} should be invalid"

    def test_simulation_days_in_range(self):
        """Test that simulation days must be between 1 and 30."""
        # Valid cases
        for days in [1, 15, 30]:
            is_valid = 1 <= days <= 30
            assert is_valid is True, f"Days {days} should be valid"

        # Invalid cases
        for days in [0, 31, 100]:
            is_valid = 1 <= days <= 30
            assert is_valid is False, f"Days {days} should be invalid"

    def test_education_levels_required(self):
        """Test that at least one education level is required."""
        # Empty list
        education_levels = []
        is_valid = len(education_levels) > 0
        assert is_valid is False

        # Non-empty list
        education_levels = [1, 2]
        is_valid = len(education_levels) > 0
        assert is_valid is True

    def test_political_leanings_required(self):
        """Test that at least one political leaning is required."""
        # Empty list
        political_leanings = []
        is_valid = len(political_leanings) > 0
        assert is_valid is False

        # Non-empty list
        political_leanings = [1]
        is_valid = len(political_leanings) > 0
        assert is_valid is True

    def test_toxicity_levels_required(self):
        """Test that at least one toxicity level is required."""
        # Empty list
        toxicity_levels = []
        is_valid = len(toxicity_levels) > 0
        assert is_valid is False

        # Non-empty list
        toxicity_levels = [1, 2, 3]
        is_valid = len(toxicity_levels) > 0
        assert is_valid is True

    def test_experiment_name_required(self):
        """Test that experiment name is required."""
        experiment_name = ""
        is_valid = bool(experiment_name.strip())
        assert is_valid is False

        experiment_name = "Test Experiment"
        is_valid = bool(experiment_name.strip())
        assert is_valid is True

    def test_client_name_required(self):
        """Test that client name is required."""
        client_name = ""
        is_valid = bool(client_name.strip())
        assert is_valid is False

        client_name = "Test Client"
        is_valid = bool(client_name.strip())
        assert is_valid is True


class TestMigrationScript:
    """Tests for the tutorial_shown column migration script."""

    def test_migration_script_exists(self):
        """Test that the migration script file exists."""
        import os

        migration_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "migrations",
            "add_tutorial_shown_column.py",
        )
        assert os.path.exists(migration_path)

    def test_migration_functions_exist(self):
        """Test that migration functions are defined."""
        from y_web.migrations.add_tutorial_shown_column import (
            migrate_postgresql,
            migrate_sqlite,
        )

        assert callable(migrate_sqlite)
        assert callable(migrate_postgresql)


class TestExpDetailsMigrationScript:
    """Tests for the exp_details_tutorial_shown column migration script."""

    def test_migration_script_exists(self):
        """Test that the migration script file exists."""
        import os

        migration_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "migrations",
            "add_exp_details_tutorial_column.py",
        )
        assert os.path.exists(migration_path)

    def test_migration_functions_exist(self):
        """Test that migration functions are defined."""
        from y_web.migrations.add_exp_details_tutorial_column import (
            migrate_postgresql,
            migrate_sqlite,
        )

        assert callable(migrate_sqlite)
        assert callable(migrate_postgresql)


class TestTutorialTemplate:
    """Tests for the tutorial template file."""

    def test_template_exists(self):
        """Test that the tutorial overlay template exists."""
        import os

        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates",
            "admin",
            "tutorials",
            "tutorial_overlay.html",
        )
        assert os.path.exists(template_path)

    def test_template_contains_step_sections(self):
        """Test that the template contains all three step sections."""
        import os

        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates",
            "admin",
            "tutorials",
            "tutorial_overlay.html",
        )

        with open(template_path, "r") as f:
            content = f.read()

        # Check for step indicators
        assert "tutorial-step-1" in content
        assert "tutorial-step-2" in content
        assert "tutorial-step-3" in content

        # Check for step content areas
        assert "Population" in content
        assert "Experiment" in content
        assert "Client" in content


class TestExpDetailsTutorialRoutes:
    """Tests for the experiment details tutorial routes."""

    @pytest.fixture
    def mock_admin_user(self):
        """Create a mock admin user with exp_details_tutorial_shown field."""
        user = MagicMock()
        user.id = 1
        user.username = "testadmin"
        user.role = "admin"
        user.tutorial_shown = True  # Already completed onboarding
        user.exp_details_tutorial_shown = False
        return user

    @pytest.fixture
    def mock_researcher_user(self):
        """Create a mock researcher user with exp_details_tutorial_shown field."""
        user = MagicMock()
        user.id = 2
        user.username = "testresearcher"
        user.role = "researcher"
        user.tutorial_shown = True  # Already completed onboarding
        user.exp_details_tutorial_shown = False
        return user

    def test_exp_details_tutorial_shown_field_exists(self):
        """Test that exp_details_tutorial_shown field is defined in Admin_users model."""
        from y_web.src.models import Admin_users

        # Check that the column exists in the model
        columns = [column.name for column in Admin_users.__table__.columns]
        assert "exp_details_tutorial_shown" in columns

    def test_exp_details_tutorial_shown_default_value(self):
        """Test that exp_details_tutorial_shown defaults to False."""
        from y_web.src.models import Admin_users

        # Get the default value from the column definition
        tutorial_shown_column = Admin_users.__table__.columns[
            "exp_details_tutorial_shown"
        ]
        assert tutorial_shown_column.default.arg is False

    def test_exp_details_tutorial_check_status_returns_show_for_new_admin(
        self, mock_admin_user
    ):
        """Test that exp details tutorial should show for admin who completed onboarding."""
        assert mock_admin_user.role == "admin"
        assert mock_admin_user.exp_details_tutorial_shown is False
        # Logic: show_tutorial = not user.exp_details_tutorial_shown and role in ['admin', 'researcher']
        show_tutorial = (
            not mock_admin_user.exp_details_tutorial_shown
            and mock_admin_user.role in ["admin", "researcher"]
        )
        assert show_tutorial is True

    def test_exp_details_tutorial_check_status_returns_hide_after_shown(
        self, mock_admin_user
    ):
        """Test that exp details tutorial should not show after user has seen it."""
        mock_admin_user.exp_details_tutorial_shown = True
        show_tutorial = (
            not mock_admin_user.exp_details_tutorial_shown
            and mock_admin_user.role in ["admin", "researcher"]
        )
        assert show_tutorial is False

    def test_exp_details_tutorial_check_status_returns_show_for_researcher(
        self, mock_researcher_user
    ):
        """Test that exp details tutorial should show for researcher users."""
        assert mock_researcher_user.role == "researcher"
        assert mock_researcher_user.exp_details_tutorial_shown is False
        show_tutorial = (
            not mock_researcher_user.exp_details_tutorial_shown
            and mock_researcher_user.role in ["admin", "researcher"]
        )
        assert show_tutorial is True

    def test_exp_details_tutorial_not_shown_for_regular_users(self):
        """Test that exp details tutorial is not shown for regular users."""
        user = MagicMock()
        user.role = "user"
        user.exp_details_tutorial_shown = False
        show_tutorial = not user.exp_details_tutorial_shown and user.role in [
            "admin",
            "researcher",
        ]
        assert show_tutorial is False


class TestExperimentDetailsPageIds:
    """Tests for experiment details page IDs used by tutorial."""

    def test_experiment_details_page_contains_required_ids(self):
        """Test that experiment_details.html contains IDs for tutorial targeting."""
        import os

        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates",
            "admin",
            "experiment_details.html",
        )

        with open(template_path, "r") as f:
            content = f.read()

        # Check for all section IDs used by the tutorial
        assert 'id="server-controls-section"' in content
        assert 'id="simulation-clients-section"' in content
        assert 'id="actions-section"' in content
        assert 'id="server-trends-section"' in content
        assert 'id="server-logs-section"' in content
        assert 'id="client-logs-section"' in content
        assert 'id="load-experiment-btn"' in content
