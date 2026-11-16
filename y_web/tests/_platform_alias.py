"""The old import names of the platform modules, for the tests that still live in the core.

Dating and instant messaging moved to their own repositories (``external/<repo>/ysocial_platform``). The tests of their
behaviour run inside the YSocial test session (they need its fixtures), so they keep importing ``y_web.src.dating.*``,
``y_web.src.im.*`` and the old view modules: this installs those names as aliases of the modules in the repository.
Where a repository is not installed nothing is installed for it and its tests are not collected.
"""

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

EXTERNAL = Path(__file__).resolve().parents[2] / "external"


@dataclass(frozen=True)
class Platform:
    repo: str  # folder under external/
    key: str  # key of the repository in the runtime registry: it names the module namespace
    old_package: str  # where the platform's own modules used to live in the core ("" when it had none)
    library: str  # their package inside ``ysocial_platform`` ("" when the platform has no library)
    provider_class: str
    #: old module name -> module in the repository package ``ysocial_platform``
    views: Dict[str, str] = field(default_factory=dict)
    needs: Tuple[str, ...] = ()  # tests that need the repository
    provider_id: str = (
        ""  # id of its provider when it is not the key (a platform with several repositories)
    )
    routes: Tuple[
        str, ...
    ] = ()  # modules that only register routes (no old name to alias)
    #: package of the repository that stands in for ``old_package`` when no other repository provides it
    fallback_library: str = ""
    #: tests that run with any of the repositories that list them (they need one of them, not each)
    needs_any: Tuple[str, ...] = ()
    fallback_package: str = ""


DATING = Platform(
    repo="YDating",
    key="dating",
    old_package="y_web.src.dating",
    library="dating",
    provider_class="Dating",
    views={
        "y_web.routes.social.dating": "routes.social_dating",
        "y_web.routes.social.dating_participant": "routes.social_dating_participant",
        "y_web.routes.admin.sub.clients._dating": "routes.clients_dating",
        "y_web.routes.admin.sub.experiments._dating": "routes.experiments_dating",
        "y_web.routes.admin.sub.experiments._dating_analytics": "routes.experiments_dating_analytics",
        "y_web.routes.admin.sub.experiments._dating_participants": "routes.experiments_dating_participants",
        "y_web.routes.admin.sub.experiments._dating_prompts": "routes.experiments_dating_prompts",
        "y_web.routes.admin.sub._populations_dating": "population_admin",
        "y_web.routes.admin.sub._populations_dating_routes": "routes.populations_dating",
    },
    needs=(
        "test_agent_form_optional_sections.py",
        "test_dating_agent_form.py",
        "test_dating_analytics.py",
        "test_dating_experiment_creation.py",
        "test_dating_observer.py",
        "test_dating_observer_perf.py",
        "test_dating_participant.py",
        "test_dating_participant_login.py",
        "test_dating_population.py",
        "test_dating_prompts.py",
        "test_dating_run.py",
        "test_dating_settings.py",
        "test_dating_settings_ui.py",
        "test_federation_human_composer.py",
        "test_federation_p1.py",
        "test_population_appearance_pictures.py",
        "test_population_platform_fields.py",
        "test_template_refactoring.py",
    ),
)

INSTANT_MESSAGING = Platform(
    repo="YInstantMessaging",
    key="instant_messaging",
    old_package="y_web.src.im",
    library="im",
    provider_class="InstantMessaging",
    views={
        "y_web.routes.social.instant_messaging": "routes.social_im",
        "y_web.routes.admin.sub.clients._im": "routes.clients_im",
        "y_web.routes.admin.sub.experiments._im": "im.server_config",
        "y_web.routes.admin.sub.experiments._im_exports": "routes.experiments_im_exports",
        "y_web.routes.admin.sub.experiments._im_prompts": "routes.experiments_im_prompts",
    },
    needs=tuple(
        sorted(path.name for path in Path(__file__).parent.glob("test_im_*.py"))
    )
    + ("test_stress_reward_churn_settings.py",),  # its experiments are IM ones
)

PHOTO_SHARING = Platform(
    repo="YPhotoSharing",
    key="photo_sharing",
    old_package="",  # its library is new: nothing was importable under an old name
    library="photo",
    provider_class="PhotoSharing",
    views={
        "y_web.routes.social.photo": "routes.social_photo",
    },
    needs=tuple(
        sorted(path.name for path in Path(__file__).parent.glob("test_photo_*.py"))
    )
    + (  # a population is tagged with a platform only when the platform is installed
        "test_agents_platform.py",
        "test_population_listing_platform.py",
    ),
)

#: World Simulation tests: they put members of every runtime (Standard and HPC) of the platforms in one group
_WORLD_SIMULATION_TESTS = (
    "test_dashboard_world_simulation.py",
    "test_federation_backlinks.py",
    "test_federation_human_outbox.py",
    "test_federation_humans.py",
    "test_federation_lifecycle.py",
    "test_federation_notifications.py",
    "test_federation_optional_plugin.py",
    "test_federation_p1.py",
    "test_federation_participant_texts.py",
    "test_federation_profile_badges.py",
    "test_federation_quoted_flag.py",
    "test_federation_quotes.py",
    "test_federation_service.py",
    "test_world_simulation_agents.py",
    "test_world_simulation_analytics.py",
    "test_world_simulation_crosspost_agent_action.py",
    "test_world_simulation_crosspost_content.py",
    "test_world_simulation_crosspost_warning.py",
    "test_world_simulation_crossposts.py",
    "test_world_simulation_frontends.py",
    "test_world_simulation_humans_lifecycle.py",
    "test_world_simulation_humans_ui.py",
    "test_world_simulation_import.py",
    "test_world_simulation_lifecycle.py",
    "test_world_simulation_member_health.py",
    "test_world_simulation_options_form.py",
    "test_world_simulation_pseudonyms.py",
    "test_world_simulation_same_platform.py",
    "test_world_simulation_schedule.py",
    "test_world_simulation_ui.py",
)

#: tests of the forum library (``y_web.src.forum``), which the HPC repository (YForum) provides
_FORUM_LIBRARY_TESTS = (
    "test_forum_community_icons.py",
    "test_phase8_src_forum.py",
)
#: tests of what the Standard repository (YServerReddit) provides: avatars, the feed service and the field groups
_FORUM_SERVICE_TESTS = (
    "test_content_article_and_avatars.py",
    "test_forum_opaque_ids.py",
    "test_forum_reddit_ui_templates.py",
    "test_frontend_settings_platforms.py",
    "test_population_appearance_pictures.py",
    "test_population_custom_field_stats.py",
)

#: tests that use the microblogging platform's settings page, offered by either of its repositories
_MICROBLOGGING_TESTS = (
    "test_content_recsys_mode_normalization.py",
    "test_personalized_feed.py",
    "test_recsys_support.py",
    "test_frontend_settings_generic_suite_panel.py",
    "test_i18n_experiment_language.py",
    "test_im_frontend_settings.py",
    "test_training_modules_advance_integration.py",
    "test_training_modules_preview_integration.py",
    "test_training_modules_teacher_integration.py",
)

FORUM = Platform(  # the Standard runtime: its repository is YServerReddit
    repo="YServerReddit",
    key="forum_server",
    old_package="",
    library="",
    provider_class="ForumStandard",
    provider_id="ysocial_server_reddit",
    views={
        "y_web.routes.social.forum": "routes.social_forum",
        "y_web.routes.interactions.forum": "routes.interactions_forum",
        "y_web.routes.api.reddit": "routes.api_reddit",
        "y_web.routes.admin.sub.experiments._forum_feeds": "routes.feeds_forum",
        "y_web.src.content.avatars": "forum.avatars",
        "y_web.src.commons.service": "forum.service",
        "y_web.src.commons.service.queries": "forum.service.queries",
        "y_web.src.commons.service.formatters": "forum.service.formatters",
        "y_web.src.commons.service.data_classes": "forum.service.data_classes",
        "y_web.src.commons.hot_rank": "forum.hot_rank",
    },
    needs=(
        "test_api_reddit_blueprint.py",
        "test_forum_feed_resource_registry.py",
        "test_forum_feed_sidebar.py",
        "test_forum_search_suggest.py",
    )
    + _FORUM_SERVICE_TESTS
    + _WORLD_SIMULATION_TESTS,
)

FORUM_HPC = Platform(  # the HPC runtime of the forum: its pages are served next to YServerReddit's
    repo="YForum",
    key="forum_hpc",
    old_package="y_web.src.forum",
    library="forum",
    provider_class="Forum",
    provider_id="forum",
    views={"y_web.routes.admin.sub.clients._forum_hpc": "routes.clients_forum_hpc"},
    routes=("routes.social_forum", "routes.interactions_forum", "routes.api_reddit"),
    needs=tuple(
        sorted(path.name for path in Path(__file__).parent.glob("test_forum_hpc*.py"))
    )
    + (
        "test_forum_plugin_listing.py",
        "test_dating_runtime_registration.py",
        "test_hpc_client_failure_alert.py",
        "test_forum_client_config.py",
        "test_forum_communities_config.py",
        "test_forum_edit_profile.py",
        "test_forum_experiment_config.py",
        "test_forum_reddit_ui_templates.py",
        "test_forum_roster.py",
        "test_forum_feed_sidebar.py",
    )
    + _FORUM_LIBRARY_TESTS
    + _WORLD_SIMULATION_TESTS,
)

MICROBLOGGING = Platform(  # the Standard runtime: its repository is YServer
    repo="YServer",
    key="microblogging_server",
    provider_class="MicrobloggingStandard",
    provider_id="ysocial_server",
    # the recommender systems of the people of the frontend live in the platform (``y_web.src.recsys`` was theirs)
    old_package="y_web.src.recsys",
    library="recsys",
    views={
        "y_web.routes.social.microblogging": "routes.social_microblogging",
        "y_web.routes.interactions.microblogging": "routes.interactions_microblogging",
    },
    needs=(
        "test_microblog_follow_links.py",
        "test_microblog_chat_component.py",
        "test_phaseT5_css_extraction.py",
        "test_trending_hashtag_prefix.py",
        "test_training_modules_baseline_access.py",
    )
    + _WORLD_SIMULATION_TESTS,
    needs_any=_MICROBLOGGING_TESTS,
)

MICROBLOGGING_HPC = Platform(  # the HPC runtime of the same platform: its routes are served next to YServer's
    repo="YSimulator",
    key="hpc_simulator",
    old_package="",
    library="",
    provider_class="Microblogging",
    provider_id="microblogging",
    fallback_package="y_web.src.recsys",  # its own copy of the recommenders, used when YServer is absent
    fallback_library="recsys",
    routes=("routes.social_microblogging", "routes.interactions_microblogging"),
    needs=_WORLD_SIMULATION_TESTS
    + (  # the launch table row of the HPC runtime
        "test_hpc_platform_characterization.py",
        "test_hpc_progress_tracking.py",
        "test_hpc_server_pid_lifecycle.py",
    ),
    needs_any=_MICROBLOGGING_TESTS,
)

PLATFORMS = (
    DATING,
    INSTANT_MESSAGING,
    PHOTO_SHARING,
    FORUM,
    FORUM_HPC,
    MICROBLOGGING,
    MICROBLOGGING_HPC,
)

_state: Dict[str, bool] = {}


def installed(platform: Platform = None) -> bool:
    """Whether the aliases of ``platform`` (any platform when ``None``) are installed."""
    if platform is None:
        return any(_state.get(p.key) for p in PLATFORMS)
    return bool(_state.get(platform.key))


def _present(platform: Platform) -> bool:
    base = EXTERNAL / platform.repo / "ysocial_platform"
    return (
        (base / platform.library / "__init__.py")
        if platform.library
        else base / "provider.py"
    ).is_file()


def _root(platform: Platform) -> str:
    from y_web.src.external_runtime.backend_plugins import _ensure_namespace_root

    return _ensure_namespace_root(platform.key, EXTERNAL / platform.repo)


def _alias_package(
    platform: Platform, old_package: str, library: str, package=None
) -> None:
    """Install ``old_package`` and its modules as aliases of the ``library`` package of the repository."""
    root = _root(platform)

    def load(name):
        return importlib.import_module(f"{root}.ysocial_platform.{name}")

    package = package or load(library)
    sys.modules[old_package] = package
    parent, _, leaf = old_package.rpartition(".")
    setattr(importlib.import_module(parent), leaf, package)
    folder = EXTERNAL / platform.repo / "ysocial_platform" / library
    for path in sorted(folder.glob("*.py")):
        if path.stem == "__init__":
            continue
        sys.modules[f"{old_package}.{path.stem}"] = load(f"{library}.{path.stem}")
    for sub in sorted(p for p in folder.iterdir() if (p / "__init__.py").is_file()):
        sys.modules[f"{old_package}.{sub.name}"] = load(f"{library}.{sub.name}")
        for path in sorted(sub.glob("*.py")):
            if path.stem != "__init__":
                sys.modules[f"{old_package}.{sub.name}.{path.stem}"] = load(
                    f"{library}.{sub.name}.{path.stem}"
                )


def _install_one(platform: Platform) -> bool:
    if _state.get(platform.key):
        return True
    if not _present(platform):
        return False
    root = _root(
        platform
    )  # the namespace discovery uses at startup, so the application finds these modules loaded

    def load(name):
        return importlib.import_module(f"{root}.ysocial_platform.{name}")

    package = load(platform.library) if platform.library else None
    if platform.old_package:
        _alias_package(platform, platform.old_package, platform.library, package)
    for name in platform.routes:
        load(name)
    for old, new in platform.views.items():
        module = load(new)
        sys.modules[old] = module
        parent, _, leaf = old.rpartition(".")
        setattr(importlib.import_module(parent), leaf, module)
    _state[platform.key] = True
    _register(platform)
    return True


def install() -> bool:
    """Install the aliases of every platform whose repository is present; true when all of them are."""
    from y_web.platforms import dispatch

    # the repositories of one platform serve some addresses together: their routes are registered together too
    with dispatch.collecting():
        results = []
        for platform in PLATFORMS:
            with dispatch.attaching(platform.provider_id or platform.key):
                results.append(_install_one(platform))
        for platform in PLATFORMS:
            if (
                platform.fallback_package
                and _state.get(platform.key)
                and platform.fallback_package not in sys.modules
            ):
                with dispatch.attaching(platform.provider_id or platform.key):
                    _alias_package(
                        platform, platform.fallback_package, platform.fallback_library
                    )
    return all(results)


def _register(platform: Platform) -> None:
    """Register the provider of the repository when the registry has none for its key (what discovery does)."""
    from y_web.platforms import registry

    if registry.by_id(platform.provider_id or platform.key) is not None:
        return
    module = importlib.import_module(f"{_root(platform)}.ysocial_platform.provider")
    provider = getattr(module, platform.provider_class)()
    provider.package_dir = EXTERNAL / platform.repo / "ysocial_platform"
    registry.replace_builtin(provider)


def register_provider() -> None:
    """Register the providers of the installed repositories (the tests that build their own application need it)."""
    for platform in PLATFORMS:
        if _state.get(platform.key):
            _register(platform)


def absent_tests() -> list:
    """Test files that need a repository that is not installed (they are not collected)."""
    out = []
    for platform in PLATFORMS:
        if not _state.get(platform.key):
            out.extend(platform.needs)
    for name in sorted({n for p in PLATFORMS for n in p.needs_any}):
        if not any(_state.get(p.key) for p in PLATFORMS if name in p.needs_any):
            out.append(name)
    return out


#: tests that need the Dating repository (kept for the callers that name it)
NEEDS_REPOSITORY = DATING.needs
