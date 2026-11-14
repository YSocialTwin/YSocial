"""Files that live in the repository of a platform, for the tests that read them from disk.

A test that needs one is skipped where the repository is not installed (it is a private plugin).
"""

from pathlib import Path

import pytest

EXTERNAL = Path(__file__).resolve().parents[2] / "external"


def platform_template(repo: str, relative: str) -> str:
    """Text of a template under ``<repo>/ysocial_platform/templates``; skips the test when it is not there."""
    path = EXTERNAL / repo / "ysocial_platform" / "templates" / relative
    if not path.is_file():
        pytest.skip(f"{repo} with its platform pages is not installed")
    return path.read_text(encoding="utf-8")


def platform_source(repo: str, relative: str) -> str:
    """Text of a file under ``<repo>/ysocial_platform``; skips the test when it is not there."""
    path = EXTERNAL / repo / "ysocial_platform" / relative
    if not path.is_file():
        pytest.skip(f"{repo} with its platform files is not installed")
    return path.read_text(encoding="utf-8")


def photo_file(old_relative: str) -> Path:
    """File of the photo-sharing platform that used to be at ``old_relative`` in the core; skips the test when absent.

    ``y_web/templates/photo/...`` and the admin pages of the platform are templates, ``y_web/static/assets/js/photo-*.js``
    are static files, ``y_web/routes/social/photo.py`` is the observer routes module.
    """
    base = EXTERNAL / "YPhotoSharing" / "ysocial_platform"
    if old_relative.startswith("y_web/templates/"):
        path = base / "templates" / old_relative[len("y_web/templates/") :]
    elif old_relative.startswith("y_web/static/assets/js/"):
        path = base / "static" / "js" / old_relative[len("y_web/static/assets/js/") :]
    elif old_relative == "y_web/routes/social/photo.py":
        path = base / "routes" / "social_photo.py"
    else:
        raise ValueError(old_relative)
    if not path.is_file():
        pytest.skip("YPhotoSharing with its platform files is not installed")
    return path


def forum_file(old_relative: str) -> str:
    """File of the forum platform that used to be at ``old_relative`` in the core; skips the test when absent.

    ``y_web/templates/forum/...`` and the admin pages of the platform are templates, ``y_web/static/assets/js/reddit/``,
    ``y_web/static/assets/css/reddit/`` and the ``forum-profile`` scripts are static files.
    """
    base = EXTERNAL / "YForum" / "ysocial_platform"
    for prefix, target in (
        ("y_web/routes/api/reddit.py", "routes/api_reddit.py"),
        ("y_web/routes/social/forum.py", "routes/social_forum.py"),
        ("y_web/routes/interactions/forum.py", "routes/interactions_forum.py"),
        ("y_web/routes/admin/sub/clients/_forum_hpc.py", "routes/clients_forum_hpc.py"),
        ("y_web/routes/admin/sub/clients/_forum_create.py", "routes/clients_forum.py"),
        ("y_web/src/forum/", "forum/"),
        ("y_web/templates/", "templates/"),
        ("y_web/static/assets/js/reddit/", "static/js/"),
        ("y_web/static/assets/css/reddit/", "static/css/"),
        ("y_web/static/assets/js/", "static/js/"),
    ):
        if old_relative.startswith(prefix):
            path = base / (target + old_relative[len(prefix) :])
            if not target.endswith("/"):
                path = base / target
            break
    else:
        raise ValueError(old_relative)
    if not path.is_file():
        pytest.skip("YForum with its platform files is not installed")
    return str(path)


def microblogging_file(old_relative: str) -> str:
    """File of the microblogging platform that used to be at ``old_relative`` in the core; skips the test when absent.

    The pages shared with the other platforms (header, edit profile, chat panel) stayed in the core under a neutral name.
    """
    core = EXTERNAL.parent / "y_web"
    base = EXTERNAL / "YSimulator" / "ysocial_platform"
    if old_relative.startswith("y_web/templates/"):
        relative = old_relative[len("y_web/templates/") :]
        renamed = _renamed()
        if relative in renamed:
            return str(core / "templates" / renamed[relative])
        path = base / "templates" / relative
    elif old_relative.startswith("y_web/static/assets/js/"):
        path = base / "static" / "js" / old_relative.rsplit("/", 1)[1]
    elif old_relative == "y_web/routes/social/microblogging.py":
        path = base / "routes" / "social_microblogging.py"
    elif old_relative == "y_web/routes/interactions/microblogging.py":
        path = base / "routes" / "interactions_microblogging.py"
    else:
        raise ValueError(old_relative)
    if not path.is_file():
        pytest.skip("YSimulator with its platform files is not installed")
    return str(path)


def _renamed():
    import json

    return json.loads(
        (Path(__file__).parent / "data" / "platform_baseline" / "moved.json").read_text(
            "utf-8"
        )
    )["renamed_templates"]


def template_file(root: Path, relative: str) -> Path:
    """File of a template that is in the core or, when it moved out, in the repository it moved to (skips when absent)."""
    path = Path(root) / relative
    if path.is_file():
        return path
    moved = moved_template_path(relative)
    if moved is None:
        pytest.skip(f"{relative} is in a platform repository that is not installed")
    return moved


def template_path(root, *parts) -> str:
    """Path of a template (or template folder) that is in the core or, when it moved out, in its repository.

    Where the repository is absent the core path is returned (it does not exist): the tests that need it are not run.
    """
    path = Path(root).joinpath(*parts)
    if path.exists():
        return str(path)
    relative = "/".join(parts)
    for old, spec in _moved().items():
        target = spec["to"].split("/", 1)[1]
        if old == relative or old.startswith(relative + "/"):
            return str(
                EXTERNAL / spec["repo"] / "ysocial_platform" / "templates" / relative
            )
    return str(path)


def _moved():
    import json

    return json.loads(
        (Path(__file__).parent / "data" / "platform_baseline" / "moved.json").read_text(
            "utf-8"
        )
    )["templates"]


def moved_template_path(old_name: str):
    """File of a template that left the core (``old_name`` is its former name), ``None`` where its repository is absent."""
    spec = _moved().get(old_name)
    if spec is None:
        return None
    path = (
        EXTERNAL
        / spec["repo"]
        / "ysocial_platform"
        / "templates"
        / spec["to"].split("/", 1)[1]
    )
    return path if path.is_file() else None


def namespaced_template_path(name: str):
    """File behind a ``@<platform>/<path>`` template name, ``None`` where its repository is absent."""
    for old, spec in _moved().items():
        if spec["to"] == name:
            return moved_template_path(old)
    return None


def platform_static_path(repo: str, relative: str) -> Path:
    """File under ``<repo>/ysocial_platform/static``; skips the test when it is not there."""
    path = EXTERNAL / repo / "ysocial_platform" / "static" / relative
    if not path.is_file():
        pytest.skip(f"{repo} with its platform files is not installed")
    return path


def core_and_platform_loader():
    """A Jinja loader for the core templates and the ``@<platform>/`` ones of the installed platform repositories."""
    import jinja2

    prefixes = {
        f"@{key}": jinja2.FileSystemLoader(
            str(EXTERNAL / repo / "ysocial_platform" / "templates")
        )
        for key, repo in (
            ("dating", "YDating"),
            ("instant_messaging", "YInstantMessaging"),
            ("photo_sharing", "YPhotoSharing"),
            ("forum", "YForum"),
            ("microblogging", "YSimulator"),
        )
        if (EXTERNAL / repo / "ysocial_platform" / "templates").is_dir()
    }
    return jinja2.ChoiceLoader(
        [
            jinja2.PrefixLoader(prefixes, delimiter="/"),
            jinja2.FileSystemLoader(str(EXTERNAL.parent / "y_web" / "templates")),
        ]
    )


def requires_platform(repo: str):
    """Skip marker for a single test that needs ``repo`` (the tests that need it as a whole are in ``_platform_alias``)."""
    return pytest.mark.skipif(
        not (EXTERNAL / repo / "ysocial_platform").is_dir(),
        reason=f"{repo} with its platform files is not installed",
    )


def photo_available(monkeypatch, value):
    """Make the Photo Sharing form sections (un)available to the administrator."""
    from y_web.platforms import registry

    monkeypatch.setattr(
        registry.library("photo_sharing", "forms"), "available", lambda user=None: value
    )
