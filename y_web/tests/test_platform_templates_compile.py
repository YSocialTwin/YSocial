"""Every template of every installed platform repository compiles (a fragment the core includes must not break)."""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def booted_app():
    from y_web import create_app

    return create_app(db_type="sqlite")


def test_every_platform_template_compiles(booted_app):
    from y_web.platforms import registry

    failures, checked = [], 0
    for provider in registry.all_providers():
        if provider.package_dir is None:
            continue
        root = provider.package_dir / "templates"
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.html")):
            name = f"@{provider.provider_id}/{path.relative_to(root).as_posix()}"
            try:
                booted_app.jinja_env.get_template(name)
                checked += 1
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
    if not checked:
        pytest.skip("no platform repository is installed")
    assert not failures, "\n".join(failures[:25])
