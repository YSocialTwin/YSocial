from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_exclude_adhoc_populations_hides_custom_pop_types():
    from y_web.routes.admin.sub.clients._crud import _exclude_adhoc_populations

    pops = [
        SimpleNamespace(id=1, name="standard_a", pop_type=None),
        SimpleNamespace(id=2, name="standard_b", pop_type=""),
        SimpleNamespace(id=3, name="hello_world_pop", pop_type="hworld"),
        SimpleNamespace(id=4, name="moderator_pop", pop_type="moderator"),
    ]

    visible = _exclude_adhoc_populations(pops)
    visible_ids = [p.id for p in visible]

    assert visible_ids == [1, 2]
