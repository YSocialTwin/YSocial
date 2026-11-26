"""What an extension needs from the core, and what the core checks before it loads or installs one.

An extension declares, in ``meta/info.json``:

* ``min_core_version``: the oldest YSocial it works on (``"4.1.0"``);
* ``max_core_version``: optional, only for a known limit;
* ``extension_api``: the extension API it was written for, as a version range (``"^1.0"``, ``">=1.0,<2"``).

The checks never raise: they return the problems, so that one broken manifest cannot take down the pages that list
the extensions.
"""

from __future__ import annotations

import re
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

_CARET = re.compile(r"^\^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?$")


def extension_api_version() -> str:
    from y_web.sdk.extensions import EXTENSION_API

    return EXTENSION_API


def _version(value: Any) -> Version | None:
    try:
        return Version(str(value).strip())
    except InvalidVersion:
        return None


def parse_range(text: Any) -> SpecifierSet | None:
    """A version range: ``^1.0`` means ``>=1.0,<2``; anything ``SpecifierSet`` accepts is allowed too."""
    value = str(text).strip()
    caret = _CARET.match(value)
    if caret:
        major, minor, patch = (int(g) if g is not None else 0 for g in caret.groups())
        return SpecifierSet(f">={major}.{minor}.{patch},<{major + 1}")
    try:
        return SpecifierSet(value)
    except InvalidSpecifier:
        return None


def info_requirement_problems(
    info: Any, core_version: str | None, *, api_version: str | None = None
) -> tuple[list[str], list[str]]:
    """``(errors, warnings)`` for the requirements declared in ``meta/info.json``.

    An extension that declares neither field still loads (a warning); a field that is malformed, or that asks for more
    than this core offers, is an error and the extension is not loaded.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(info, dict):
        return errors, warnings
    api_version = api_version or extension_api_version()
    declared = False

    core = _version(core_version) if core_version else None

    if "min_core_version" in info:
        declared = True
        minimum = _version(info["min_core_version"])
        if minimum is None:
            errors.append(
                f"meta/info.json: 'min_core_version' is not a version: {info['min_core_version']!r}"
            )
        elif core is not None and core < minimum:
            errors.append(f"requires YSocial {minimum} or later, this is {core}")
    if "max_core_version" in info:
        declared = True
        maximum = _version(info["max_core_version"])
        if maximum is None:
            errors.append(
                f"meta/info.json: 'max_core_version' is not a version: {info['max_core_version']!r}"
            )
        elif core is not None and core > maximum:
            errors.append(f"supports YSocial up to {maximum}, this is {core}")
    if "extension_api" in info:
        declared = True
        wanted = parse_range(info["extension_api"])
        if wanted is None:
            errors.append(
                f"meta/info.json: 'extension_api' is not a version range: {info['extension_api']!r}"
            )
        elif not wanted.contains(api_version, prereleases=True):
            errors.append(
                f"requires extension API {info['extension_api']}, this YSocial offers {api_version}"
            )
    if not declared:
        warnings.append(
            "meta/info.json: declares neither 'min_core_version' nor 'extension_api'"
        )
    return errors, warnings


def install_requirement_problem(spec: Any, core_version: str | None) -> str | None:
    """Why ``spec`` cannot be installed on this core, or ``None``. Used before anything is downloaded."""
    minimum_text = getattr(spec, "min_ysocial_version", None)
    if not minimum_text or not core_version:
        return None
    minimum, core = _version(minimum_text), _version(core_version)
    if minimum is None or core is None:
        return None
    if core < minimum:
        return (
            f"{getattr(spec, 'label', 'This plugin')} needs YSocial {minimum} or later "
            f"(this is {core}); nothing was downloaded"
        )
    return None
