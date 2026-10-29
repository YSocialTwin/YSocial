"""Characterization of the Ray-platform launch contracts (photo sharing, microblogging).

These tests pin today's server and client command lines, the prompts file names, the stop actor
names and the photo-sharing client normalizer, so that introducing the platform spec table
(``y_web/src/hpc/platforms.py``) provably changes none of them (plan, Phase 2).
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

PLATFORMS = ("microblogging", "photo_sharing")


def _exp(platform):
    return SimpleNamespace(
        idexp=6,
        db_name="experiments_uid1",
        platform_type=platform,
        server="127.0.0.1",
        port=5004,
        server_pid=None,
        prompt_language="en",
    )


@pytest.fixture
def layout(tmp_path):
    """A writable root (experiment folder) and a resource root holding the runtime scripts."""
    writable = tmp_path / "writable"
    base = tmp_path / "base"
    exp_folder = writable / "y_web" / "experiments" / "uid1"
    exp_folder.mkdir(parents=True)
    for repo, scripts in {
        "YSimulator": ("run_server.py", "run_client.py"),
        "YServer": (),
        "YPhotoSharing": ("run_server.py", "run_client.py"),
    }.items():
        d = base / "external" / repo
        d.mkdir(parents=True)
        for s in scripts:
            (d / s).write_text("")
    return SimpleNamespace(writable=writable, base=base, exp_folder=exp_folder)


def _patch_common(monkeypatch, module, layout):
    monkeypatch.setattr(module, "get_base_path", lambda: str(layout.base))
    monkeypatch.setattr(module, "get_writable_path", lambda: str(layout.writable))
    monkeypatch.setattr(module, "build_subprocess_env", lambda: {})
    monkeypatch.setattr(
        "y_web.src.simulation.server.detect_env_handler", lambda: "python"
    )
    monkeypatch.setattr(module.db.session, "commit", lambda: None)


def _capture_popen(monkeypatch, module):
    calls = []
    process = MagicMock()
    process.pid = 90001

    def fake_popen(cmd, **kwargs):
        calls.append(SimpleNamespace(cmd=list(cmd), kwargs=kwargs))
        return process

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    return calls


def _start_server(monkeypatch, layout, platform, frozen=False, postgres=False):
    from y_web.src.hpc import server as hs

    _patch_common(monkeypatch, hs, layout)
    monkeypatch.setattr(
        hs,
        "current_app",
        SimpleNamespace(
            config={
                "SQLALCHEMY_DATABASE_URI": (
                    "postgresql://u:p@h/db" if postgres else "sqlite:///tmp/main.db"
                )
            }
        ),
    )
    calls = _capture_popen(monkeypatch, hs)
    if frozen:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
    exp = _exp(platform)
    hs.start_hpc_server(exp)
    assert exp.server_pid == 90001 and exp.running == 1 and exp.exp_status == "active"
    return calls[0], exp


# -- server command lines ------------------------------------------------------------------------
def test_microblogging_server_command(monkeypatch, layout):
    call, _ = _start_server(monkeypatch, layout, "microblogging")
    script = str(layout.base / "external" / "YSimulator" / "run_server.py")
    assert call.cmd == ["python", script, "--config", str(layout.exp_folder)]
    assert call.kwargs["start_new_session"] is True


def test_photo_server_command(monkeypatch, layout):
    call, _ = _start_server(monkeypatch, layout, "photo_sharing")
    script = str(layout.base / "external" / "YPhotoSharing" / "run_server.py")
    assert call.cmd == ["python", script, "--config", str(layout.exp_folder)]


def test_microblogging_server_on_postgres_uses_gunicorn(monkeypatch, layout):
    call, _ = _start_server(monkeypatch, layout, "microblogging", postgres=True)
    assert call.cmd[0].endswith("gunicorn")
    assert call.cmd[1:] == [
        "--config",
        str(layout.base / "external" / "YServer" / "gunicorn_config.py"),
        "--bind",
        "127.0.0.1:5004",
        "--chdir",
        str(layout.base / "external" / "YServer"),
        "wsgi:app",
    ]


def test_photo_server_on_postgres_still_uses_the_plain_runner(monkeypatch, layout):
    call, _ = _start_server(monkeypatch, layout, "photo_sharing", postgres=True)
    script = str(layout.base / "external" / "YPhotoSharing" / "run_server.py")
    assert call.cmd == ["python", script, "--config", str(layout.exp_folder)]


def test_frozen_microblogging_server_command(monkeypatch, layout):
    call, _ = _start_server(monkeypatch, layout, "microblogging", frozen=True)
    assert call.cmd == [
        sys.executable,
        "--run-server-subprocess",
        "--config",
        str(layout.exp_folder),
        "--platform",
        "microblogging",
    ]


def test_frozen_photo_server_command(monkeypatch, layout):
    call, _ = _start_server(monkeypatch, layout, "photo_sharing", frozen=True)
    script = str(layout.base / "external" / "YPhotoSharing" / "run_server.py")
    assert call.cmd == [sys.executable, script, "--config", str(layout.exp_folder)]


def test_unknown_server_platform_names_the_platform(monkeypatch, layout):
    from y_web.src.hpc import server as hs

    _patch_common(monkeypatch, hs, layout)
    monkeypatch.setattr(
        hs,
        "current_app",
        SimpleNamespace(config={"SQLALCHEMY_DATABASE_URI": "sqlite://"}),
    )
    with pytest.raises(NotImplementedError, match="no_such_platform"):
        hs.start_hpc_server(_exp("no_such_platform"))


def test_missing_server_script_names_the_runtime_repository(monkeypatch, layout):
    from y_web.src.hpc import server as hs

    _patch_common(monkeypatch, hs, layout)
    monkeypatch.setattr(
        hs,
        "current_app",
        SimpleNamespace(config={"SQLALCHEMY_DATABASE_URI": "sqlite://"}),
    )
    (layout.base / "external" / "YPhotoSharing" / "run_server.py").unlink()
    with pytest.raises(FileNotFoundError, match="external/YPhotoSharing"):
        hs.start_hpc_server(_exp("photo_sharing"))
    (layout.base / "external" / "YSimulator" / "run_server.py").unlink()
    with pytest.raises(FileNotFoundError, match="external/YSimulator"):
        hs.start_hpc_server(_exp("microblogging"))


# -- client command lines -------------------------------------------------------------------------
def _start_client(monkeypatch, layout, platform, frozen=False):
    from y_web.src.hpc import client as hc

    _patch_common(monkeypatch, hc, layout)
    monkeypatch.setattr(hc, "_wait_for_hpc_server_ready", lambda *a, **k: None)
    monkeypatch.setattr(hc.time, "sleep", lambda *_: None)
    monkeypatch.setattr("y_web.src.system.prompt_packs.launch_env", lambda *a, **k: {})
    scalars = MagicMock()
    scalars.first.return_value = None
    monkeypatch.setattr(hc.db.session, "scalars", lambda *a, **k: scalars)
    monkeypatch.setattr(hc.db.session, "add", lambda *a, **k: None)
    calls = _capture_popen(monkeypatch, hc)
    if frozen:
        monkeypatch.setattr(sys, "frozen", True, raising=False)

    folder = layout.exp_folder
    (folder / "ray_config.temp").write_text("")
    (folder / "server_config.json").write_text(
        json.dumps({"namespace": "ns1", "server_name": "srv1"})
    )
    (folder / "client_cl-pop.json").write_text(
        json.dumps({"logging": {}, "simulation": {}})
    )
    (folder / "pop.json").write_text("{}")
    prompts = "prompts_ygram.json" if platform == "photo_sharing" else "prompts.json"
    (folder / prompts).write_text("{}")

    exp = _exp(platform)
    cli = SimpleNamespace(id=3, name="cl", days=2, pid=None, prompt_language=None)
    population = SimpleNamespace(name="pop")
    hc.start_hpc_client(exp, cli, population)
    assert cli.pid == 90001
    return calls[0]


def test_microblogging_client_command(monkeypatch, layout):
    call = _start_client(monkeypatch, layout, "microblogging")
    f = layout.exp_folder
    script = str(layout.base / "external" / "YSimulator" / "run_client.py")
    assert call.cmd == [
        "python",
        script,
        "--config",
        str(f / "client_cl-pop.json"),
        "--agents",
        str(f / "pop.json"),
        "--prompts",
        str(f / "prompts.json"),
    ]


def test_photo_client_command_and_normalized_config(monkeypatch, layout):
    call = _start_client(monkeypatch, layout, "photo_sharing")
    f = layout.exp_folder
    script = str(layout.base / "external" / "YPhotoSharing" / "run_client.py")
    assert call.cmd == ["python", script, "--config", str(f / "client_cl-pop.json")]
    cfg = json.loads((f / "client_cl-pop.json").read_text())
    runtime_id = "uid1:cl"
    assert cfg["client_id"] == runtime_id
    assert cfg["namespace"] == "ns1" and cfg["server_name"] == "srv1"
    assert cfg["address"] == "auto"
    assert cfg["agents_file"] == "pop.json" and cfg["users_file"] == "pop.json"
    assert cfg["logging"] == {"log_dir": str(f / "logs"), "instance_name": runtime_id}


def test_frozen_client_commands(monkeypatch, layout):
    call = _start_client(monkeypatch, layout, "microblogging", frozen=True)
    f = layout.exp_folder
    assert call.cmd == [
        sys.executable,
        "--run-hpc-client-subprocess",
        "--config",
        str(f / "client_cl-pop.json"),
        "--agents",
        str(f / "pop.json"),
        "--prompts",
        str(f / "prompts.json"),
    ]


def test_frozen_photo_client_command(monkeypatch, layout):
    call = _start_client(monkeypatch, layout, "photo_sharing", frozen=True)
    script = str(layout.base / "external" / "YPhotoSharing" / "run_client.py")
    assert call.cmd == [
        sys.executable,
        script,
        "--config",
        str(layout.exp_folder / "client_cl-pop.json"),
    ]


def test_unknown_client_platform_names_the_platform(monkeypatch, layout):
    with pytest.raises(NotImplementedError, match="no_such_platform"):
        _start_client(monkeypatch, layout, "no_such_platform")


# -- names and files tied to the platform -----------------------------------------------------------
@pytest.mark.parametrize(
    "platform,expected",
    [
        ("photo_sharing", "prompts_ygram.json"),
        ("microblogging", "prompts.json"),
        ("forum", "prompts.json"),
    ],
)
def test_hpc_prompts_filename(platform, expected):
    from y_web.routes.admin.sub.experiments._crud import _hpc_prompts_filename

    assert _hpc_prompts_filename(SimpleNamespace(platform_type=platform)) == expected
