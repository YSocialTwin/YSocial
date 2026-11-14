"""Two repositories serving one address are dispatched, not collided (plan, phase F9.1)."""

import types

import pytest
from flask import Blueprint, Flask

from y_web.platforms import PlatformProvider, dispatch, registry
from y_web.platforms.base import HPC, STANDARD


def _provider(provider_id, runtime):
    attrs = {"key": "ddemo", "id": provider_id, "simulator_types": (runtime,)}
    return type("P_" + provider_id, (PlatformProvider,), attrs)()


@pytest.fixture
def world(monkeypatch):
    before, extra = dict(registry._PROVIDERS), dict(registry._EXTRA)
    registry.register(_provider("d_hpc", HPC))
    registry.register(_provider("d_std", STANDARD))
    experiments = {
        1: types.SimpleNamespace(platform_type="ddemo", simulator_type=HPC),
        2: types.SimpleNamespace(platform_type="ddemo", simulator_type=STANDARD),
        3: types.SimpleNamespace(platform_type="other", simulator_type=STANDARD),
    }
    monkeypatch.setattr(
        dispatch,
        "EXPERIMENT_RESOLVERS",
        [lambda args: experiments.get(args.get("exp_id"))],
    )
    yield
    registry._PROVIDERS.clear()
    registry._PROVIDERS.update(before)
    registry._EXTRA.clear()
    registry._EXTRA.update(extra)


def _attach(bp, owner, routes):
    """What a provider's ``attach_routes`` does: decorate the blueprint it is given."""
    with dispatch.attaching(owner):
        wrapped = dispatch.wrap(bp)
        for rule, name, methods in routes:
            wrapped.route(rule, methods=methods)(_view(f"{owner}:{name}", name))


def _view(answer, name):
    def view(**kwargs):
        return answer

    view.__name__ = name
    return view


def _app(bp):
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app.test_client(), app


def test_an_address_of_one_provider_is_registered_as_written(world):
    bp = Blueprint("solo", __name__)
    with dispatch.collecting():
        _attach(bp, "d_std", [("/<int:exp_id>/only_std", "only_std", ["GET"])])
    client, app = _app(bp)
    assert "solo.only_std" in app.view_functions  # endpoint name untouched
    assert client.get("/2/only_std").data == b"d_std:only_std"


def test_a_shared_address_runs_the_view_of_the_provider_of_the_experiment(world):
    bp = Blueprint("shared", __name__)
    with dispatch.collecting():
        _attach(bp, "d_hpc", [("/<int:exp_id>/publish", "publish", ["POST"])])
        _attach(bp, "d_std", [("/<int:exp_id>/publish", "publish", ["POST"])])
    client, app = _app(bp)
    rules = [r for r in app.url_map.iter_rules() if r.rule == "/<int:exp_id>/publish"]
    assert len(rules) == 1  # one rule, not two
    assert client.post("/1/publish").data == b"d_hpc:publish"
    assert client.post("/2/publish").data == b"d_std:publish"


def test_the_provider_that_does_not_serve_the_address_answers_404(world):
    bp = Blueprint("partial", __name__)
    with dispatch.collecting():
        _attach(bp, "d_hpc", [("/<int:exp_id>/extra", "extra", ["GET"])])
        _attach(bp, "d_std", [("/<int:exp_id>/shared", "shared", ["GET"])])
        _attach(bp, "d_hpc", [("/<int:exp_id>/shared", "shared", ["GET"])])
    client, _ = _app(bp)
    assert client.get("/1/extra").data == b"d_hpc:extra"
    assert (
        client.get("/2/extra").data == b"d_hpc:extra"
    )  # one owner: registered directly
    assert client.get("/2/shared").data == b"d_std:shared"


def test_a_dispatched_address_is_404_for_a_provider_without_it_and_for_unknown_experiments(
    world,
):
    bp = Blueprint("both", __name__)
    with dispatch.collecting():
        _attach(bp, "d_hpc", [("/<int:exp_id>/x", "x", ["GET"])])
        _attach(bp, "d_std", [("/<int:exp_id>/x", "x", ["GET"])])
    client, _ = _app(bp)
    assert client.get("/3/x").status_code == 404  # an experiment nobody here runs
    assert client.get("/99/x").status_code == 404  # no such experiment


def test_methods_are_part_of_the_address(world):
    bp = Blueprint("methods", __name__)
    with dispatch.collecting():
        _attach(bp, "d_hpc", [("/<int:exp_id>/m", "m_get", ["GET"])])
        _attach(bp, "d_std", [("/<int:exp_id>/m", "m_post", ["POST"])])
    client, _ = _app(bp)
    assert client.get("/1/m").data == b"d_hpc:m_get"
    assert client.post("/2/m").data == b"d_std:m_post"
    # an address of one provider is not dispatched: it answers whatever experiment it is asked for
    assert client.post("/1/m").data == b"d_std:m_post"


def test_two_addresses_with_one_endpoint_name_do_not_collide(world):
    bp = Blueprint("names", __name__)
    with dispatch.collecting():
        _attach(bp, "d_hpc", [("/<int:exp_id>/hpc_page", "page", ["GET"])])
        _attach(bp, "d_std", [("/<int:exp_id>/std_page", "page", ["GET"])])
    client, app = _app(bp)
    assert {"names.page", "names.d_std__page"} <= set(app.view_functions)
    assert client.get("/1/hpc_page").data == b"d_hpc:page"
    assert client.get("/2/std_page").data == b"d_std:page"


def test_outside_collecting_a_blueprint_is_used_as_it_is(world):
    bp = Blueprint("plain", __name__)
    with dispatch.attaching("d_std"):
        assert dispatch.wrap(bp) is bp
    assert dispatch.wrap(bp) is bp


def test_other_blueprint_attributes_reach_the_real_blueprint(world):
    bp = Blueprint("attrs", __name__)
    seen = []
    with dispatch.collecting():
        with dispatch.attaching("d_std"):
            wrapped = dispatch.wrap(bp)
            wrapped.before_request(lambda: seen.append(1))
            assert wrapped.name == "attrs"
            wrapped.route("/<int:exp_id>/ok")(_view("ok", "ok"))
    client, _ = _app(bp)
    assert client.get("/2/ok").data == b"ok"
    assert seen == [1]


def test_a_failing_rule_is_reported_and_the_others_still_register(world):
    bp = Blueprint("bad", __name__)
    with dispatch.collecting() as collector:
        _attach(bp, "d_std", [("/<int:exp_id>/good", "good", ["GET"])])
        collector.add(bp, "d_std", "/boom", "boom", None, {"methods": ["GET"]})
    client, _ = _app(bp)
    assert client.get("/2/good").data == b"d_std:good"
