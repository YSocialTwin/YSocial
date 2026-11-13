"""The registry of the simulation platforms (plan, phase F1)."""

import pytest

from y_web.platforms import PlatformProvider, registry
from y_web.tests import _platform_alias
from y_web.tests._platform_repos import requires_platform

#: Dating is provided by its repository: what is said about it is checked where the repository is installed
needs_photo = pytest.mark.skipif(
    not _platform_alias.installed(_platform_alias.PHOTO_SHARING),
    reason="YPhotoSharing is not installed",
)
needs_im = pytest.mark.skipif(
    not _platform_alias.installed(_platform_alias.INSTANT_MESSAGING),
    reason="YInstantMessaging is not installed",
)
#: the tests that compare the tables of every platform need both repositories (a test of one platform alone uses its mark)
needs_dating = pytest.mark.skipif(
    not (
        _platform_alias.installed(_platform_alias.DATING)
        and _platform_alias.installed(_platform_alias.INSTANT_MESSAGING)
        and _platform_alias.installed(_platform_alias.PHOTO_SHARING)
    ),
    reason="YDating, YInstantMessaging and YPhotoSharing are not all installed",
)
_needs_dating_only = pytest.mark.skipif(
    not _platform_alias.installed(_platform_alias.DATING),
    reason="YDating is not installed",
)


@needs_dating
def test_the_built_in_platforms_are_registered_in_menu_order():
    assert registry.keys() == [
        "microblogging",
        "forum",
        "photo_sharing",
        "instant_messaging",
        "dating",
    ]


def test_an_unknown_or_empty_platform_has_no_provider():
    assert registry.get("video_chat") is None
    assert registry.get(None) is None
    assert registry.get("") is None


def test_a_platform_key_cannot_be_registered_twice(monkeypatch):
    monkeypatch.setattr(registry, "_PROVIDERS", dict(registry._PROVIDERS))

    class Another(PlatformProvider):
        key = "forum"

    with pytest.raises(ValueError, match="already provided"):
        registry.register(Another())


def test_a_provider_needs_a_key():
    with pytest.raises(ValueError, match="no platform key"):
        registry.register(PlatformProvider())


@pytest.mark.parametrize(
    "key, expected",
    [
        ("microblogging", "/3/feed/7/feed/rf/1"),
        ("forum", "/3/rfeed/7/feed/rf/1"),
        pytest.param("photo_sharing", "/3/photo/feed/all/feed/rf/1", marks=needs_photo),
        pytest.param("instant_messaging", None, marks=needs_im),
        pytest.param("dating", None, marks=_needs_dating_only),
    ],
)
def test_entry_url_of_each_built_in_platform(key, expected):
    assert registry.get(key).entry_url(3, 7) == expected


def test_landing_redirect_follows_the_platform_of_the_experiment(app):
    from types import SimpleNamespace as NS

    from y_web.routes.social.common import _landing_redirect

    with app.test_request_context():
        forum = _landing_redirect(NS(platform_type="forum", idexp=3), 7)
        assert forum.status_code == 302
        assert forum.location == "/3/rfeed/7/feed/rf/1"
        for without_landing in ("instant_messaging", "dating", "video_chat", None):
            assert (
                _landing_redirect(NS(platform_type=without_landing, idexp=3), 7) is None
            )


# --- admin client pages: the answers of the providers equal the chains of tests they replaced -----------------------


def _legacy_clients_page(platform, simulator):
    """The dispatcher of client creation before the providers (routes/admin/sub/clients/_crud.py)."""
    if simulator == "HPC":
        if platform == "instant_messaging":
            return "clientsr.clients_im"
        if platform == "dating":
            return "clientsr.clients_dating"
        if platform == "photo_sharing":
            return "clientsr.clients_photo"
        if platform == "forum":
            return "clientsr.clients_forum_hpc"
        return "clientsr.clients_hpc"
    if platform == "forum":
        return "clientsr.clients_forum"
    return "clientsr.clients_standard"


def _legacy_client_mode(platform, simulator):
    if simulator == "HPC":
        return "hpc"
    return "forum" if platform == "forum" else "standard"


def _legacy_client_details_page(platform, simulator):
    if platform == "dating":
        return "clientsr.client_details_dating"
    if simulator == "HPC":
        return "clientsr.client_details_hpc"
    if platform == "forum":
        return "clientsr.client_details_forum"
    return "clientsr.client_details"


def _legacy_opinion_mode(platform, simulator):
    if platform == "instant_messaging":
        return "im"
    return _legacy_client_mode(platform, simulator)


#: the platform/simulator pairs an experiment can have (photo sharing, instant messaging and dating run on HPC only)
REACHABLE = (
    [
        (platform, simulator)
        for platform in ("microblogging", "forum", "video_chat", None)
        for simulator in ("Standard", "HPC")
    ]
    + [pytest.param("photo_sharing", "HPC", marks=needs_photo)]
    + [pytest.param("instant_messaging", "HPC", marks=needs_im)]
    + [pytest.param("dating", "HPC", marks=_needs_dating_only)]
)


@pytest.mark.parametrize("platform, simulator", REACHABLE)
def test_client_pages_and_modes_equal_the_previous_logic(platform, simulator):
    provider = registry.resolve(platform)
    assert provider.clients_page(simulator) == _legacy_clients_page(platform, simulator)
    assert provider.client_mode(simulator) == _legacy_client_mode(platform, simulator)
    assert provider.client_details_page(simulator) == _legacy_client_details_page(
        platform, simulator
    )
    assert provider.opinion_mode(simulator) == _legacy_opinion_mode(platform, simulator)


@pytest.mark.parametrize(
    "platform, generic",
    [
        ("microblogging", True),
        pytest.param("photo_sharing", True, marks=needs_photo),
        ("forum", False),
        pytest.param("instant_messaging", False, marks=needs_im),
        pytest.param("dating", False, marks=_needs_dating_only),
    ],
)
def test_which_platforms_create_their_hpc_clients_with_the_generic_route(
    platform, generic
):
    assert registry.resolve(platform).generic_hpc_client_creation is generic


@needs_dating
def test_client_files_and_execution_hooks_match_the_previous_platform_logic(tmp_path):
    from types import SimpleNamespace

    from y_web.platforms import registry

    packs = {
        "microblogging": ("prompts.json", "prompts.json"),
        "forum": ("prompts_forum.json", "prompts.json"),
        "photo_sharing": ("prompts_ygram.json", "prompts_ygram.json"),
        "instant_messaging": None,
        "dating": None,
    }
    for key, pack in packs.items():
        assert registry.get(key).prompt_pack == pack
    assert registry.get("photo_sharing").extra_prompt_files == ("prompts_ygram.json",)
    assert [
        k for k in packs if not registry.get(k).client_file_has_simulation_days
    ] == ["forum"]
    assert registry.resolve("unknown").client_file_has_simulation_days

    (tmp_path / "client_a-p.state.json").write_text("{}")
    (tmp_path / "client_a-q.state.json").write_text("{}")
    client = SimpleNamespace(name="a")
    names = {
        p.name
        for p in registry.get("photo_sharing").client_state_files(tmp_path, client)
    }
    assert names == {"client_a-p.state.json", "client_a-q.state.json"}
    for key in ("microblogging", "forum", "instant_messaging", "dating"):
        assert registry.get(key).client_state_files(tmp_path, client) == []
        if key != "dating":
            assert registry.get(key).rounds_per_day(None) is None


def _legacy_prompts_page(platform, simulator):
    if platform in ("instant_messaging",):
        return "experiments.prompts_im"
    if platform == "dating":
        return "experiments.prompts_dating"
    if simulator == "HPC":
        return "experiments.prompts_hpc"
    if platform == "forum":
        return "experiments.prompts_forum"
    return "experiments.prompts"


def _legacy_prompt_pack(platform, simulator):
    if platform == "photo_sharing":
        return "prompts_ygram.json", "prompts_ygram.json"
    if platform == "forum":
        return "prompts_forum.json", "prompts.json"
    if simulator == "HPC":
        return "prompts_hpc.json", "prompts.json"
    return "prompts.json", "prompts.json"


def test_experiment_prompt_hooks_match_the_previous_platform_logic():
    from y_web.platforms import registry

    for platform in registry.keys() + ["unknown"]:
        provider = registry.resolve(platform)
        for simulator in ("Standard", "HPC"):
            assert provider.prompts_page(simulator) == _legacy_prompts_page(
                platform, simulator
            ), (platform, simulator)
            assert provider.experiment_prompt_pack(simulator) == _legacy_prompt_pack(
                platform, simulator
            ), (platform, simulator)
        modules = ["news", "voting", "image"] + (
            ["image_post"] if platform == "forum" else []
        )
        assert list(provider.server_modules) == modules


def test_standard_runtime_hooks_match_the_previous_platform_logic(tmp_path):
    from y_web.platforms import registry
    from y_web.src.simulation import process_runner, server

    runtimes = {key: registry.get(key).standard_runtime for key in registry.keys()}
    assert {k for k, v in runtimes.items() if v} == {"microblogging", "forum"}
    for key, repos in {
        "microblogging": ("YServer", "YClient"),
        "forum": ("YServerReddit", "YClientReddit"),
    }.items():
        runtime = runtimes[key]
        assert (runtime.server_repo, runtime.client_repo) == repos
        server_dir, script = server._resolve_server_runtime_paths(str(tmp_path), key)
        assert server_dir.endswith(repos[0]) and script.endswith("y_server_run.py")
        assert process_runner._resolve_client_package_dir(str(tmp_path), key).endswith(
            repos[1]
        )
    for other in ("photo_sharing", "instant_messaging", "dating", "unknown"):
        for call in (
            lambda: server._resolve_server_runtime_paths(str(tmp_path), other),
            lambda: process_runner._resolve_client_package_dir(str(tmp_path), other),
        ):
            with pytest.raises(NotImplementedError):
                call()
    assert [k for k in runtimes if process_runner._has_activity_profiles(k)] == [
        "microblogging"
    ]
    assert runtimes["forum"].client_takes_log_file
    assert not runtimes["microblogging"].client_takes_log_file
    assert runtimes["forum"].fake_agent_module == "y_client.classes.fake_base_agent"
    synced = {
        k
        for k in registry.keys() + ["hpc", "unknown"]
        if registry.syncs_stress_reward(k)
    }
    assert synced == {"microblogging", "forum", "hpc"}


@needs_dating
def test_hpc_client_start_hooks_match_the_previous_platform_logic(tmp_path):
    from types import SimpleNamespace as NS

    from y_web.platforms import registry

    client, population = NS(name="c"), NS(name="p")
    folder = str(tmp_path)
    config = f"{folder}/client_c-p.json"
    agents = f"{folder}/p.json"
    prompts = {
        "photo_sharing": "prompts_ygram.json",
        "instant_messaging": "prompts_im.json",
    }
    for key in registry.keys() + ["unknown"]:
        assert registry.resolve(key).hpc_client_files(folder, client, population) == (
            config,
            agents,
            f"{folder}/{prompts.get(key, 'prompts.json')}",
        )
    overriding = {
        "prepare_hpc_client_files": {"photo_sharing"},
        "prepare_hpc_client_start": {"forum"},
        "sync_hpc_run_length": {"forum", "dating"},
        "start_hpc_gateway": {"instant_messaging", "dating"},
    }
    from y_web.platforms.base import PlatformProvider

    for hook, owners in overriding.items():
        found = {
            k
            for k in registry.keys()
            if getattr(type(registry.get(k)), hook)
            is not getattr(PlatformProvider, hook)
        }
        assert found == owners, hook


@needs_dating
def test_hpc_server_hooks_are_overridden_by_the_expected_platforms():
    from y_web.platforms import registry
    from y_web.platforms.base import PlatformProvider

    expected = {
        "validate_hpc_folder": {"forum", "instant_messaging", "dating"},
        "prepare_hpc_server": {"dating"},
        "after_hpc_server_started": {"instant_messaging"},
        "stop_hpc_gateway": {"instant_messaging", "dating"},
    }
    for hook, owners in expected.items():
        found = {
            k
            for k in registry.keys()
            if getattr(type(registry.get(k)), hook)
            is not getattr(PlatformProvider, hook)
        }
        assert found == owners, hook
    # the platforms that validate their folder are exactly those the HPC table marks as validating
    from y_web.src.hpc.platforms import HPC_PLATFORMS

    assert {k for k, v in HPC_PLATFORMS.items() if v.validates_config} == expected[
        "validate_hpc_folder"
    ]


def _legacy_resolve_simulator(platform_type, simulator_type, av):
    """The platform chain create_experiment used before the provider answered for it."""
    err = {
        "forum_hpc": "Forum HPC experiments are unavailable because YForum is not present.",
        "forum": "Forum experiments are unavailable because YServerReddit and YClientReddit are not both present.",
        "photo_sharing": "Photo Sharing experiments are unavailable because YPhotoSharing is not present.",
        "instant_messaging": "Instant messaging experiments are unavailable because YInstantMessaging is not present.",
        "dating": "Dating experiments are unavailable because YDating is not present.",
        "mb_hpc": "HPC microblogging experiments are unavailable because YMicroblogging is not present.",
        "mb": "Microblogging experiments are unavailable because neither YServer/YClient nor YMicroblogging is present.",
    }
    if platform_type == "forum" and simulator_type == "HPC":
        if not av["forum_hpc"]:
            return simulator_type, err["forum_hpc"]
    elif platform_type == "forum" and not av["forum"]:
        return simulator_type, err["forum"]
    for key in ("photo_sharing", "instant_messaging", "dating"):
        if platform_type == key and not av[key]:
            return simulator_type, err[key]
    if platform_type == "microblogging":
        if simulator_type == "HPC":
            if not av["hpc"]:
                if av["microblogging"]:
                    simulator_type = "Standard"
                else:
                    return simulator_type, err["mb_hpc"]
        else:
            if not av["microblogging"]:
                if av["hpc"]:
                    simulator_type = "HPC"
                else:
                    return simulator_type, err["mb"]
    elif platform_type in {"photo_sharing", "instant_messaging", "dating"}:
        simulator_type = "HPC"
    if platform_type == "forum":
        simulator_type = "HPC" if simulator_type == "HPC" else "Standard"
    elif simulator_type != "HPC":
        simulator_type = "Standard"
    return simulator_type, None


def test_resolve_simulator_matches_the_previous_creation_logic():
    import itertools

    from y_web.platforms import registry

    names = (
        "microblogging",
        "hpc",
        "forum",
        "forum_hpc",
        "photo_sharing",
        "instant_messaging",
        "dating",
    )
    for flags in itertools.product((False, True), repeat=len(names)):
        available = dict(zip(names, flags))
        for platform in registry.keys() + ["unknown"]:
            for simulator in ("Standard", "HPC", "other"):
                got, error = registry.resolve(platform).resolve_simulator(
                    simulator, available
                )
                want, want_error = _legacy_resolve_simulator(
                    platform, simulator, available
                )
                assert bool(error) == bool(want_error), (platform, simulator, flags)
                if error:
                    assert error == want_error
                else:
                    assert got == want, (platform, simulator, flags)


@needs_dating
def test_creation_rules_match_the_previous_creation_logic():
    from y_web.platforms import registry

    forced = {
        ("microblogging", "Standard"): {},
        ("microblogging", "HPC"): {},
        ("forum", "Standard"): {
            "opinion_dynamics_enabled": False,
            "sentiment_annotation": False,
            "emotion_annotation": False,
        },
        ("forum", "HPC"): {"redis_enabled": False},
        ("photo_sharing", "HPC"): {},
        ("instant_messaging", "HPC"): {
            "opinion_dynamics_enabled": False,
            "toxicity_annotation": False,
            "perspective_api": None,
            "sentiment_annotation": False,
            "emotion_annotation": False,
            "redis_enabled": False,
        },
        ("dating", "HPC"): {
            "opinion_dynamics_enabled": False,
            "perspective_api": None,
            "redis_enabled": False,
        },
    }
    own_database = {("forum", "HPC"), ("instant_messaging", "HPC"), ("dating", "HPC")}
    for (platform, simulator), want in forced.items():
        rules = registry.get(platform).creation_rules(simulator)
        assert dict(rules.forced) == want, (platform, simulator)
        assert (rules.database == "own") == ((platform, simulator) in own_database)
        assert (rules.database == "server") != ((platform, simulator) in own_database)
        # remote experiments are refused exactly where the runtime is not remote-capable
        assert bool(rules.remote_error) == ((platform, simulator) in own_database)
        assert bool(rules.sqlite_only_note) == ((platform, simulator) in own_database)
    unknown = registry.resolve("unknown").creation_rules("Standard")
    assert (dict(unknown.forced), unknown.remote_error, unknown.database) == (
        {},
        None,
        "none",
    )


def _server_config_request(**overrides):
    from y_web.platforms.base import ServerConfigRequest

    values = dict(
        exp_name="e",
        db_type="sqlite",
        db_uri="/tmp/x.db",
        data_path="/tmp/x/",
        db_config_dict=None,
        is_remote=0,
        seed=None,
        topics=["a"],
        toxicity_annotation=False,
        sentiment_annotation=True,
        emotion_annotation=False,
        opinion_dynamics_enabled=False,
        perspective_api="",
        redis_enabled=False,
        redis_host="h",
        redis_port=1,
        redis_password=None,
        redis_sliding_window_days=2,
    )
    values.update(overrides)
    return ServerConfigRequest(**values)


def test_generic_hpc_server_config_passes_the_request_to_the_generator(monkeypatch):
    from y_web.platforms import registry
    from y_web.routes.admin.sub.experiments import _crud

    seen = {}
    monkeypatch.setattr(
        _crud, "generate_hpc_config", lambda **kw: seen.update(kw) or {"ok": 1}
    )
    config = registry.get("microblogging").hpc_server_config(
        _server_config_request(perspective_api="")
    )
    assert config == {"ok": 1}
    assert seen["platform_type"] == "microblogging"
    assert seen["perspective_api"] is None  # an empty key means none
    assert seen["topics"] == ["a"] and seen["redis_host"] == "h"


@pytest.mark.parametrize(
    "key, module, error, generator, message",
    [
        pytest.param(
            "dating",
            "y_web.src.dating.experiment_config",
            "DatingConfigError",
            "generate_dating_server_config",
            "Invalid dating settings: boom",
            marks=_needs_dating_only,
        ),
        (
            "forum",
            "y_web.src.forum.experiment_config",
            "ForumConfigError",
            "generate_forum_server_config",
            "Invalid forum settings: boom",
        ),
        pytest.param(
            "instant_messaging",
            "y_web.routes.admin.sub.experiments._im",
            "ImConfigError",
            "generate_im_server_config",
            "Invalid instant messaging settings: boom",
            marks=needs_im,
        ),
    ],
)
def test_platform_config_errors_become_one_refusal(
    app, monkeypatch, key, module, error, generator, message
):
    import importlib

    from y_web.platforms import registry
    from y_web.platforms.base import PlatformConfigError

    mod = importlib.import_module(module)

    def refuse(**kwargs):
        raise getattr(mod, error)("boom")

    monkeypatch.setattr(mod, generator, refuse)
    with app.test_request_context():
        with pytest.raises(PlatformConfigError, match=message):
            registry.get(key).hpc_server_config(_server_config_request())


@needs_dating
def test_experiment_lifecycle_hooks_match_the_previous_platform_logic():
    from types import SimpleNamespace as NS

    from y_web.platforms import registry
    from y_web.platforms.base import PlatformProvider

    assert {k: registry.get(k).observer_url(5) for k in registry.keys()} == {
        "microblogging": None,
        "forum": None,
        "photo_sharing": None,
        "instant_messaging": "/5/im",
        "dating": "/5/dating",
    }
    cloning = {k for k in registry.keys() if registry.get(k).folder_clone()}
    assert cloning == {"instant_messaging", "dating"}
    for key in cloning:
        copy_folder, new_uid = registry.get(key).folder_clone()
        assert callable(copy_folder) and callable(new_uid)
    assert registry.resolve("unknown").folder_clone() is None
    validating = {
        k
        for k in registry.keys()
        if type(registry.get(k)).validate_before_start
        is not PlatformProvider.validate_before_start
    }
    assert validating == {"instant_messaging", "dating"}
    assert [
        registry.resolve(k).slots_per_day("/nowhere")
        for k in ("forum", "instant_messaging")
    ] == [24, 24]
    # only the Standard runtime of microblogging and forum starts from the empty server database
    assert {
        (k, s)
        for k in registry.keys()
        for s in ("Standard", "HPC")
        if registry.get(k).creation_rules(s).copies_clean_database
    } == {("microblogging", "Standard"), ("forum", "Standard")}


@needs_dating
@pytest.mark.skipif(
    not _platform_alias.installed(_platform_alias.INSTANT_MESSAGING),
    reason="needs the YInstantMessaging repository",
)
def test_experiment_page_templates_and_variables_match_the_previous_logic():
    from y_web.platforms import registry

    assert {k: registry.get(k).details_template for k in registry.keys()} == {
        "microblogging": "admin/experiment_details.html",
        "forum": "admin/experiment_details_forum.html",
        "photo_sharing": "@photo_sharing/admin/experiment_details_photo.html",
        "instant_messaging": "@instant_messaging/admin/experiment_details_im.html",
        "dating": "@dating/admin/experiment_details_dating.html",
    }
    assert registry.resolve("unknown").details_template == (
        "admin/experiment_details.html"
    )
    assert registry.details_context_defaults() == {
        "forum_feed_health": None,
        "im_analytics": None,
        "im_advanced": None,
        "im_switches": None,
    }
    for key in registry.keys():
        provider = registry.get(key)
        # a platform provides exactly the variables it names
        if not provider.details_context_keys:
            assert provider.details_context(None) == {}


@needs_dating
def test_frontend_capabilities_match_the_previous_tables():
    import json
    import pathlib

    from y_web.platforms import registry
    from y_web.routes.admin.sub.experiments import _frontend_settings as fs

    expected = json.loads(
        (
            pathlib.Path(__file__).parent
            / "data"
            / "platform_baseline"
            / "frontend_capabilities.json"
        ).read_text()
    )
    assert fs.supported_platforms() == tuple(registry.keys())
    for platform, want in expected.items():
        assert fs.capabilities_for(platform) == want["caps"], platform
        assert fs.excluded_capabilities_for(platform) == want["excluded"], platform
        if "label" in want:
            assert fs._localized_platform_label(platform) == want["label"]


@requires_platform("YPhotoSharing")
def test_client_creation_guards_follow_the_provider():
    from y_web.platforms import registry

    # the Standard routes of microblogging and of forum are the only ones that create their clients
    standard = [
        k
        for k in registry.keys() + ["unknown"]
        if registry.resolve(k).client_mode("Standard") == "standard"
        and registry.resolve(k).standard_runtime is not None
    ]
    forum = [
        k for k in registry.keys() if registry.get(k).client_mode("Standard") == "forum"
    ]
    assert (standard, forum) == (["microblogging"], ["forum"])
    assert [
        k for k in registry.keys() if registry.get(k).inherits_client_llm_defaults
    ] == ["forum"]
    # the pack a generic HPC client starts from: photo and forum have their own, the rest the HPC one
    assert {
        k: registry.get(k).experiment_prompt_pack("HPC")
        for k in ("microblogging", "photo_sharing", "forum")
    } == {
        "microblogging": ("prompts_hpc.json", "prompts.json"),
        "photo_sharing": ("prompts_ygram.json", "prompts_ygram.json"),
        "forum": ("prompts_forum.json", "prompts.json"),
    }
