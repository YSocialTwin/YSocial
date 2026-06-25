from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_populations_data_uses_username_type_for_platform_column(app):
    from y_web.routes.admin.sub import populations as populations_module

    pop = SimpleNamespace(
        id=1,
        name="Photo Pop",
        size=25,
        education="",
        leanings="",
        toxicity="",
        username_type="photo_sharing",
        pop_type=None,
    )

    with app.test_request_context("/admin/populations_data"):
        with (
            patch.object(
                populations_module,
                "ensure_population_username_type_column",
                return_value=None,
            ),
            patch.object(populations_module.Population, "query") as mock_query,
            patch.object(populations_module.ActivityProfile, "query") as mock_ap_query,
            patch.object(populations_module.Education, "query") as mock_edu_query,
            patch.object(populations_module.Leanings, "query") as mock_lean_query,
            patch.object(populations_module.Toxicity_Levels, "query") as mock_tox_query,
            patch.object(populations_module.db.session, "query") as mock_session_query,
        ):
            mock_query.filter.return_value.count.return_value = 1
            mock_query.filter.return_value.all.return_value = [pop]
            mock_ap_query.join.return_value.filter.return_value.all.return_value = []
            mock_edu_query.all.return_value = []
            mock_lean_query.all.return_value = []
            mock_tox_query.all.return_value = []
            mock_session_query.return_value.join.return_value.filter.return_value.all.return_value = []

            response = populations_module.populations_data.__wrapped__()

    assert response["data"][0]["platform_type"] == "photo_sharing"
    assert response["data"][0]["username_type"] == "photo_sharing"
