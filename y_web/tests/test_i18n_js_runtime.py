"""JS runtime: catalog endpoint and YI18n.t()/tn() (F1-5)."""

import json
import pathlib
import shutil
import subprocess

import pytest
from flask import Flask
from flask_login import LoginManager

import y_web.i18n as i18n
import y_web.routes.i18n.routes as routes
from y_web.routes.i18n import i18n_bp

JS = (
    pathlib.Path(__file__).resolve().parents[1] / "static" / "assets" / "js" / "i18n.js"
)


@pytest.fixture
def i18n_app(tmp_path, monkeypatch):
    core = tmp_path / "core"
    core.mkdir()
    (core / "en.json").write_text(
        json.dumps(
            {
                "a": "A",
                "b": "B",
                "posts": {"one": "{count} post", "other": "{count} posts"},
            }
        )
    )
    (core / "it.json").write_text(json.dumps({"a": "UNO"}))
    monkeypatch.setattr(routes, "JS_CATALOG_DIR", tmp_path)
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True, SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it")
    )
    LoginManager(flask_app).user_loader(lambda uid: None)
    flask_app.register_blueprint(i18n_bp)
    i18n.init_i18n(flask_app)
    return flask_app


def test_endpoint_merges_language_over_english(i18n_app):
    data = i18n_app.test_client().get("/i18n/core/it.json").get_json()
    assert data["a"] == "UNO" and data["b"] == "B"


def test_endpoint_sets_cache_header(i18n_app):
    r = i18n_app.test_client().get("/i18n/core/en.json")
    assert "max-age" in r.headers["Cache-Control"]


@pytest.mark.parametrize(
    "path", ["/i18n/core/fr.json", "/i18n/nope/en.json", "/i18n/Co..re/en.json"]
)
def test_endpoint_unknown_domain_or_language_is_404(i18n_app, path):
    assert i18n_app.test_client().get(path).status_code == 404


def test_endpoint_returns_plural_objects(i18n_app):
    data = i18n_app.test_client().get("/i18n/core/en.json").get_json()
    assert data["posts"]["one"] == "{count} post"


def _node(script):
    out = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_t_tn_placeholders_and_plurals():
    script = f"""
global.document = {{documentElement: {{getAttribute: () => 'en'}}}};
global.fetch = () => Promise.resolve({{ok: true, json: () => Promise.resolve({{
  'hello': 'Hi {{name}}', 'posts': {{one: '{{count}} post', other: '{{count}} posts'}}}})}});
global.window = {{}};
require({json.dumps(str(JS))});
window.YI18n.ready.then(() => console.log(JSON.stringify([
  window.YI18n.t('hello', {{name: 'Ann'}}),
  window.YI18n.t('missing.key'),
  window.YI18n.tn('posts', 1), window.YI18n.tn('posts', 3),
  window.YI18n.t('posts'),
  window.YI18n.formatNumber(1234.5)
])));
"""
    assert json.loads(_node(script)) == [
        "Hi Ann",
        "missing.key",
        "1 post",
        "3 posts",
        "{count} posts",
        "1,234.5",
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_plural_rules_for_other_language():
    script = f"""
global.document = {{documentElement: {{getAttribute: () => 'ar'}}}};
global.fetch = () => Promise.resolve({{ok: true, json: () => Promise.resolve({{
  'n': {{zero: 'Z', one: 'O', two: 'T', few: 'F', many: 'M', other: 'X'}}}})}});
global.window = {{}};
require({json.dumps(str(JS))});
window.YI18n.ready.then(() => console.log([0,1,2,3,11,100].map(n => window.YI18n.tn('n', n)).join('')));
"""
    assert _node(script) == "ZOTFMX"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_load_failure_falls_back_to_keys():
    script = f"""
global.document = {{documentElement: {{getAttribute: () => 'it'}}}};
global.fetch = () => Promise.reject(new Error('offline'));
global.window = {{}};
require({json.dumps(str(JS))});
window.YI18n.ready.then(() => console.log(window.YI18n.t('x.y')));
"""
    assert _node(script) == "x.y"
