from pathlib import Path

from y_web.utils.external_processes import detect_env_handler


def test_detect_env_handler_prefers_running_interpreter(monkeypatch):
    expected_python = "/Users/rossetti/miniforge3/envs/Y_Social/bin/python3.11"

    monkeypatch.setattr("y_web.utils.external_processes.sys.executable", expected_python)
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == expected_python)
    monkeypatch.setenv("CONDA_PREFIX", "/opt/anaconda3")
    monkeypatch.delenv("PIPENV_ACTIVE", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    assert detect_env_handler() == expected_python
