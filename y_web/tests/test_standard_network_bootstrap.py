import os
import sys
from pathlib import Path

import pytest

ROOT = Path("/Users/rossetti/PycharmProjects/YWeb")
EXTERNAL_YCLIENT = ROOT / "external" / "YClient"
if str(EXTERNAL_YCLIENT) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_YCLIENT))

YClientWeb = pytest.importorskip(
    "y_client.clients.client_web", reason="y_client module not available in this environment"
).YClientWeb


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    @property
    def text(self):
        import json

        return json.dumps(self._payload)


def test_add_network_replays_headerless_csv_first_row(monkeypatch, tmp_path):
    network_path = tmp_path / "demo_network.csv"
    network_path.write_text("Alice,Bob\nBob,Carol\n", encoding="utf-8")

    calls = {"get": [], "post": []}

    def fake_get(url, headers=None, params=None, data=None):
        calls["get"].append({"url": url, "params": params, "data": data})
        username = (params or {}).get("username")
        mapping = {"Alice": 1, "Bob": 2, "Carol": 3}
        return _Resp({"id": mapping.get(username)})

    def fake_post(url, headers=None, data=None):
        calls["post"].append({"url": url, "data": data})
        return _Resp({"status": 200})

    monkeypatch.setattr("y_client.clients.client_web.get", fake_get)
    monkeypatch.setattr("y_client.clients.client_web.post", fake_post)

    client = YClientWeb.__new__(YClientWeb)
    client.first_run = True
    client.network_file = network_path.name
    client.base_path = f"{tmp_path}{os.sep}"
    client.config = {"servers": {"api": "http://example.test/"}}
    client._extract_user_id_response = YClientWeb._extract_user_id_response

    client.add_network()

    assert len(calls["get"]) == 3
    assert len(calls["post"]) == 2
    assert "Alice" in str(calls["get"][0]["params"])
    assert "Bob" in str(calls["get"][1]["params"])
    assert '"user_id": 1' in calls["post"][0]["data"]
    assert '"target": 2' in calls["post"][0]["data"]
    assert '"user_id": 2' in calls["post"][1]["data"]
    assert '"target": 3' in calls["post"][1]["data"]
