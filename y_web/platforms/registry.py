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
