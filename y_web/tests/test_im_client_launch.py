"""Starting an IM client through the HPC path: normalizer and command line (plan, Phase 5)."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
IM_REPO = ROOT / "external" / "YInstantMessaging"


def _client_json():
    return {
        "client_name": "cl",
        "seed": 7,
        "llm": {"backend": "echo"},
        "simulation": {"num_days": 1},
        "telegram": {"topics": {"catalog_file": "topic_catalog.json"}},
        "logging": {"enable_console_log": False},
    }


def _folder(tmp_path):
    folder = tmp_path / "y_web" / "experiments" / "uid1"
    folder.mkdir(parents=True)
    (folder / "server_config.json").write_text(
        json.dumps(
            {"server_name": "orchestrator_server", "namespace": "yinstantmessaging"}
        )
    )
    (folder / "client_cl-pop.json").write_text(json.dumps(_client_json()))
    (folder / "pop.json").write_text('{"agents": []}')
    (folder / "topic_catalog.json").write_text('{"topics": []}')
    return folder


def test_normalizer_sets_only_runtime_keys_and_is_idempotent(tmp_path):
    from y_web.src.hpc.client import _normalize_im_client_config

    folder = _folder(tmp_path)
    path = folder / "client_cl-pop.json"
    _normalize_im_client_config(str(folder), "cl", "pop", str(path))
    first = path.read_text()
    cfg = json.loads(first)
    assert cfg["client_id"] == "uid1:cl"
    assert (
        cfg["namespace"] == "yinstantmessaging"
        and cfg["server_name"] == "orchestrator_server"
    )
    assert cfg["address"] == "auto" and cfg["agents_file"] == "pop.json"
    assert cfg["logging"] == {
        "enable_console_log": False,
        "log_dir": str(folder / "logs"),
        "instance_name": "uid1:cl",
    }
    assert cfg["llm"] == {"backend": "echo"} and cfg["seed"] == 7
    for _ in range(3):
        _normalize_im_client_config(str(folder), "cl", "pop", str(path))
    assert path.read_text() == first
    assert "llm_api_key" not in first


def test_normalizer_does_not_change_the_im_config_hash(tmp_path):
    if not (IM_REPO / "yinstantmessaging").is_dir():
        pytest.skip("YInstantMessaging is not installed")
    sys.path.insert(0, str(IM_REPO))
    try:
        from yinstantmessaging.common.config import (
            client_input_files,
            compute_config_hash,
        )
    finally:
        sys.path.remove(str(IM_REPO))
    from y_web.src.hpc.client import _normalize_im_client_config

    folder = _folder(tmp_path)
    path = folder / "client_cl-pop.json"

    def digest():
        cfg = json.loads(path.read_text())
        return compute_config_hash(folder, client_input_files(cfg) + (path.name,))

    # the client file is hashed here on purpose: even then only excluded keys may change
    before_cfg = _client_json()
    before_cfg.update(agents_file="pop.json")
    path.write_text(json.dumps(before_cfg))
    before = digest()
    _normalize_im_client_config(str(folder), "cl", "pop", str(path))
    assert digest() == before


def test_start_im_client_command_and_no_ysimulator_steps(monkeypatch, tmp_path):
    from y_web.src.hpc import client as hc

    folder = _folder(tmp_path)
    (folder / "ray_config.temp").write_text("")
    repo = tmp_path / "base" / "external" / "YInstantMessaging"
    repo.mkdir(parents=True)
    (repo / "run_client.py").write_text("")

    monkeypatch.setattr(hc, "get_base_path", lambda: str(tmp_path / "base"))
    monkeypatch.setattr(hc, "get_writable_path", lambda: str(tmp_path))
    monkeypatch.setattr(hc, "build_subprocess_env", lambda: {})
    monkeypatch.setattr(
        "y_web.src.simulation.server.detect_env_handler", lambda: "python"
    )
    monkeypatch.setattr(hc, "_wait_for_hpc_server_ready", lambda *a, **k: None)
    monkeypatch.setattr(hc.time, "sleep", lambda *_: None)
    monkeypatch.setattr("y_web.src.system.prompt_packs.launch_env", lambda *a, **k: {})
    monkeypatch.setattr(hc.db.session, "commit", lambda: None)
    scalars = MagicMock()
    scalars.first.return_value = None
    monkeypatch.setattr(hc.db.session, "scalars", lambda *a, **k: scalars)
    monkeypatch.setattr(hc.db.session, "add", lambda *a, **k: None)
    for name in (
        "_sync_stress_reward_into_hpc_client_config",
        "_sync_hpc_network_bootstrap",
    ):
        monkeypatch.setattr(
            hc, name, lambda *a, **k: pytest.fail(f"{name} must not run for IM")
        )
    validated = []
    monkeypatch.setattr(
        "y_web.src.im.validation.validate_im_folder",
        lambda folder_, repo_, client_config=None: validated.append(
            (folder_, client_config)
        ),
    )
    calls = []
    proc = MagicMock()
    proc.pid = 777
    monkeypatch.setattr(
        hc.subprocess, "Popen", lambda cmd, **kw: calls.append(list(cmd)) or proc
    )

    exp = SimpleNamespace(
        idexp=6,
        db_name="experiments/uid1/database_server.db",
        platform_type="instant_messaging",
        server="127.0.0.1",
        port=5004,
        prompt_language="en",
    )
    cli = SimpleNamespace(id=3, name="cl", days=1, pid=None, prompt_language=None)
    hc.start_hpc_client(exp, cli, SimpleNamespace(name="pop"))

    assert calls == [
        [
            "python",
            str(repo / "run_client.py"),
            "--config",
            str(folder / "client_cl-pop.json"),
        ]
    ]
    assert cli.pid == 777
    assert validated == [(str(folder), "client_cl-pop.json")]
    assert (
        json.loads((folder / "client_cl-pop.json").read_text())["client_id"]
        == "uid1:cl"
    )
