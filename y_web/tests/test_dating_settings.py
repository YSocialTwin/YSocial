"""Schema-generated settings, recommender choice, client creation and the run lock (plan S3)."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "external" / "YDating"
EXAMPLE = REPO / "example" / "population" / "population_10.json"

needs_runtime = pytest.mark.skipif(not REPO.exists(), reason="YDating is not present")


# -- coverage: every key of a schema is exposed or named as internal ---------------------------------
@needs_runtime
@pytest.mark.parametrize("kind", ["client", "server"])
def test_every_schema_key_is_exposed_or_listed_as_internal(kind):
    from y_web.src.dating import client_config, schema_forms, server_settings

    mod = client_config if kind == "client" else server_settings
    sch = mod.schema(str(REPO))
    exposed, internal, unknown = schema_forms.coverage(sch, mod.INTERNAL)
    assert unknown == [], "internal keys that are not in the schema"
    leaves = set(schema_forms.leaf_paths(sch))
    assert set(exposed) | set(internal) == leaves
    assert not set(exposed) & set(internal)
    assert all(mod.INTERNAL[p] for p in internal)  # every exclusion has its reason


@needs_runtime
def test_every_recommender_schema_is_covered():
    from y_web.src.dating import schema_forms, server_settings

    models = server_settings.recsys_models(str(REPO))
    assert len(models) == 10 and "common" not in models
    for model in models:
        sch = server_settings.recsys_schema(str(REPO), model)
        exposed, internal, _unknown = schema_forms.coverage(sch)
        assert internal == [] and set(exposed) == set(schema_forms.leaf_paths(sch))
    common = schema_forms.load_schema(str(REPO), "recsys/common.json")
    assert set(f.path for f in schema_forms.fields(common)) == set(
        schema_forms.leaf_paths(common)
    )


# -- parsing -----------------------------------------------------------------------------------------
def _form(**kw):
    return kw


@needs_runtime
def test_form_values_are_typed_and_bounded():
    from y_web.src.dating import client_config as cc
    from y_web.src.dating import schema_forms as sf

    fields = {f.path: f for f in cc.form_fields(str(REPO))}
    out = sf.parse_form(
        {
            fields["swipe.w_attr"].name: "0.5",
            fields["activity.swipes_per_session"].name: "7",
            fields["swipe.mode"].name: "mixed",
            fields["conversation.enabled"].name + "__present": "1",
        },
        list(fields.values()),
    )
    assert out["swipe"]["w_attr"] == 0.5 and out["swipe"]["mode"] == "mixed"
    assert out["activity"]["swipes_per_session"] == 7
    assert out["conversation"]["enabled"] is False  # present but unchecked
    for name, value in (
        (fields["swipe.w_attr"].name, "abc"),
        (fields["activity.swipes_per_session"].name, "1.5"),
        (fields["swipe.mode"].name, "nope"),
        (fields["swipe.noise_std"].name, "-1"),
    ):
        with pytest.raises(sf.SettingsError):
            sf.parse_form({name: value}, list(fields.values()))


@needs_runtime
def test_client_config_satisfies_the_runtime_schema_and_carries_the_internal_keys():
    import jsonschema

    from y_web.src.dating import client_config as cc
    from y_web.src.dating import schema_forms as sf

    server = {"seed": 77, "simulation": {"num_slots_per_day": 12}}
    fields = {f.path: f for f in cc.form_fields(str(REPO))}
    cfg = cc.build_client_config(
        str(REPO),
        name="c1",
        population_file="Pop.json",
        days=3,
        server_config=server,
        memory_enabled=True,
        language="it",
        form={fields["llm.backend"].name: "stub", fields["swipe.mode"].name: "llm"},
    )
    jsonschema.Draft7Validator(cc.schema(str(REPO))).validate(cfg)
    assert cfg["client_name"] == "c1" and cfg["num_days"] == 3
    assert (
        cfg["num_slots_per_day"] == 12 and cfg["seed"] == 77 and cfg["language"] == "it"
    )
    assert cfg["population_file"] == "Pop.json" and cfg["memory"]["enabled"] is True
    assert cfg["swipe"]["mode"] == "llm"
    assert (
        sf.get_path(cfg, "swipe.w_attr") == 0.35
    )  # an untouched setting keeps the schema default
    with pytest.raises(cc.DatingClientFormError):
        cc.build_client_config(
            str(REPO),
            name="c",
            population_file="p",
            days=1,
            server_config=server,
            memory_enabled=False,
            language="en",
            form={fields["swipe.w_attr"].name: "x"},
        )
    for bad in ("0", "-2", "abc", "99999"):
        with pytest.raises(cc.DatingClientFormError):
            cc.parse_days(bad)
    assert cc.parse_days("-1") == -1


# -- recommender and server settings ---------------------------------------------------------------------
@needs_runtime
def test_each_of_the_ten_recommenders_can_be_chosen_and_passes_its_schema():
    from y_web.src.dating import schema_forms as sf
    from y_web.src.dating import server_settings as ss

    for model in ss.recsys_models(str(REPO)):
        cfg = {}
        ss.apply_recsys(str(REPO), cfg, {"matching_default_model": model})
        assert cfg["matching"]["default_model"] == model
        assert (
            sf.schema_problems(
                ss.recsys_schema(str(REPO), model), cfg["matching"]["models"][model]
            )
            == []
        )


@needs_runtime
def test_recommender_parameters_are_validated_and_unknown_models_refused():
    from y_web.src.dating import schema_forms as sf
    from y_web.src.dating import server_settings as ss

    stack = next(
        f for f in ss.common_fields(str(REPO)) if f.path.endswith("stack_size")
    )
    cfg = {}
    ss.apply_recsys(
        str(REPO), cfg, {"matching_default_model": "random", stack.name: "30"}
    )
    assert cfg["matching"]["common"]["stack_size"] == 30
    with pytest.raises(ss.ServerSettingsError):
        ss.apply_recsys(str(REPO), {}, {"matching_default_model": "tinder"})
    with pytest.raises(ss.ServerSettingsError):
        ss.apply_recsys(
            str(REPO), {}, {"matching_default_model": "random", stack.name: "0"}
        )
    hyb = next(f for m in ["hybrid"] for f in ss.recsys_fields(str(REPO), m))
    with pytest.raises(ss.ServerSettingsError):
        ss.apply_recsys(
            str(REPO),
            {},
            {"matching_default_model": "hybrid", hyb.name: '[{"weight": 1}]'},
        )
    ok = {
        "matching_default_model": "hybrid",
        hyb.name: json.dumps([{"name": "random", "weight": 2}]),
    }
    cfg = {}
    ss.apply_recsys(str(REPO), cfg, ok)
    assert cfg["matching"]["models"]["hybrid"]["components"][0]["name"] == "random"


@needs_runtime
def test_apply_form_keeps_the_config_valid_for_the_strict_schema():
    from y_web.src.dating import schema_forms as sf
    from y_web.src.dating import server_settings as ss
    from y_web.src.dating.experiment_config import generate_dating_server_config

    cfg = generate_dating_server_config("e", "/x/d.db", "/x/", seed=3)
    fields = {f.path: f for f in ss.form_fields(str(REPO))}
    ss.apply_form(
        str(REPO),
        cfg,
        {
            fields["matching.likes_per_day"].name: "50",
            fields["simulation.num_slots_per_day"].name: "12",
            "matching_default_model": "reciprocal",
        },
    )
    assert (
        cfg["matching"]["likes_per_day"] == 50
        and cfg["simulation"]["num_slots_per_day"] == 12
    )
    assert cfg["matching"]["default_model"] == "reciprocal"
    assert sf.schema_problems(ss.schema(str(REPO)), cfg) == []
    assert (
        cfg["platform_type"] == "dating" and cfg["seed"] == 3
    )  # host keys and seed survive


# -- the run lock --------------------------------------------------------------------------------------------
def test_the_run_lock_refuses_changes_that_shape_the_run(tmp_path):
    from y_web.src.dating import server_settings as ss

    cfg = {
        "seed": 1,
        "matching": {"likes_per_day": 100},
        "logging": {"enable_server_log": True},
    }
    assert ss.check_change_allowed(str(tmp_path), cfg) == (True, "")
    assert not ss.run_started(str(tmp_path))
    ss.write_lock(str(tmp_path), cfg)
    assert ss.run_started(str(tmp_path))
    first = ss.read_lock(str(tmp_path))
    assert ss.write_lock(str(tmp_path), {"seed": 99}) == first  # never overwritten
    assert ss.check_change_allowed(str(tmp_path), cfg)[0] is True
    logs = json.loads(json.dumps(cfg))
    logs["logging"]["enable_server_log"] = False
    assert ss.check_change_allowed(str(tmp_path), logs)[0] is True  # logging may change
    changed = json.loads(json.dumps(cfg))
    changed["matching"]["likes_per_day"] = 5
    allowed, why = ss.check_change_allowed(str(tmp_path), changed)
    assert not allowed and "locked" in why
    ss.clear_lock(str(tmp_path))
    assert ss.check_change_allowed(str(tmp_path), changed)[0] is True


def test_a_database_without_a_lock_also_locks(tmp_path):
    from y_web.src.dating import server_settings as ss

    (tmp_path / "database_server.db").write_text("")
    assert ss.run_started(str(tmp_path))
    assert ss.check_change_allowed(str(tmp_path), {"seed": 1})[0] is False


# -- routes -------------------------------------------------------------------------------------------------
@pytest.fixture
def dating_exp(app, tmp_path, monkeypatch):
    from y_web import db
    from y_web.routes.admin.sub.clients import _dating as client_routes
    from y_web.routes.admin.sub.experiments import _dating as exp_routes
    from y_web.src.dating.experiment_config import generate_dating_server_config
    from y_web.src.models import Exps

    for mod in (exp_routes, client_routes):
        monkeypatch.setattr(mod, "check_privileges", lambda *_: None)
        monkeypatch.setattr(
            mod, "current_user", SimpleNamespace(username="admin", id=1)
        )
        monkeypatch.setattr(
            mod,
            "url_for",
            lambda endpoint, **kw: "/"
            + endpoint
            + "/"
            + "/".join(str(v) for v in kw.values()),
        )
        monkeypatch.setattr(mod, "get_writable_path", lambda *a: str(tmp_path))
    flashes = []
    for mod in (exp_routes, client_routes):
        monkeypatch.setattr(
            mod, "flash", lambda m, c="message": flashes.append((c, str(m)))
        )
    monkeypatch.setattr(exp_routes, "user_can_manage_experiment", lambda *a: True)
    monkeypatch.setattr(exp_routes, "_current_admin_user_or_none", lambda: None)
    monkeypatch.setattr(exp_routes, "_get_database_type", lambda: "sqlite")
    monkeypatch.setattr(
        exp_routes,
        "_get_experiment_folder",
        lambda base, exp, t: str(Path(base) / "y_web" / "experiments" / "u1"),
    )
    monkeypatch.setattr(client_routes, "_get_experiment_folder_name", lambda exp: "u1")
    folder = tmp_path / "y_web" / "experiments" / "u1"
    folder.mkdir(parents=True)
    cfg = generate_dating_server_config(
        "e", str(folder / "database_server.db"), str(folder), seed=5
    )
    (folder / "server_config.json").write_text(json.dumps(cfg))
    with app.app_context():
        exp = Exps(
            exp_name="d",
            platform_type="dating",
            db_name="experiments/u1/database_server.db",
            owner="admin",
            exp_descr="",
            status=0,
            port=5001,
            server="127.0.0.1",
            annotations="",
            llm_agents_enabled=1,
            simulator_type="HPC",
            is_remote=0,
            prompt_language="en",
        )
        db.session.add(exp)
        db.session.commit()
        yield SimpleNamespace(
            exp=exp,
            folder=folder,
            flashes=flashes,
            exp_routes=exp_routes,
            client_routes=client_routes,
        )


@needs_runtime
def test_update_settings_route_saves_then_refuses_after_the_run_started(
    app, dating_exp
):
    from y_web.src.dating import server_settings as ss

    path = dating_exp.folder / "server_config.json"
    with app.test_request_context(
        f"/admin/update_dating_settings/{dating_exp.exp.idexp}",
        method="POST",
        data={"matching_default_model": "random", "adv__matching__likes_per_day": "40"},
    ):
        dating_exp.exp_routes.update_dating_settings.__wrapped__(dating_exp.exp.idexp)
    saved = json.loads(path.read_text())
    assert (
        saved["matching"]["default_model"] == "random"
        and saved["matching"]["likes_per_day"] == 40
    )
    ss.write_lock(str(dating_exp.folder), saved)
    with app.test_request_context(
        f"/admin/update_dating_settings/{dating_exp.exp.idexp}",
        method="POST",
        data={"matching_default_model": "hybrid", "adv__matching__likes_per_day": "41"},
    ):
        dating_exp.exp_routes.update_dating_settings.__wrapped__(dating_exp.exp.idexp)
    assert json.loads(path.read_text()) == saved
    assert any("locked" in m for _c, m in dating_exp.flashes)
    with app.test_request_context(
        f"/admin/update_dating_settings/{dating_exp.exp.idexp}",
        method="POST",
        data={"matching_default_model": "tinder"},
    ):
        dating_exp.exp_routes.update_dating_settings.__wrapped__(dating_exp.exp.idexp)
    assert json.loads(path.read_text()) == saved


@needs_runtime
def test_create_client_writes_config_population_and_rows(app, dating_exp, tmp_path):
    from y_web import db
    from y_web.src.dating import population as dp
    from y_web.src.models import Client, Client_Execution, Population

    with app.app_context():
        pop = Population(name="Pisa", descr="", size=10, username_type="dating")
        db.session.add(pop)
        db.session.commit()
        dp.store(str(tmp_path), pop.id, json.loads(EXAMPLE.read_text()))
        with app.test_request_context(
            "/admin/create_dating_client",
            method="POST",
            data={
                "id_exp": dating_exp.exp.idexp,
                "name": "c1",
                "population_id": pop.id,
                "num_days": "2",
                "adv__swipe__mode__": "x",
            },
        ):
            dating_exp.client_routes.create_dating_client()
        client = db.session.query(Client).one()
        assert client.days == 2 and client.population_id == pop.id
        assert db.session.query(Client_Execution).one().expected_duration_rounds == 48
        cfg = json.loads((dating_exp.folder / "client_c1-Pisa.json").read_text())
        assert cfg["population_file"] == "Pisa.json" and cfg["seed"] == 5
        assert (
            json.loads((dating_exp.folder / "Pisa.json").read_text())["agents"][0][
                "username"
            ]
            == "user_01"
        )
        # the same name on the same population is refused
        with app.test_request_context(
            "/admin/create_dating_client",
            method="POST",
            data={
                "id_exp": dating_exp.exp.idexp,
                "name": "c1",
                "population_id": pop.id,
                "num_days": "1",
            },
        ):
            dating_exp.client_routes.create_dating_client()
        assert db.session.query(Client).count() == 1
        # a population for another platform is refused
        other = Population(
            name="Micro", descr="", size=1, username_type="microblogging"
        )
        db.session.add(other)
        db.session.commit()
        with app.test_request_context(
            "/admin/create_dating_client",
            method="POST",
            data={
                "id_exp": dating_exp.exp.idexp,
                "name": "c2",
                "population_id": other.id,
                "num_days": "1",
            },
        ):
            dating_exp.client_routes.create_dating_client()
        assert db.session.query(Client).count() == 1
        assert any("incompatible" in m for _c, m in dating_exp.flashes)


def test_the_new_templates_compile(app):
    templates = ROOT / "y_web" / "templates" / "admin"
    for name in ("clients_dating.html", "dating_settings.html", "_dating_fields.html"):
        assert (
            app.jinja_env.parse((templates / name).read_text(encoding="utf-8"))
            is not None
        )
