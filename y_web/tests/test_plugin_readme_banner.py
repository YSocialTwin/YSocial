"""The header image of the README of a plugin, shown on its page."""

import pytest

from y_web.src.external_runtime.readme_banner import find_banner

pytestmark = pytest.mark.unit


def _plugin(tmp_path, readme, files=("docs/banner.png",)):
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG\r\n")
    return tmp_path


def test_the_first_local_image_is_the_banner(tmp_path):
    folder = _plugin(
        tmp_path,
        '# P\n\n<p align="center">\n  <img src="docs/banner.png" alt="P: a plugin">\n</p>\n'
        '<a href="x"><img src="https://img.shields.io/badge/a-b-blue.svg" alt="badge"></a>\n',
    )
    path, alt = find_banner(folder)
    assert path == (tmp_path / "docs" / "banner.png").resolve()
    assert alt == "P: a plugin"


def test_badges_and_remote_images_are_skipped(tmp_path):
    folder = _plugin(
        tmp_path,
        '<img src="https://example.org/a.png">\n![badge](https://img.shields.io/x.svg)\n'
        "![logo](./img/logo.png)\n",
        files=("img/logo.png",),
    )
    path, alt = find_banner(folder)
    assert path.name == "logo.png" and alt == "logo"


def test_nothing_that_leaves_the_folder_is_served(tmp_path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"x")
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "README.md").write_text(
        '<img src="../secret.png">\n<img src="/etc/passwd">\n<img src="notes.txt">\n',
        encoding="utf-8",
    )
    (plugin / "notes.txt").write_text("not an image", encoding="utf-8")
    assert find_banner(plugin) is None


def test_no_readme_or_no_image_gives_none(tmp_path):
    assert find_banner(tmp_path) is None
    assert find_banner(tmp_path / "missing") is None
    (tmp_path / "README.md").write_text("# only text\n", encoding="utf-8")
    assert find_banner(tmp_path) is None


class _Resp:
    def __init__(self, text="", content=b""):
        self.text, self.content = text, content

    def raise_for_status(self):
        return None


def test_a_plugin_that_is_not_installed_gets_its_image_from_github(monkeypatch):
    from types import SimpleNamespace

    import requests

    from y_web.src.external_runtime import manager, readme_banner

    manager.clear_remote_cache()
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        if url.endswith("/readme"):
            return _Resp(
                text='<img src="https://x/y.png"><img src="docs/banner.png" alt="Banner">'
            )
        return _Resp(content=b"\x89PNG")

    monkeypatch.setattr(requests, "get", fake_get)
    spec = SimpleNamespace(github_repo="Org/Plugin")
    data, mime, alt = readme_banner.fetch_remote_banner(spec, "token")
    assert (data, mime, alt) == (b"\x89PNG", "image/png", "Banner")
    assert calls[-1].endswith("/repos/Org/Plugin/contents/docs/banner.png")
    readme_banner.fetch_remote_banner(spec, "token")  # cached
    assert len(calls) == 2
    manager.clear_remote_cache()


def test_a_failed_github_request_gives_no_image(monkeypatch):
    from types import SimpleNamespace

    import requests

    from y_web.src.external_runtime import manager, readme_banner

    manager.clear_remote_cache()

    def boom(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", boom)
    assert readme_banner.fetch_remote_banner(SimpleNamespace(github_repo="O/P")) is None
    manager.clear_remote_cache()
