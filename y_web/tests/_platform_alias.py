"""The old import names of the Dating modules, for the tests that still live in the core.

Dating moved to its own repository (``external/YDating/ysocial_platform``). The tests of its behaviour run inside the
YSocial test session (they need its fixtures), so they keep importing ``y_web.src.dating.*`` and the old view modules:
this installs those names as aliases of the modules in the repository. Where the repository is not installed nothing is
installed and ``installed()`` is false, so those tests are not collected.
"""

import importlib.util
import sys
from pathlib import Path

REPO = "YDating"  # folder under external/
REPO_KEY = "dating"  # key of the repository in the runtime registry: it names the module namespace
EXTERNAL = Path(__file__).resolve().parents[2] / "external"

#: old module name -> module in the repository package ``ysocial_platform``
_VIEWS = {
    "y_web.routes.social.dating": "routes.social_dating",
    "y_web.routes.social.dating_participant": "routes.social_dating_participant",
    "y_web.routes.admin.sub.clients._dating": "routes.clients_dating",
    "y_web.routes.admin.sub.experiments._dating": "routes.experiments_dating",
    "y_web.routes.admin.sub.experiments._dating_analytics": "routes.experiments_dating_analytics",
    "y_web.routes.admin.sub.experiments._dating_participants": "routes.experiments_dating_participants",
    "y_web.routes.admin.sub.experiments._dating_prompts": "routes.experiments_dating_prompts",
}

_state = {"installed": False}


def installed() -> bool:
    return _state["installed"]


def _present() -> bool:
    return (EXTERNAL / REPO / "ysocial_platform" / "dating" / "__init__.py").is_file()


def install() -> bool:
    if _state["installed"]:
        return True
    if not _present():
        return False
    from y_web.src.external_runtime.backend_plugins import _ensure_namespace_root

    # the namespace discovery uses at startup, so the application finds these modules already loaded
    root = _ensure_namespace_root(REPO_KEY, EXTERNAL / REPO)

    def load(name):
        return importlib.import_module(f"{root}.ysocial_platform.{name}")

    package = load("dating")
    sys.modules["y_web.src.dating"] = package
    import y_web.src

    y_web.src.dating = package
    folder = EXTERNAL / REPO / "ysocial_platform" / "dating"
    for path in sorted(folder.glob("*.py")):
        if path.stem == "__init__":
            continue
        sys.modules[f"y_web.src.dating.{path.stem}"] = load(f"dating.{path.stem}")
    for old, new in _VIEWS.items():
        module = load(new)
        sys.modules[old] = module
        parent, _, leaf = old.rpartition(".")
        setattr(importlib.import_module(parent), leaf, module)
    _state["installed"] = True
    register_provider()
    return True


def register_provider() -> None:
    """Register the provider of the repository when the registry has none for ``dating`` (what discovery does)."""
    from y_web.platforms import registry

    if registry.get("dating") is not None:
        return
    from y_web.src.external_runtime.backend_plugins import _ensure_namespace_root

    root = _ensure_namespace_root(REPO_KEY, EXTERNAL / REPO)
    module = importlib.import_module(f"{root}.ysocial_platform.provider")
    provider = module.Dating()
    provider.package_dir = EXTERNAL / REPO / "ysocial_platform"
    registry.replace_builtin(provider)


#: tests that need the Dating repository (they import its modules or drive its views)
NEEDS_REPOSITORY = (
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
)
