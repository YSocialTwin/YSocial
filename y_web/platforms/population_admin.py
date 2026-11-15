"""How the population administration asks the platforms that have populations of their own.

A platform whose populations are not the standard ones (its agents carry fields of their own, its documents have their
own format) offers ``PlatformProvider.population_admin``: an object with any of the functions below, none of which is
required. The administration calls them for every platform that has one, in the order of the platforms, so the core
never names a platform:

``wants_generation(form)`` / ``generate()``
    the creation form asks for a population of this platform; ``generate`` answers the request.
``wants_upload(form, upload)`` / ``upload()``
    the uploaded file is a population document of this platform; ``upload`` answers the request.
``runtime_missing(user)``
    translated reason the optional fields cannot be generated (the runtime is not installed), or ``None``.
``complete_with_fields(population)``
    give the agents just generated the platform's fields (the creation form had its section on).
``owns(population)``, ``sync_if_needed(population)``, ``sync(population)``, ``remove_agents_of(population)``
    populations of the platform: whom they belong to, the columns the list reads, and their removal.
``discard_agents(population_id)``
    remove the agents of a population whose generation failed.
``form_context()`` / ``details_context(uid, population)``
    template variables of the creation form and of the details page.
``download_url(uid)``
    where a population of the platform is downloaded from, or ``None`` when it is a standard one.
``includes_own_appearance``
    the platform's fields include the appearance, so the standard Appearance section is not applied on top.
``form_flag``
    name of the creation-form field that switches the platform's fields on.
"""

from __future__ import annotations

from typing import Any, Iterator, List, Optional, Tuple

from y_web.platforms import registry


def _admins() -> List[Tuple[Any, Any]]:
    return [
        (provider, provider.population_admin)
        for provider in registry.providers()
        if provider.population_admin is not None
    ]


def _each(function: str) -> Iterator[Tuple[Any, Any]]:
    for provider, admin in _admins():
        method = getattr(admin, function, None)
        if method is not None:
            yield provider, method


def generation_response(form):
    """The response of the platform whose population the form asks for, or ``None`` for a standard one."""
    for admin in (a for _p, a in _admins()):
        asks = getattr(admin, "wants_generation", None)
        if asks is not None and asks(form):
            return admin.generate()
    return None


def upload_response(form, upload):
    """The response of the platform whose document was uploaded, or ``None`` for a standard population file."""
    for admin in (a for _p, a in _admins()):
        asks = getattr(admin, "wants_upload", None)
        if asks is not None and asks(form, upload):
            return admin.upload()
    return None


def included(flag) -> list:
    """The administrations whose fields the creation form switched on (``flag(name)`` reads a checkbox)."""
    return [
        admin
        for _p, admin in _admins()
        if getattr(admin, "form_flag", None) and flag(admin.form_flag)
    ]


def runtime_missing(admins, user) -> Optional[str]:
    for admin in admins:
        method = getattr(admin, "runtime_missing", None)
        reason = method(user) if method is not None else None
        if reason:
            return reason
    return None


def complete_with_fields(admins, population) -> None:
    for admin in admins:
        method = getattr(admin, "complete_with_fields", None)
        if method is not None:
            method(population)


def own_appearance(admins) -> bool:
    return any(getattr(a, "includes_own_appearance", False) for a in admins)


def sync_if_needed(population) -> None:
    for _p, method in _each("sync_if_needed"):
        method(population)


def sync(population) -> None:
    for _p, method in _each("sync"):
        method(population)


def remove_agents_of(population) -> None:
    for _p, method in _each("remove_agents_of"):
        method(population)


def discard_agents(population_id) -> None:
    for _p, method in _each("discard_agents"):
        method(population_id)


def form_context() -> dict:
    context: dict = {}
    for _p, method in _each("form_context"):
        context.update(method())
    return context


def details_context(uid, population) -> dict:
    context: dict = {}
    for _p, method in _each("details_context"):
        context.update(method(uid, population))
    return context


def download_url(uid) -> Optional[str]:
    for _p, method in _each("download_url"):
        url = method(uid)
        if url:
            return url
    return None
