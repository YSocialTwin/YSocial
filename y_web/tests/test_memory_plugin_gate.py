"""Memory UI/backends are exposed only when the Agent Memory plugin is installed."""

import pytest

from y_web.src.system import memory_plugin

pytestmark = pytest.mark.unit


def _fake_install(tmp_path, present):
    pkg = tmp_path / "external" / memory_plugin.PLUGIN_FOLDER / "src" / "yclient_memory"
    if present:
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")


@pytest.mark.parametrize("present", [True, False])
def test_plugin_detection(tmp_path, monkeypatch, present):
    _fake_install(tmp_path, present)
    monkeypatch.setattr(memory_plugin, "get_writable_path", lambda: str(tmp_path))
    assert memory_plugin.agent_memory_plugin_installed() is present


def test_templates_gate_memory_sections():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "templates" / "admin"
    for name in ("clients.html", "clients_hpc.html", "clients_photo.html"):
        text = (root / name).read_text()
        i = text.index('id="section-memory"')
        assert "{% if memory_configuration_supported %}" in text[max(0, i - 120) : i]
    for name in (
        "client_details.html",
        "client_details_forum.html",
        "client_details_hpc.html",
    ):
        text = (root / name).read_text()
        i = text.index('id="box-memory-config"')
        assert "{% if memory_plugin_installed %}" in text[max(0, i - 120) : i]
