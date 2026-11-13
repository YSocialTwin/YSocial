"""A platform repository's templates, static files and blueprints reach the application without touching the core."""

import pytest
from flask import Blueprint, Flask, render_template

from y_web.platforms import registry
from y_web.platforms.base import PlatformProvider
from y_web.platforms.extension import (
    install_platform_extensions,
    template_name,
)


@pytest.fixture
def clean_registry():
    before = dict(registry._PROVIDERS)
    # platforms of installed repositories (found by an application started earlier) are not part of these tests
    for key, provider in before.items():
        if provider.package_dir is not None:
            del registry._PROVIDERS[key]
    yield
    registry._PROVIDERS.clear()
    registry._PROVIDERS.update(before)


def _platform(tmp_path, key="demo", blueprint=None):
    package = tmp_path / "ysocial_platform"
    (package / "templates").mkdir(parents=True)
    (package / "static").mkdir()
    (package / "templates" / "hello.html").write_text("platform says {{ who }}")
    (package / "static" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside")

    class Demo(PlatformProvider):
        pass

    Demo.key = key
    Demo.package_dir = package
    if blueprint is not None:
        Demo.blueprints = lambda self: [blueprint]
    return Demo()


def _app(tmp_path):
    app = Flask(__name__, template_folder=str(tmp_path / "core"))
    (tmp_path / "core").mkdir(exist_ok=True)
    (tmp_path / "core" / "hello.html").write_text("core says {{ who }}")
    return app


def test_templates_are_namespaced_and_the_core_keeps_its_own(tmp_path, clean_registry):
    registry.register(_platform(tmp_path))
    app = _app(tmp_path)
    assert install_platform_extensions(app) == {"demo": []}
    with app.test_request_context():
        assert render_template("hello.html", who="x") == "core says x"
        assert (
            render_template(template_name("demo", "hello.html"), who="y")
            == "platform says y"
        )


def test_static_files_are_served_from_the_platform_folder_only(
    tmp_path, clean_registry
):
    registry.register(_platform(tmp_path))
    app = _app(tmp_path)
    install_platform_extensions(app)
    client = app.test_client()
    assert client.get("/platform-static/demo/app.js").data == b"console.log(1)"
    assert client.get("/platform-static/demo/missing.js").status_code == 404
    assert client.get("/platform-static/demo/../secret.txt").status_code == 404


def test_blueprints_are_registered(tmp_path, clean_registry):
    blueprint = Blueprint("demo_pages", __name__)

    @blueprint.route("/demo")
    def demo():
        return "ok"

    registry.register(_platform(tmp_path, blueprint=blueprint))
    app = _app(tmp_path)
    install_platform_extensions(app)
    assert app.test_client().get("/demo").data == b"ok"


def test_a_failing_platform_is_reported_and_the_others_still_load(
    tmp_path, clean_registry
):
    broken = Blueprint("clash", __name__)
    registry.register(_platform(tmp_path / "a", key="broken", blueprint=broken))
    registry.register(_platform(tmp_path / "b", key="fine"))
    app = _app(tmp_path)
    app.register_blueprint(
        Blueprint("clash", __name__)
    )  # same name: registration fails
    report = install_platform_extensions(app)
    assert report["fine"] == []
    assert report["broken"] and "blueprints not registered" in report["broken"][0]
    with app.test_request_context():
        assert render_template(template_name("fine", "hello.html"), who="z")


def test_built_in_platforms_add_nothing(clean_registry):
    app = Flask(__name__)
    assert install_platform_extensions(app) == {}
    assert app.url_map._rules_by_endpoint.keys() == {"static"}


def test_external_platforms_are_offered_in_the_new_experiment_menu(
    tmp_path, clean_registry, monkeypatch
):
    assert (
        registry.external_platform_options() == []
    )  # built-ins have their own entries
    registry.register(_platform(tmp_path, key="demo"))
    monkeypatch.setattr("flask_babel.gettext", lambda text: text.upper())
    assert registry.external_platform_options() == [{"key": "demo", "label": "OTHER"}]
