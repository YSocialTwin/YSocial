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
    assert manager.resolve_python_executable() == str(fake.resolve())


def test_missing_managed_python_is_ignored(monkeypatch):
    monkeypatch.setenv("YSOCIAL_PYTHON", "/nonexistent/python")
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.delenv("MAMBA_PREFIX", raising=False)
    assert manager.resolve_python_executable() == str(Path(sys.executable).resolve())


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
