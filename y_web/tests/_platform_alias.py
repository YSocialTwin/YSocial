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
    old_package: str  # where the platform's own modules used to live in the core
    library: str  # their package inside ``ysocial_platform``
    provider_class: str
    #: old module name -> module in the repository package ``ysocial_platform``
    views: Dict[str, str] = field(default_factory=dict)
    needs: Tuple[str, ...] = ()  # tests that need the repository


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
    ),
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
    ),
)

FORUM = Platform(
    repo="YForum",
    key="forum",
    old_package="y_web.src.forum",
    library="forum",
    provider_class="Forum",
    views={
        "y_web.routes.social.forum": "routes.social_forum",
        "y_web.routes.interactions.forum": "routes.interactions_forum",
        "y_web.routes.api.reddit": "routes.api_reddit",
        "y_web.routes.admin.sub.clients._forum_hpc": "routes.clients_forum_hpc",
    },
    needs=tuple(
        sorted(path.name for path in Path(__file__).parent.glob("test_forum_*.py"))
    )
    + (
        "test_api_reddit_blueprint.py",
        "test_hpc_client_failure_alert.py",
        "test_phase8_src_forum.py",
        "test_template_refactoring.py",
    ),
)

PLATFORMS = (DATING, INSTANT_MESSAGING, PHOTO_SHARING, FORUM)

_state: Dict[str, bool] = {}


def installed(platform: Platform = None) -> bool:
    """Whether the aliases of ``platform`` (any platform when ``None``) are installed."""
    if platform is None:
        return any(_state.get(p.key) for p in PLATFORMS)
    return bool(_state.get(platform.key))


def _present(platform: Platform) -> bool:
    return (
        EXTERNAL / platform.repo / "ysocial_platform" / platform.library / "__init__.py"
    ).is_file()


def _root(platform: Platform) -> str:
    from y_web.src.external_runtime.backend_plugins import _ensure_namespace_root

    return _ensure_namespace_root(platform.key, EXTERNAL / platform.repo)


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

    package = load(platform.library)
    if platform.old_package:
        sys.modules[platform.old_package] = package
        parent, _, leaf = platform.old_package.rpartition(".")
        setattr(importlib.import_module(parent), leaf, package)
        folder = EXTERNAL / platform.repo / "ysocial_platform" / platform.library
        for path in sorted(folder.glob("*.py")):
            if path.stem == "__init__":
                continue
            sys.modules[f"{platform.old_package}.{path.stem}"] = load(
                f"{platform.library}.{path.stem}"
            )
        for sub in sorted(p for p in folder.iterdir() if (p / "__init__.py").is_file()):
            sys.modules[f"{platform.old_package}.{sub.name}"] = load(
                f"{platform.library}.{sub.name}"
            )
            for path in sorted(sub.glob("*.py")):
                if path.stem != "__init__":
                    sys.modules[f"{platform.old_package}.{sub.name}.{path.stem}"] = (
                        load(f"{platform.library}.{sub.name}.{path.stem}")
                    )
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
    results = [_install_one(platform) for platform in PLATFORMS]
    return all(results)


def _register(platform: Platform) -> None:
    """Register the provider of the repository when the registry has none for its key (what discovery does)."""
    from y_web.platforms import registry

    if registry.get(platform.key) is not None:
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
    return out


#: tests that need the Dating repository (kept for the callers that name it)
NEEDS_REPOSITORY = DATING.needs
