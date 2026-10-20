"""Release/branch archives are downloaded without an Accept that codeload rejects (415)."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _manager():
    spec = importlib.util.spec_from_file_location(
        "ys_runtime_manager", ROOT / "y_web/src/external_runtime/manager.py"
    )
    src = (ROOT / "y_web/src/external_runtime/manager.py").read_text(encoding="utf-8")
    return src, spec


def test_download_headers_do_not_force_octet_stream():
    src, _ = _manager()
    start = src.index("def _github_download_headers")
    block = src[start : src.index("def _git_auth_env")]
    assert '"Accept": "*/*"' in block
    assert 'Accept": "application/octet-stream"' not in block


def test_archive_download_retries_once_on_415(monkeypatch):
    src, _ = _manager()
    start = src.index("def _get_archive")
    fn_src = src[start : src.index("def _download_release_archive")]
    calls = []

    class Resp:
        def __init__(self, code):
            self.status_code = code

    def fake_get(url, headers, timeout, allow_redirects):
        calls.append(dict(headers))
        return Resp(415 if len(calls) == 1 else 200)

    ns = {
        "requests": types.SimpleNamespace(get=fake_get),
        "_github_download_headers": lambda token=None: {
            "Accept": "*/*",
            "User-Agent": "x",
        },
    }
    exec(fn_src, ns)
    assert ns["_get_archive"]("https://x", None, 5).status_code == 200
    assert calls[0]["Accept"] == "*/*" and "Accept" not in calls[1]
