"""A platform nobody in the core has heard of is recognised from what its repository declares (gate G8).

The repository below is written to a temporary external folder and only declares a platform: no catalog lists it,
no core file names it. The test checks every place where the core used to carry a list of platforms.
"""

import json
import sys
from types import SimpleNamespace

import pytest

KEY = "zplat"
REPO = "ZPlatform"

PROVIDER = """
from types import SimpleNamespace

from y_web.sdk import HPC, FrontendSetting, HumanRecsysTraits, N_, PlatformProvider

LEARNED = []


def _normalize(mode):
    return "ZRank" if str(mode or "").strip().lower() in ("zrank", "zr") else "Random"


RECSYS = HumanRecsysTraits(
    normalize=_normalize,
    is_supported=lambda mode: _normalize(mode) in ("ZRank", "Random"),
    describe=lambda mode: N_("Posts of Z, best first.") if mode == "ZRank" else None,
    suggested_posts=lambda uid, mode, page=1, per_page=10, *a, **k: (
        SimpleNamespace(items=[("ranked", uid, mode, page, per_page)]),
        None,
    ),
    suggested_users=lambda username, pages=False: [(username, pages)],
    on_interaction=lambda *args: LEARNED.append(args),
)


class ZPlat(PlatformProvider):
    reads_server_config = True

    def profile_picture(self, user):
        return "/z/" + user.name

    def discussion_community(self, article, topics):
        return {"slug": "z"}

    def page_context(self, exp, ui):
        return {"platform_ui": "z", "frontend_plugins": False}

    frontend_settings = (
        FrontendSetting("z_flag", True),
        FrontendSetting("z_rounds", 5, minimum=1, maximum=9),
        FrontendSetting("z_note", "", max_length=5, strip=True),
        FrontendSetting(
            "z_mode", "a", choices=({"name": "a", "label": N_("A")}, {"name": "b", "label": N_("B")})
        ),
    )
    recsys_catalog = (
        {"kind": "content", "name": "ZRank", "label": "Z rank", "category": "Z",
         "enabled": "Standard"},
        {"kind": "follow", "name": "ZFollow", "label": "Z follow", "category": "Z",
         "enabled": "Standard"},
    )

    @property
    def human_recsys(self):
        return RECSYS


    key = "zplat"
    label = N_("Z platform")
    icon = "star"
    order = 900
    simulator_types = (HPC,)
    runtime_keys = ("zplatform",)
    tag_runtime_sets = (("zplatform",),)
    server_label = "ZPlatform"
    hpc_launch = {"runtime_repo": "ZPlatform", "supports_gunicorn": False}
"""


@pytest.fixture
def new_platform(tmp_path, monkeypatch):
    from y_web.platforms import discovery, registry
    from y_web.src.external_runtime import registry as runtime_registry

    external = tmp_path / "external"
    repo = external / REPO
    (repo / "meta").mkdir(parents=True)
    (repo / "ysocial_platform").mkdir()
    (repo / "ysocial_platform" / "__init__.py").write_text("")
    (repo / "ysocial_platform" / "provider.py").write_text(PROVIDER)
    (repo / "meta" / "registry.json").write_text(
        json.dumps(
            {
                "platform": {
                    "key": KEY,
                    "label": "Z platform",
                    "api_version": "1.0",
                    "provider": "ysocial_platform.provider:ZPlat",
                }
            }
        )
    )

    saved = (
        dict(registry._PROVIDERS),
        {k: list(v) for k, v in registry._EXTRA.items()},
        dict(discovery._DISCOVERED),
    )
    monkeypatch.setattr(runtime_registry, "EXTERNAL_DIR", external)
    # only this folder is searched: the repositories of the checkout are not touched
    monkeypatch.setattr(
        runtime_registry, "supported_repos", lambda: dict(runtime_registry._LOCAL_SPECS)
    )
    registry._PROVIDERS.clear()
    registry._EXTRA.clear()
    problems = discovery.discover_platforms()
    try:
        yield SimpleNamespace(problems=problems, repo=repo)
    finally:
        runtime_registry.remove_local_specs()
        registry._PROVIDERS.clear()
        registry._PROVIDERS.update(saved[0])
        registry._EXTRA.clear()
        registry._EXTRA.update(saved[1])
        discovery._DISCOVERED.clear()
        discovery._DISCOVERED.update(saved[2])
        for name in [n for n in sys.modules if "zplat" in n.lower()]:
            sys.modules.pop(name, None)


def test_it_is_found_and_registered_without_any_catalog(new_platform):
    from y_web.platforms import registry
    from y_web.src.external_runtime import registry as runtime_registry

    assert new_platform.problems == {"zplatform": []}
    provider = registry.get(KEY)
    assert provider is not None and provider.label == "Z platform"
    assert KEY in registry.keys()
    spec = runtime_registry._LOCAL_SPECS["zplatform"]
    assert (spec.group, spec.category, spec.trust, spec.source) == (
        KEY,
        "simulation_runtimes",
        "community",
        "local",
    )


def test_the_plugin_list_shows_it_with_the_platforms(new_platform):
    from y_web.platforms.discovery import provider_of_repo
    from y_web.routes.admin.sub.experiments import _external_runtimes as er
    from y_web.src.external_runtime import registry as runtime_registry

    spec = runtime_registry._LOCAL_SPECS["zplatform"]
    assert provider_of_repo(spec).key == KEY
    entry = {
        "key": "zplatform",
        "paired": False,
        "members": [{"key": "zplatform", "category": spec.category}],
    }
    sections = er._plugin_sections([entry])
    assert [(s["key"], [e["key"] for e in s["entries"]]) for s in sections] == [
        ("platforms", ["zplatform"])
    ]


def test_its_plugin_group_is_never_dropped_from_the_status_page(new_platform):
    from y_web.src.external_runtime import registry as runtime_registry

    # the groups of the built-in platforms are listed first; one the list does not know follows them
    keys = [g for g, _label, _specs in runtime_registry.grouped_runtime_specs()]
    assert keys == [KEY]  # supported_repos is narrowed to the folder searched here


class _Column:
    """Stands in for a model column: any comparison or ``|`` gives another column."""

    def __eq__(self, _other):
        return self

    def __or__(self, _other):
        return self


def test_running_experiments_block_the_removal_of_its_runtime(
    new_platform, monkeypatch
):
    from y_web.routes.admin.sub.experiments import _external_runtimes as er
    from y_web.src.external_runtime import registry as runtime_registry

    monkeypatch.setattr(
        er, "supported_repos", lambda: dict(runtime_registry._LOCAL_SPECS)
    )
    rows = [
        SimpleNamespace(platform_type=KEY, simulator_type="HPC"),
        SimpleNamespace(platform_type="other", simulator_type="Standard"),
    ]

    class _Query:
        def filter(self, *_conditions):
            return self

        def all(self):
            return rows

    fake = SimpleNamespace(
        query=_Query(), is_remote=_Column(), running=_Column(), exp_status=_Column()
    )
    monkeypatch.setattr(er, "Exps", fake)
    assert er._runtime_group_active_experiments(KEY) == [rows[0]]
    assert er._runtime_group_active_experiments("no_such_group") == []


def test_its_hpc_launch_row_comes_from_the_provider(new_platform):
    from y_web.src.hpc.platforms import find_hpc_platform, get_hpc_platform

    spec = get_hpc_platform(KEY)
    assert (spec.key, spec.runtime_repo, spec.supports_gunicorn) == (
        KEY,
        "ZPlatform",
        False,
    )
    assert find_hpc_platform(KEY) is spec


def test_it_is_a_population_type_and_an_agents_tag_and_has_a_label(
    new_platform, monkeypatch
):
    import importlib

    agents = importlib.import_module("y_web.routes.admin.sub.agents")
    from y_web.src.agents.platform import (
        VALID_POPULATION_TYPES,
        normalize_population_username_type,
    )
    from y_web.src.experiment.platform_labels import (
        group_experiments_by_platform,
        platform_label,
    )

    assert KEY in VALID_POPULATION_TYPES
    assert normalize_population_username_type("ZPlat") == KEY
    assert agents._platforms()[KEY][1] == (("zplatform",),)
    monkeypatch.setattr(agents, "_runtime_installed", lambda key: key == "zplatform")
    assert agents._installed_platforms() == [KEY]
    assert str(platform_label(KEY)) == "Z platform"
    groups = group_experiments_by_platform(
        [SimpleNamespace(platform_type=KEY, exp_name="e")]
    )
    assert [g["type"] for g in groups] == [KEY]


def test_the_public_registry_can_list_a_platform_too():
    from y_web.src.external_runtime.catalog import parse_registry

    specs, problems = parse_registry(
        {
            "schema_version": 1,
            "plugins": [
                {
                    "id": "zplat_runtime",
                    "name": "ZPlatform",
                    "repo": "someone/ZPlatformRepo",
                    "category": "simulation_runtimes",
                    "platform": KEY,
                    "platform_label": "Z platform",
                }
            ],
        }
    )
    assert problems == []
    spec = specs["zplat_runtime"]
    assert (spec.group, spec.group_label, spec.category) == (
        KEY,
        "Z platform",
        "simulation_runtimes",
    )
    _, problems = parse_registry(
        {
            "schema_version": 1,
            "plugins": [
                {
                    "id": "nameless",
                    "name": "X",
                    "repo": "someone/X",
                    "category": "simulation_runtimes",
                }
            ],
        }
    )
    assert problems and "platform" in problems[0]


def _experiment():
    return SimpleNamespace(platform_type=KEY, simulator_type="HPC")


def test_its_recommenders_live_in_the_platform_and_the_core_only_asks(
    new_platform, monkeypatch
):
    """The ranking, the modes, their explanations and what a mode learns come from ``provider.human_recsys``."""
    from y_web.platforms import registry
    from y_web.routes.social import helpers

    recsys = registry.human_recsys(_experiment())
    assert recsys is not None and recsys.normalize("zr") == "ZRank"
    # a platform with no recommenders answers ``None``
    assert registry.human_recsys(SimpleNamespace(platform_type="nothing")) is None

    # no catalogue rows: the label falls back to the mode name
    monkeypatch.setattr(
        helpers,
        "db",
        SimpleNamespace(
            select=lambda model: model,
            session=SimpleNamespace(scalars=lambda q: SimpleNamespace(all=lambda: [])),
        ),
    )
    info = helpers._content_recsys_info("zr", {"show_recsys_info": True}, recsys)
    assert info["name"] == "ZRank" and info["description"] == "Posts of Z, best first."
    assert helpers._content_recsys_info("zr", {"show_recsys_info": True}) is None

    ranked, _more = recsys.suggested_posts(7, "zr", 2, 5)
    assert ranked.items == [("ranked", 7, "zr", 2, 5)]


def test_the_core_lets_the_platform_learn_from_an_interaction(
    new_platform, monkeypatch
):
    from y_web.platforms import registry
    from y_web.routes.interactions import common

    recsys = registry.human_recsys(_experiment())
    monkeypatch.setattr(registry, "human_recsys", lambda exp_id: recsys)
    person = SimpleNamespace(id=3, recsys_type="zr")
    common._maybe_update_fb_interests(11, person, 99, "like")
    learned = sys.modules[type(registry.get(KEY)).__module__].LEARNED
    assert learned == [(11, person, 99, "like")]


def test_its_recommenders_join_the_catalogue_without_touching_the_existing_rows(
    new_platform,
):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from y_web.platforms.recsys_catalog import ensure_catalog
    from y_web.src.models import Content_Recsys, Follow_Recsys

    engine = create_engine("sqlite://")
    Content_Recsys.__table__.create(engine)
    Follow_Recsys.__table__.create(engine)
    with Session(engine) as session:
        session.add(
            Content_Recsys(
                name="zrank", value="edited by hand", category="Mine", enabled="HPC"
            )
        )
        session.commit()
        assert ensure_catalog(session) == 1  # ZFollow only: ZRank is already there
        assert ensure_catalog(session) == 0  # idempotent
        row = session.scalars(select(Content_Recsys)).one()
        assert (row.value, row.enabled) == ("edited by hand", "HPC")
        follow = session.scalars(select(Follow_Recsys)).one()
        assert (follow.name, follow.enabled) == ("ZFollow", "Standard")


def test_its_frontend_settings_are_declared_and_validated_by_the_platform(new_platform):
    """The defaults, the accepted values and the page's fields come from ``provider.frontend_settings``."""
    from y_web.routes.admin.sub.experiments import _frontend_settings as fs
    from y_web.src.experiment.frontend_defaults import defaults_for

    defaults = defaults_for(KEY)
    assert defaults["z_flag"] is True and defaults["z_rounds"] == 5
    assert "z_flag" not in defaults_for("microblogging")
    assert "z_flag" not in defaults_for(None)

    specs = {s["key"]: s for s in fs._platform_setting_specs(KEY)}
    assert specs["z_rounds"]["type"] == "int" and specs["z_flag"]["type"] == "bool"
    assert [c["name"] for c in specs["z_mode"]["choices"]] == ["a", "b"]

    # a platform never hides its own controls from itself
    assert "z_flag" not in fs.excluded_capabilities_for(KEY)

    setting = {s.key: s for s in fs.declared_settings(KEY)}["z_rounds"]
    assert fs._clamped(50, setting) == 9 and fs._clamped(-3, setting) == 1


def test_the_shared_pages_ask_the_platform_instead_of_naming_it(
    new_platform, monkeypatch
):
    """Profile pictures, communities and the page context of the shared pages come from the provider's hooks."""
    from y_web.platforms import registry
    from y_web.routes.social import helpers

    exp = SimpleNamespace(idexp=5, platform_type=KEY, simulator_type="HPC")
    provider = registry.resolve(exp)
    assert provider.reads_server_config is True
    assert provider.profile_picture(SimpleNamespace(name="ann")) == "/z/ann"
    assert provider.discussion_community(None, []) == {"slug": "z"}
    # a platform that says nothing keeps the shared behaviour
    generic = registry.resolve(SimpleNamespace(platform_type="nothing"))
    assert (
        generic.profile_picture(None) is None
        and generic.render_profile(exp, {}) is None
    )
    assert generic.profile_redirect(exp, None, 1) is None
    assert generic.accepts_account_id_login is False

    monkeypatch.setattr(
        helpers, "request", SimpleNamespace(blueprint="main", view_args={"exp_id": 5})
    )
    monkeypatch.setattr(
        helpers,
        "db",
        SimpleNamespace(session=SimpleNamespace(get=lambda model, key: exp)),
    )
    monkeypatch.setattr(helpers, "_load_ui_settings", lambda exp_id: {"k": 1})
    context = helpers._platform_ui_context()
    assert context == {
        "frontend_adds_on_modules": [],
        "ui": {"k": 1},
        "platform_ui": "z",
    }


def test_a_platform_gets_its_own_shared_blueprint_without_the_core_naming_it(
    monkeypatch,
):
    """``routes.blueprint(name, url_prefix=...)`` creates the blueprint the repositories of a platform share."""
    from y_web.sdk import routes

    monkeypatch.setattr(routes, "_SHARED", {})
    first = routes.blueprint("zapi", url_prefix="/api/z")
    again = routes.blueprint("zapi", url_prefix="/api/z")
    assert first is not None and again is not None
    assert routes.shared_blueprint_names() == {"zapi"}
    assert [b.url_prefix for b in routes.shared_blueprints()] == ["/api/z"]
    with pytest.raises(ValueError):
        routes.blueprint("zapi", url_prefix="/api/other")
    with pytest.raises(KeyError):
        routes.blueprint("unknown")
