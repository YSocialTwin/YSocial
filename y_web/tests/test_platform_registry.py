"""The registry of the simulation platforms (plan, phase F1)."""

import pytest

from y_web.platforms import PlatformProvider, registry


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
        ("forum", "/3/rfeed/7/rfeed/rf/1"),
        ("photo_sharing", "/3/photo/feed/all/feed/rf/1"),
        ("instant_messaging", None),
        ("dating", None),
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
        assert forum.location == "/3/rfeed/7/rfeed/rf/1"
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
REACHABLE = [
    (platform, simulator)
    for platform in ("microblogging", "forum", "video_chat", None)
    for simulator in ("Standard", "HPC")
] + [(p, "HPC") for p in ("photo_sharing", "instant_messaging", "dating")]


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
        ("photo_sharing", True),
        ("forum", False),
        ("instant_messaging", False),
        ("dating", False),
    ],
)
def test_which_platforms_create_their_hpc_clients_with_the_generic_route(
    platform, generic
):
    assert registry.resolve(platform).generic_hpc_client_creation is generic


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
