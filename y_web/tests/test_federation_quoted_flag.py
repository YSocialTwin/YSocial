"""P3: federation.json asks the coordinator to check the visibility of quoted content when members send exposures."""

import json
import os

from y_web.src.federation import service
from y_web.tests.test_federation_service import world  # noqa: F401  (fixture)


def _config(fed):
    with open(os.path.join(fed.folder, "federation.json")) as fh:
        return json.load(fh)


def test_exposures_turn_the_quoted_visibility_check_on(world):  # noqa: F811
    app, exps, tmp = world
    fed = service.create_federation("w1", list(exps.values()), owner="admin", seed=1, exposures=True)
    assert _config(fed)["quoted"] == {"require_exposure": True}


def test_no_exposures_no_check(world):  # noqa: F811
    app, exps, tmp = world
    fed = service.create_federation("w2", list(exps.values()), owner="admin", seed=1, options={})
    assert "quoted" not in _config(fed)
