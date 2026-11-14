"""Registry of the simulation platforms known to the application."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from y_web.platforms.base import PlatformProvider

_PROVIDERS: Dict[str, PlatformProvider] = {}
#: further providers of a key that more than one repository provides (see :func:`variants`)
_EXTRA: Dict[str, List[PlatformProvider]] = {}


def _compatible_variant(existing: PlatformProvider, provider: PlatformProvider) -> bool:
    """Whether two providers of one key can live side by side: distinct repositories serving distinct runtimes."""
    if existing.provider_id == provider.provider_id:
        return False
    if existing.simulator_types is None or provider.simulator_types is None:
        return False
    return not set(existing.simulator_types) & set(provider.simulator_types)


def _add(provider: PlatformProvider) -> PlatformProvider:
    """Register ``provider`` as the first provider of its key or as a variant of the ones already there."""
    key = provider.key
    existing = variants(key)
    if not existing:
        _PROVIDERS[key] = provider
        return provider
    if all(_compatible_variant(other, provider) for other in existing):
        _EXTRA.setdefault(key, []).append(provider)
        return provider
    clash = next(
        (o for o in existing if not _compatible_variant(o, provider)), existing[0]
    )
    raise ValueError(f"platform {key!r} is already provided by {type(clash).__name__}")


def register(provider: PlatformProvider) -> PlatformProvider:
    """Make a platform known. A key can be registered once, unless the providers are variants of it.

    A second provider for a key is an error, never a replacement, except when it comes from another repository
    (another ``id``) and serves other runtimes (``simulator_types``): then it is a variant, chosen per experiment
    by :func:`for_experiment`.
    """
    if not provider.key:
        raise ValueError(f"{type(provider).__name__} has no platform key")
    return _add(provider)


def replace_builtin(provider: PlatformProvider) -> Optional[PlatformProvider]:
    """Register the provider of an installed repository in place of the built-in one of the same key.

    While a platform is moving out of the core, its repository may already carry the provider (it declares
    it in ``meta/registry.json``) and the core still has a built-in copy: the repository wins, so that the
    code that is being moved is the code that runs. Returns the provider that was replaced (``None`` when
    there was none). Two providers from repositories for one key are an error unless they are variants of it.
    """
    existing = _PROVIDERS.get(provider.key)
    if existing is not None and existing.package_dir is not None:
        _add(provider)
        return None
    _PROVIDERS[provider.key] = provider
    return existing


def variants(platform_type: Any) -> List[PlatformProvider]:
    """Every provider of a platform type (one per repository), the preferred one first; empty when nobody provides it."""
    key = str(platform_type or "").strip()
    primary = _PROVIDERS.get(key)
    if primary is None:
        return []
    return [primary, *_EXTRA.get(key, [])]


def by_id(provider_id: Any) -> Optional[PlatformProvider]:
    """The provider of the repository ``provider_id`` (for a provider that declares no ``id``, its platform key)."""
    return next((p for p in all_providers() if p.provider_id == provider_id), None)


def for_simulator(
    platform_type: Any, simulator_type: Any
) -> Optional[PlatformProvider]:
    """The provider that runs ``platform_type`` experiments on ``simulator_type``, or ``None`` when none does.

    With one provider for the key this is that provider whatever the runtime (nothing changes for the platforms
    that have a single repository); with variants it is the one that serves the runtime. Without a runtime to go
    by (``None``) it is the preferred provider of the key.
    """
    found = variants(platform_type)
    if len(found) <= 1 or not simulator_type:
        return found[0] if found else None
    return next((p for p in found if p.serves(simulator_type)), None)


def _split(platform_type: Any, simulator_type: Any = None) -> Tuple[Any, Any]:
    """``(key, runtime)`` of a platform key and an optional runtime, or of an experiment-like object."""
    if hasattr(platform_type, "platform_type"):
        return platform_type.platform_type, getattr(
            platform_type, "simulator_type", simulator_type
        )
    return platform_type, simulator_type


def for_experiment(experiment: Any) -> Optional[PlatformProvider]:
    """The provider of an experiment: its ``platform_type`` run by its ``simulator_type``."""
    return for_simulator(*_split(experiment))


def get(platform_type: Any, simulator_type: Any = None) -> Optional[PlatformProvider]:
    """The provider of a platform type, or ``None`` for a type nobody provides (e.g. a platform no longer installed).

    ``platform_type`` can also be an experiment (anything with ``platform_type`` and ``simulator_type``): the
    provider of its runtime answers. A key with several repositories needs the runtime to say which one is meant;
    without it the preferred one answers (fine for what every variant says the same, like labels and icons).
    """
    key, runtime = _split(platform_type, simulator_type)
    return for_simulator(str(key or "").strip(), runtime)


_GENERIC = PlatformProvider()


def resolve(platform_type: Any, simulator_type: Any = None) -> PlatformProvider:
    """The provider of a platform type (or experiment); a type nobody provides behaves like the generic platform."""
    return get(platform_type, simulator_type) or _GENERIC


def resolve_hooks(experiment: Any) -> PlatformProvider:
    """The provider whose switch, memory and opinion hooks apply to ``experiment``.

    A platform that marks them ``hpc_only_hooks`` answers only for its HPC experiments; for the others the
    generic platform answers (every hook a no-op), which is what they always got.
    """
    provider = resolve(experiment)
    if provider.hpc_only_hooks and getattr(experiment, "simulator_type", None) != "HPC":
        return _GENERIC
    return provider


def choose_simulator(
    platform_type: Any, requested: Any, available: Dict[str, bool]
) -> Tuple[str, Optional[str]]:
    """``(simulator type, problem)`` an experiment of ``platform_type`` is created with, given the one asked for.

    A platform with one provider decides itself (:meth:`PlatformProvider.resolve_simulator`: it knows which
    repositories it needs). With several the repositories are the installed providers: the requested runtime when
    one serves it, else another one, and a problem only when nothing serves the platform.
    """
    found = variants(platform_type)
    if len(found) > 1:
        provider = for_simulator(platform_type, requested)
        if provider is not None:
            return requested, None
        runtimes = [t for p in found for t in (p.simulator_types or ())]
        if runtimes:
            return runtimes[0], None
    return resolve(platform_type).resolve_simulator(requested, available)


def default() -> Optional[PlatformProvider]:
    """The provider marked ``default_platform`` (``None`` when the platform that is the default is not installed)."""
    return next((p for p in providers() if p.default_platform), None)


def providers() -> List[PlatformProvider]:
    """The preferred provider of every platform key, in menu order (variants: :func:`all_providers`)."""
    return sorted(_PROVIDERS.values(), key=lambda p: (p.order, p.key))


def all_providers() -> List[PlatformProvider]:
    """Every provider, variants included, in menu order."""
    return sorted(
        [*_PROVIDERS.values(), *(p for v in _EXTRA.values() for p in v)],
        key=lambda p: (p.order, p.key, p.provider_id),
    )


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


class PlatformNotInstalled(LookupError):
    """A module of a platform was asked for, but the platform is not installed."""


def library(platform_type: Any, name: str) -> Any:
    """Module ``name`` of the platform's own package; :class:`PlatformNotInstalled` when nobody provides it."""
    provider = get(platform_type)
    if provider is None or not provider.library_package:
        raise PlatformNotInstalled(str(platform_type))
    return provider.library(name)


def library_or_none(platform_type: Any, name: str) -> Any:
    """Like :func:`library`, but ``None`` when the platform is not installed."""
    try:
        return library(platform_type, name)
    except PlatformNotInstalled:
        return None
