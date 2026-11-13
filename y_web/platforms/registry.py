"""Registry of the simulation platforms known to the application."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from y_web.platforms.base import PlatformProvider

_PROVIDERS: Dict[str, PlatformProvider] = {}


def register(provider: PlatformProvider) -> PlatformProvider:
    """Make a platform known. A key can be registered once: a second provider for it is an error, never a replacement."""
    key = provider.key
    if not key:
        raise ValueError(f"{type(provider).__name__} has no platform key")
    if key in _PROVIDERS:
        raise ValueError(
            f"platform {key!r} is already provided by {type(_PROVIDERS[key]).__name__}"
        )
    _PROVIDERS[key] = provider
    return provider


def replace_builtin(provider: PlatformProvider) -> Optional[PlatformProvider]:
    """Register the provider of an installed repository in place of the built-in one of the same key.

    While a platform is moving out of the core, its repository may already carry the provider (it declares
    it in ``meta/registry.json``) and the core still has a built-in copy: the repository wins, so that the
    code that is being moved is the code that runs. Returns the provider that was replaced (``None`` when
    there was none). Two providers from repositories for one key are still an error.
    """
    existing = _PROVIDERS.get(provider.key)
    if existing is not None and existing.package_dir is not None:
        raise ValueError(
            f"platform {provider.key!r} is already provided by {type(existing).__name__}"
        )
    _PROVIDERS[provider.key] = provider
    return existing


def get(platform_type: Any) -> Optional[PlatformProvider]:
    """The provider of a platform type, or ``None`` for a type nobody provides (e.g. a platform no longer installed)."""
    return _PROVIDERS.get(str(platform_type or "").strip())


_GENERIC = PlatformProvider()


def resolve(platform_type: Any) -> PlatformProvider:
    """The provider of a platform type; a type nobody provides behaves like the generic platform."""
    return get(platform_type) or _GENERIC


def providers() -> List[PlatformProvider]:
    """All providers, in menu order."""
    return sorted(_PROVIDERS.values(), key=lambda p: (p.order, p.key))


def keys() -> List[str]:
    return [provider.key for provider in providers()]


def syncs_stress_reward(platform_type: Any) -> bool:
    """Whether the stress/reward setting of the server is copied into the client file of this platform type.

    It is for the platforms with a Standard runtime and for the HPC runtime itself (``"hpc"`` is a runtime
    family that clients are labelled with, not a platform).
    """
    return (
        str(platform_type) == "hpc"
        or resolve(platform_type).standard_runtime is not None
    )


def details_context_defaults() -> Dict[str, None]:
    """Every template variable some platform adds to the experiment page, set to ``None``."""
    return {
        key: None for provider in providers() for key in provider.details_context_keys
    }


def external_platform_options() -> List[Dict[str, str]]:
    """Menu entries (``key``, translated ``label``) of the platforms that come from installed repositories.

    The built-in platforms have their own entries in the new-experiment form; an external one is always available,
    since it is registered only when its repository is installed.
    """
    from flask_babel import gettext

    return [
        {"key": provider.key, "label": gettext(provider.label)}
        for provider in providers()
        if provider.package_dir is not None
    ]
