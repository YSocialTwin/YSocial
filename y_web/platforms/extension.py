"""What an installed platform adds to the application: templates, static files and routes.

A platform repository keeps its own pages in ``ysocial_platform/`` (see :attr:`PlatformProvider.package_dir`). They
never mix with the core ones:

* templates are named ``@<provider id>/<template>`` (the ``@`` keeps the namespace apart from the core folders);
* static files are served at ``/platform-static/<provider id>/<path>``;
* blueprints are registered as they are.

The provider id is the identity of the repository (:attr:`PlatformProvider.provider_id`): the platform key unless the
repository declares another one. When a platform key has a single provider the key also works as a namespace
(``@myplatform/...`` for a provider whose id is ``ymyplatform``); with several repositories for one key (a Standard and an HPC
runtime) only the ids do, because a key would not say which repository is meant.

A built-in platform has no ``package_dir`` and adds nothing: installing the extensions is a no-op for it.
Registration happens once at startup; a platform installed later is picked up at the next start (decision D-5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from flask import Flask, abort, send_from_directory
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader

from y_web.platforms import registry

TEMPLATE_PREFIX = "@"
STATIC_URL = "/platform-static"


def template_name(platform_key: str, name: str) -> str:
    """Name under which a template of a platform repository is rendered.

    ``platform_key`` is the namespace of the repository: its provider id, or its platform key while a single
    repository provides that key (the parameter keeps its name for providers written against PLATFORM_API 1.0).
    """
    return f"{TEMPLATE_PREFIX}{platform_key}/{name}"


def provider_template(platform_or_experiment, name: str) -> str:
    """Name of a template of the repository that serves an experiment (or, given a platform key, the preferred one)."""
    provider = registry.resolve(platform_or_experiment)
    return template_name(provider.provider_id, name)


def namespaces(provider) -> List[str]:
    """The namespaces a provider answers to: its id, and its key when no other repository provides that key."""
    names = [provider.provider_id]
    if (
        provider.key != provider.provider_id
        and len(registry.variants(provider.key)) == 1
    ):
        names.append(provider.key)
    return names


def _folder(provider, name: str) -> Path | None:
    folder = provider.package_dir / name if provider.package_dir else None
    return folder if folder is not None and folder.is_dir() else None


def platform_slots(name: str, once_per_key: bool = False) -> List[str]:
    """Templates the installed platforms offer for the slot ``name`` of a core page (``slots/<name>.html``).

    A core page renders them with ``{% for t in platform_slots('name') %}{% include t %}{% endfor %}``; an included
    template sees the variables of the page. A platform without the file adds nothing. With ``once_per_key`` the
    repositories of one platform key (a Standard and an HPC runtime) show one box between them: a box whose
    fields have fixed ids must not appear twice.
    """
    found = []
    served = set()
    for provider in registry.all_providers():
        folder = _folder(provider, "templates")
        if folder is not None and (folder / "slots" / f"{name}.html").is_file():
            if once_per_key:
                if provider.key in served:
                    continue
                served.add(provider.key)
            found.append(template_name(provider.provider_id, f"slots/{name}.html"))
    return found


def _install_templates(app: Flask, folders: Dict[str, Path]) -> None:
    loaders = {
        f"{TEMPLATE_PREFIX}{key}": FileSystemLoader(str(folder))
        for key, folder in folders.items()
    }
    # the core keeps answering for every name without a platform prefix
    app.jinja_env.loader = ChoiceLoader(
        [PrefixLoader(loaders, delimiter="/"), app.jinja_env.loader]
    )


def _install_static(app: Flask, key: str, folder: Path) -> None:
    root = folder.resolve()

    def serve(filename):
        requested = (root / filename).resolve()
        if root not in requested.parents:  # no way out of the platform's own folder
            abort(404)
        return send_from_directory(str(root), filename)

    app.add_url_rule(
        f"{STATIC_URL}/{key}/<path:filename>",
        endpoint=f"platform_static_{key}",
        view_func=serve,
    )


def install_platform_extensions(app: Flask) -> Dict[str, List[str]]:
    """Make the templates, static files and blueprints of the installed platforms available.

    Never raises: a platform that fails is reported and skipped, the others and the core are not affected.
    Returns ``{platform key: [problems]}`` for every platform that has a ``package_dir``.
    """
    app.jinja_env.globals["platform_slots"] = platform_slots
    report: Dict[str, List[str]] = {}
    templates: Dict[str, Path] = {}
    for provider in registry.all_providers():
        if provider.package_dir is None:
            continue
        key = provider.provider_id
        problems = report.setdefault(key, [])
        folder = _folder(provider, "templates")
        if folder is not None:
            for namespace in namespaces(provider):
                templates[namespace] = folder
        folder = _folder(provider, "static")
        if folder is not None:
            for namespace in namespaces(provider):
                try:
                    _install_static(app, namespace, folder)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"static files not served: {exc}")
        try:
            for blueprint in provider.blueprints():
                app.register_blueprint(blueprint)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"blueprints not registered: {exc}")
    if templates:
        _install_templates(app, templates)
    for key, problems in report.items():
        for problem in problems:
            app.logger.warning("[platform %s] %s", key, problem)
    return report
