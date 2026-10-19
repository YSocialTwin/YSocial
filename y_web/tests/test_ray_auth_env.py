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


def test_ray_safe_cmd_removes_spaces(tmp_path, monkeypatch):
    import os

    import y_web.src.simulation.subprocess_env as se

    home = tmp_path / "Application Support" / "YSocial"
    (home / "runtime" / "venv" / "bin").mkdir(parents=True)
    monkeypatch.setattr(se, "get_writable_path", lambda: str(home))
    py = str(home / "runtime" / "venv" / "bin" / "python")
    cmd = se.ray_safe_cmd([py, str(home / "external/x.py"), "--n", "3"])
    assert all(" " not in a for a in cmd)
    assert cmd[2:] == ["--n", "3"]
    assert os.path.realpath(cmd[0]) == os.path.realpath(py)


def test_ray_safe_cmd_noop_without_spaces(tmp_path, monkeypatch):
    import y_web.src.simulation.subprocess_env as se

    monkeypatch.setattr(se, "get_writable_path", lambda: str(tmp_path))
    assert se.ray_safe_cmd(["a", str(tmp_path / "b")]) == ["a", str(tmp_path / "b")]
