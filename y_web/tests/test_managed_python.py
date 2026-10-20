import sys
from pathlib import Path

import pytest

from y_web.src.external_runtime import manager

pytestmark = pytest.mark.unit


def test_managed_python_env_wins(tmp_path, monkeypatch):
    fake = tmp_path / "python"
    fake.write_text("")
    monkeypatch.setenv("YSOCIAL_PYTHON", str(fake))
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    assert manager.resolve_python_executable() == str(fake)


def test_missing_managed_python_is_ignored(monkeypatch):
    monkeypatch.setenv("YSOCIAL_PYTHON", "/nonexistent/python")
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.delenv("MAMBA_PREFIX", raising=False)
    assert manager.resolve_python_executable() == __import__("os").path.abspath(
        sys.executable
    )


def test_ensure_pip_runs_ensurepip_when_missing(monkeypatch):
    calls = []

    class R:
        returncode = 1
        stdout = ""
        stderr = ""

    monkeypatch.setattr(manager.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(
        manager, "_run_command", lambda cmd, **k: calls.append(cmd) or "ok"
    )
    assert manager._ensure_pip("/x/python") == "ok"
    assert calls[0][1:4] == ["-m", "ensurepip", "--upgrade"]


def test_ensure_pip_noop_when_present(monkeypatch):
    class R:
        returncode = 0

    monkeypatch.setattr(manager.subprocess, "run", lambda *a, **k: R())
    assert manager._ensure_pip("/x/python") == ""


def test_venv_symlink_is_not_resolved(tmp_path, monkeypatch):
    base = tmp_path / "base" / "python3.12"
    base.parent.mkdir()
    base.write_text("")
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(base)
    monkeypatch.setenv("YSOCIAL_PYTHON", str(venv_python))
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    assert manager.resolve_python_executable() == str(venv_python)


def test_core_constraints_file_found_via_env(tmp_path, monkeypatch):
    c = tmp_path / "constraints.txt"
    c.write_text("flask-login==0.6.3\n")
    monkeypatch.setenv("YSOCIAL_CONSTRAINTS", str(c))
    assert manager.core_constraints_file() == c


def test_core_constraints_file_from_home(tmp_path, monkeypatch):
    monkeypatch.delenv("YSOCIAL_CONSTRAINTS", raising=False)
    monkeypatch.setenv("YSOCIAL_HOME", str(tmp_path))
    assert manager.core_constraints_file() is None
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "constraints.txt").write_text("x==1\n")
    assert manager.core_constraints_file() == tmp_path / "runtime" / "constraints.txt"
