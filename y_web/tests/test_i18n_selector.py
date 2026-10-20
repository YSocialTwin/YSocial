"""Language selection for the admin and simulation contexts (F1-2)."""

import pytest
from flask import Blueprint, Flask, jsonify
from flask_babel import get_locale
from flask_login import LoginManager, UserMixin, login_user

import y_web.i18n as i18n


class _Admin(UserMixin):
    def __init__(self, lang):
        self.id = "1"
        self.lang = lang


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True, SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it", "es")
    )
    lm = LoginManager(app)
    users = {}

    @lm.user_loader
    def load(uid):
        return users.get(uid)

    admin = Blueprint("admin", __name__)
    sim = Blueprint("main", __name__)

    @admin.route("/a")
    def a():
        return str(get_locale())

    @sim.route("/s")
    def s():
        return str(get_locale())

    @app.route("/login-as/<lang>")
    def login_as(lang):
        user = _Admin(None if lang == "none" else lang)
        users["1"] = user
        login_user(user)
        return "ok"

    app.register_blueprint(admin)
    app.register_blueprint(sim)
    i18n.init_i18n(app)
    yield app
    i18n.experiment_language_resolver = None


def test_admin_defaults_to_english(app):
    assert app.test_client().get("/a").get_data(as_text=True) == "en"


def test_admin_uses_accept_language(app):
    r = app.test_client().get("/a", headers={"Accept-Language": "it-IT,it;q=0.9"})
    assert r.get_data(as_text=True) == "it"


def test_admin_unsupported_accept_language_falls_back_to_english(app):
    r = app.test_client().get("/a", headers={"Accept-Language": "fr"})
    assert r.get_data(as_text=True) == "en"


def test_admin_cookie_beats_accept_language(app):
    c = app.test_client()
    c.set_cookie(i18n.ADMIN_COOKIE, "es")
    r = c.get("/a", headers={"Accept-Language": "it"})
    assert r.get_data(as_text=True) == "es"


def test_admin_invalid_cookie_is_ignored(app):
    c = app.test_client()
    c.set_cookie(i18n.ADMIN_COOKIE, "xx")
    assert c.get("/a").get_data(as_text=True) == "en"


def test_saved_user_language_beats_cookie_and_header(app):
    c = app.test_client()
    c.get("/login-as/it")
    c.set_cookie(i18n.ADMIN_COOKIE, "es")
    r = c.get("/a", headers={"Accept-Language": "es"})
    assert r.get_data(as_text=True) == "it"


def test_user_without_saved_language_uses_cookie(app):
    c = app.test_client()
    c.get("/login-as/none")
    c.set_cookie(i18n.ADMIN_COOKIE, "es")
    assert c.get("/a").get_data(as_text=True) == "es"


def test_simulation_ignores_accept_language_and_admin_cookie(app):
    c = app.test_client()
    c.set_cookie(i18n.ADMIN_COOKIE, "es")
    r = c.get("/s", headers={"Accept-Language": "it"})
    assert r.get_data(as_text=True) == "en"


def test_simulation_uses_experiment_language(app):
    i18n.experiment_language_resolver = lambda: ("it", True)
    assert app.test_client().get("/s").get_data(as_text=True) == "it"


def test_simulation_override_allowed(app):
    i18n.experiment_language_resolver = lambda: ("it", True)
    c = app.test_client()
    c.set_cookie(i18n.SIMULATION_COOKIE, "es")
    assert c.get("/s").get_data(as_text=True) == "es"


def test_simulation_override_disabled(app):
    i18n.experiment_language_resolver = lambda: ("it", False)
    c = app.test_client()
    c.set_cookie(i18n.SIMULATION_COOKIE, "es")
    assert c.get("/s").get_data(as_text=True) == "it"


def test_simulation_resolver_failure_falls_back_to_english(app):
    def boom():
        raise RuntimeError("no experiment")

    i18n.experiment_language_resolver = boom
    assert app.test_client().get("/s").get_data(as_text=True) == "en"


def test_normalize_language(app):
    with app.app_context():
        assert i18n.normalize_language("it_IT") == "it"
        assert i18n.normalize_language("es-MX") == "es"
        assert i18n.normalize_language("de") is None
        assert i18n.normalize_language(None) is None
