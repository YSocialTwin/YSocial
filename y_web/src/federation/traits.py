"""What the World Simulation knows about each platform, asked of the platform's provider (``federation_traits``).

The core holds no table per platform: a platform that is installed declares its traits, one that is not has none (a
member of a platform that is no longer installed shows its type as label and a generic icon).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Dict, List, Optional, Tuple

from y_web.platforms import registry

DEFAULT_TEXT_LIMIT = 280


def traits(platform_type, simulator_type=None):
    """The ``FederationTraits`` of the provider of ``platform_type`` (for ``simulator_type`` when several runtimes), or ``None``."""
    provider = registry.get(platform_type, simulator_type)
    return getattr(provider, "federation_traits", None) if provider else None


def platforms() -> List[str]:
    """Platform types, in menu order, that can take part in a World Simulation."""
    allowed = allowed_simulators()
    return [key for key in registry.keys() if allowed.get(key)]


def label(platform_type, default=None) -> str:
    """Display name of the platform type (``default`` or the type itself when no provider declares it)."""
    provider = registry.get(platform_type)
    if provider is not None and provider.label:
        return str(provider.label)
    return default if default is not None else str(platform_type)


def icon(platform_type, default="link") -> str:
    """Name of the icon of the platform type (``shared/world_simulation_icon.html``)."""
    provider = registry.get(platform_type)
    return provider.icon if provider is not None and provider.icon else default


def mdi_icon(platform_type, default="mdi-web") -> str:
    found = traits(platform_type)
    return found.mdi_icon if found else default


def _attr(name):
    def get(platform_type) -> Optional[str]:
        found = traits(platform_type)
        return getattr(found, name) if found else None

    return get


local_kind = _attr("local_kind")
author_sql = _attr("author_sql")
content_path = _attr("content_path")
profile_path = _attr("profile_path")
account_sql = _attr("account_sql")
account_search_sql = _attr("account_search_sql")


def text_limit(platform_type) -> int:
    found = traits(platform_type)
    return found.text_limit if found else DEFAULT_TEXT_LIMIT


def title_line(platform_type) -> bool:
    found = traits(platform_type)
    return bool(found and found.title_line)


def decision_triggers(platform_type, simulator_type=None) -> Tuple[str, ...]:
    """Events the client of the platform can decide with its LLM (empty: the random draw stays)."""
    found = traits(platform_type, simulator_type)
    return found.decision_triggers if found else ()


def allowed_simulators() -> Dict[str, Tuple[str, ...]]:
    """``{platform type: runtimes it can federate on}``, over every provider of the platform."""
    out: Dict[str, Tuple[str, ...]] = {}
    for provider in registry.all_providers():
        found = getattr(provider, "federation_traits", None)
        if found is None:
            continue
        merged = out.get(provider.key, ())
        out[provider.key] = merged + tuple(
            s for s in found.simulators if s not in merged
        )
    return out


class _PlatformMap(Mapping):
    """``{platform type: value}`` over the installed platforms, read from their providers when asked."""

    def __init__(self, getter):
        self._getter = getter

    def __getitem__(self, key):
        if registry.get(key) is None:
            raise KeyError(key)
        return self._getter(key)

    def __iter__(self):
        return iter(registry.keys())

    def __len__(self):
        return len(registry.keys())


LABELS = _PlatformMap(label)
MDI_ICONS = _PlatformMap(mdi_icon)


def human_gateway(platform_type, simulator_type=None):
    """The ``HumanGatewayTraits`` of the provider that serves ``platform_type`` on ``simulator_type``, or ``None`` when that
    provider has no human gateway (or is not installed)."""
    provider = registry.get(platform_type, simulator_type)
    return getattr(provider, "human_gateway", None) if provider else None
