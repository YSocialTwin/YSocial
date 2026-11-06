"""LLM API keys: "Fetch Models" authenticates, and the key is stored and used (OpenAI, DeepSeek, ...)."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from y_web import db
from y_web.src.llm import vllm_manager
from y_web.src.llm.url_summarizer import UrlSummarizer
from y_web.src.llm.vllm_manager import (
    LLMAuthenticationError,
    get_llm_models,
    llm_auth_headers,
)
from y_web.src.models import Admin_users

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise vllm_manager.requests.exceptions.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


class FakeServer:
    """A provider that answers the model list only to the right Bearer token."""

    def __init__(self, token="sk-test"):
        self.token = token
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        if (headers or {}).get("Authorization") != f"Bearer {self.token}":
            return FakeResponse(401, {"error": "unauthorized"})
        return FakeResponse(200, {"data": [{"id": "deepseek-chat"}, {"id": "m2"}]})


@pytest.fixture
def server(monkeypatch):
    fake = FakeServer()
    monkeypatch.setattr(vllm_manager.requests, "get", fake.get)
    vllm_manager._MODELS_DOWN_CACHE.clear()
    return fake


@pytest.mark.parametrize("value", [None, "", "  ", "NULL", "null", "EMPTY", "None"])
def test_no_key_sends_no_authorization_header(value):
    assert llm_auth_headers(value) == {}


def test_key_becomes_a_bearer_header():
    assert llm_auth_headers(" sk-abc ") == {"Authorization": "Bearer sk-abc"}


def test_get_llm_models_sends_the_key(server):
    models = get_llm_models("https://api.deepseek.com", api_key="sk-test")
    assert models == ["deepseek-chat", "m2"]
    assert server.calls[0][1] == {"Authorization": "Bearer sk-test"}


def test_get_llm_models_without_key_sends_no_header_and_returns_empty_on_401(server):
    assert get_llm_models("https://api.deepseek.com") == []
    assert all("Authorization" not in headers for _, headers in server.calls)


def test_auth_failure_can_be_told_apart_from_an_unreachable_server(server):
    with pytest.raises(LLMAuthenticationError) as error:
        get_llm_models(
            "https://api.deepseek.com", api_key="wrong", raise_on_auth_error=True
        )
    assert error.value.status_code == 401


def call_fetch_models(app, query="llm_url=https://api.deepseek.com", key=None):
    """The view without its login decorator, in a request like the browser's."""
    from y_web.routes.admin import dashboard

    headers = {"X-LLM-API-Key": key} if key else {}
    with app.test_request_context(f"/admin/api/fetch_models?{query}", headers=headers):
        result = dashboard.fetch_models.__wrapped__()
    response, status = result if isinstance(result, tuple) else (result, 200)
    return status, response.get_json()


def test_fetch_models_route_uses_the_key_from_the_header(app, server):
    status, body = call_fetch_models(app, key="sk-test")
    assert status == 200
    assert body["models"] == ["deepseek-chat", "m2"]
    # the key travels in a header, never in the URL
    assert all("sk-test" not in url for url, _ in server.calls)


def test_fetch_models_route_reports_a_wrong_key(app, server):
    status, body = call_fetch_models(app, key="wrong")
    assert status == 401
    assert body["success"] is False and body["auth_error"] is True
    assert "API key" in body["error"] == body["message"] or "API key" in body["message"]


def test_fetch_models_route_without_key_says_it_is_refused(app, server):
    status, body = call_fetch_models(app)
    assert status == 401
    assert body["auth_error"] is True


def admin_user_id(app, key=None):
    with app.app_context():
        user = db.session.scalars(
            select(Admin_users).filter_by(username="admin")
        ).first()
        if key is not None:
            user.llm_api_key = key
            db.session.commit()
        return user.id


def test_fetch_models_route_uses_the_stored_key_of_the_user(app, server, monkeypatch):
    from y_web.routes.admin import dashboard

    user_id = admin_user_id(app, key="sk-test")
    monkeypatch.setattr(dashboard, "current_user", SimpleNamespace(username="admin"))
    status, body = call_fetch_models(
        app, query=f"llm_url=https://api.deepseek.com&user_id={user_id}"
    )
    assert status == 200 and body["success"] is True


def test_a_user_cannot_borrow_the_key_of_another_user(app, server, monkeypatch):
    from y_web.routes.admin import dashboard

    user_id = admin_user_id(app, key="sk-test")
    with app.app_context():
        other = Admin_users(
            username="plain",
            email="plain@test.com",
            password="x",
            role="user",
            last_seen="2023-01-01",
        )
        db.session.add(other)
        db.session.commit()
    monkeypatch.setattr(dashboard, "current_user", SimpleNamespace(username="plain"))
    status, _ = call_fetch_models(
        app, query=f"llm_url=https://api.deepseek.com&user_id={user_id}"
    )
    assert status == 401


def test_update_user_llm_stores_keeps_and_clears_the_key(app, monkeypatch):
    users = importlib.import_module("y_web.routes.admin.sub.users")

    user_id = admin_user_id(app)
    monkeypatch.setattr(users, "current_user", SimpleNamespace(username="admin"))
    monkeypatch.setattr(users, "user_details", lambda uid: "page")

    def post(**fields):
        data = {"user_id": str(user_id), "llm": "deepseek-chat"}
        data.update(fields)
        with app.test_request_context(
            "/admin/update_user_llm", method="POST", data=data
        ):
            users.update_user_llm.__wrapped__()
        with app.app_context():
            return db.session.get(Admin_users, user_id).llm_api_key

    url = "https://api.deepseek.com"
    assert post(custom_llm_url=url, llm_api_key="sk-1") == "sk-1"
    # an empty field keeps the stored key
    assert post(custom_llm_url=url, llm_api_key="") == "sk-1"
    assert post(custom_llm_url=url, clear_llm_api_key="1") == ""


def test_the_key_field_never_shows_the_stored_value():
    template = (ROOT / "y_web/templates/admin/user_details.html").read_text()
    field = template[template.index('name="llm_api_key"') - 120 :][:400]
    assert 'type="password"' in field
    assert "value=" not in field


def test_url_summarizer_sends_the_key():
    config = UrlSummarizer.build_config(
        model="m", base_url="https://api.deepseek.com", api_key="sk-test"
    )
    assert UrlSummarizer(config)._headers["Authorization"] == "Bearer sk-test"
    config = UrlSummarizer.build_config(model="m", base_url="http://127.0.0.1:11434/v1")
    assert "Authorization" not in UrlSummarizer(config)._headers


def test_migration_adds_the_column_once(tmp_path):
    import sqlite3

    from y_web.migrations.add_admin_llm_api_key_column import migrate_sqlite

    path = tmp_path / "admin.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE admin_users (id INTEGER PRIMARY KEY, llm_url TEXT)"
    )
    connection.execute("INSERT INTO admin_users (llm_url) VALUES ('http://x')")
    connection.commit()
    connection.close()

    assert migrate_sqlite(str(path)) is True
    assert migrate_sqlite(str(path)) is True  # idempotent
    connection = sqlite3.connect(path)
    columns = [row[1] for row in connection.execute("PRAGMA table_info(admin_users)")]
    assert columns.count("llm_api_key") == 1
    assert connection.execute("SELECT llm_api_key FROM admin_users").fetchone() == ("",)
    connection.close()
