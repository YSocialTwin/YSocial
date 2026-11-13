"""What an installed platform adds to the application: templates, static files and routes.

A platform repository keeps its own pages in ``ysocial_platform/`` (see :attr:`PlatformProvider.package_dir`). They
never mix with the core ones:

* templates are named ``@<platform key>/<template>`` (the ``@`` keeps the namespace apart from the core folders);
* static files are served at ``/platform-static/<platform key>/<path>``;
* blueprints are registered as they are.

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
    """Name under which a template of a platform repository is rendered."""
    return f"{TEMPLATE_PREFIX}{platform_key}/{name}"


def _folder(provider, name: str) -> Path | None:
    folder = provider.package_dir / name if provider.package_dir else None
    return folder if folder is not None and folder.is_dir() else None


def platform_slots(name: str) -> List[str]:
    """Templates the installed platforms offer for the slot ``name`` of a core page (``slots/<name>.html``).

    A core page renders them with ``{% for t in platform_slots('name') %}{% include t %}{% endfor %}``; an included
    template sees the variables of the page. A platform without the file adds nothing.
    """
    found = []
    for provider in registry.providers():
        folder = _folder(provider, "templates")
        if folder is not None and (folder / "slots" / f"{name}.html").is_file():
            found.append(template_name(provider.key, f"slots/{name}.html"))
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
    for provider in registry.providers():
        if provider.package_dir is None:
            continue
        key = provider.key
        problems = report.setdefault(key, [])
        folder = _folder(provider, "templates")
        if folder is not None:
            templates[key] = folder
        folder = _folder(provider, "static")
        if folder is not None:
            try:
                _install_static(app, key, folder)
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
