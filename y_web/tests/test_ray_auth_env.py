from y_web.src.simulation.subprocess_env import (
    apply_ray_auth_defaults,
    build_subprocess_env,
)


def test_ray_auth_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RAY_AUTH_MODE", raising=False)
    monkeypatch.delenv("RAY_AUTH_TOKEN", raising=False)
    assert build_subprocess_env()["RAY_AUTH_MODE"] == "disabled"


def test_ray_auth_respects_user_choice(monkeypatch):
    monkeypatch.setenv("RAY_AUTH_MODE", "token")
    assert build_subprocess_env()["RAY_AUTH_MODE"] == "token"
    env = apply_ray_auth_defaults({"RAY_AUTH_TOKEN": "x"})
    assert "RAY_AUTH_MODE" not in env
