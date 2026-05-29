"""
Test for experiment group field functionality.

Verifies that the exp_group field is correctly added to the Exps model
and can be set during experiment creation.
"""

import pytest

pytestmark = pytest.mark.integration


def _setup_exps_model_for_test(app):
    """Helper function to set up Exps model for testing.

    This avoids duplicate code and provides consistent test setup.
    """
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        # Override bind_key for testing to use the test database
        original_bind_key = Exps.__bind_key__
        Exps.__bind_key__ = None

        # Create tables
        db.create_all()

        # Return the model and original bind_key for cleanup
        return Exps, db, original_bind_key


def test_exps_model_has_exp_group_field():
    """Test that Exps model has exp_group field."""
    from y_web.src.models import Exps

    # Check that the model has the exp_group attribute
    assert hasattr(Exps, "exp_group"), "Exps model should have exp_group field"


def test_exp_group_field_in_database(app):
    """Test that exp_group field exists in database schema."""
    Exps, db, original_bind_key = _setup_exps_model_for_test(app)

    try:
        with app.app_context():
            # Create an experiment with a group
            exp = Exps(
                exp_name="Test Experiment",
                platform_type="microblogging",
                db_name="test_db",
                owner="admin",
                exp_descr="Test description",
                status=0,
                running=0,
                port=5000,
                server="127.0.0.1",
                exp_group="Test Group",
            )
            db.session.add(exp)
            db.session.commit()

            # Retrieve the experiment
            retrieved_exp = Exps.query.filter_by(exp_name="Test Experiment").first()

            # Verify the group field was saved correctly
            assert retrieved_exp is not None, "Experiment should be created"
            assert (
                retrieved_exp.exp_group == "Test Group"
            ), "Experiment group should be 'Test Group'"
    finally:
        # Restore original bind_key
        Exps.__bind_key__ = original_bind_key


def test_exp_group_field_optional(app):
    """Test that exp_group field is optional."""
    Exps, db, original_bind_key = _setup_exps_model_for_test(app)

    try:
        with app.app_context():
            # Create an experiment without a group
            exp = Exps(
                exp_name="Test Experiment No Group",
                platform_type="microblogging",
                db_name="test_db_2",
                owner="admin",
                exp_descr="Test description",
                status=0,
                running=0,
                port=5001,
                server="127.0.0.1",
            )
            db.session.add(exp)
            db.session.commit()

            # Retrieve the experiment
            retrieved_exp = Exps.query.filter_by(
                exp_name="Test Experiment No Group"
            ).first()

            # Verify the experiment was created without a group
            assert retrieved_exp is not None, "Experiment should be created"
            # exp_group should be empty string (default)
            assert (
                retrieved_exp.exp_group == "" or retrieved_exp.exp_group is None
            ), "Experiment group should be empty"
    finally:
        # Restore original bind_key
        Exps.__bind_key__ = original_bind_key

