import io
import tarfile
import tomllib
from pathlib import Path

import pytest

from y_web.src.system import avatars_store as av
from y_web.src.system import model_cache

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _make_archive(n):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for i in range(n):
            data = b"x"
            info = tarfile.TarInfo(f"sub/{i}.png")
            info.size = 1
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_get_avatars_dir_falls_back_to_home(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "bundled_avatars_dir", lambda: str(tmp_path / "none"))
    monkeypatch.setenv("YSOCIAL_HOME", str(tmp_path / "home"))
    assert av.get_avatars_dir() == str(tmp_path / "home" / "avatars")
    assert not av.avatars_ready()


def test_download_extracts_flat_images(tmp_path):
    archive = tmp_path / "a.tar.gz"
    archive.write_bytes(_make_archive(3))
    dest = tmp_path / "out"
    av._download(archive.as_uri(), str(dest))
    assert sorted(p.name for p in dest.iterdir()) == ["0.png", "1.png", "2.png"]


def test_ensure_avatars_respects_skip_env(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "bundled_avatars_dir", lambda: str(tmp_path / "none"))
    monkeypatch.setenv("YSOCIAL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("YSOCIAL_SKIP_AVATARS_DOWNLOAD", "1")
    assert av.ensure_avatars() is False


def test_avatar_route_serves_placeholder_when_missing(tmp_path, monkeypatch):
    from flask import Flask

    monkeypatch.setattr(av, "bundled_avatars_dir", lambda: str(tmp_path / "none"))
    monkeypatch.setenv("YSOCIAL_HOME", str(tmp_path / "home"))
    app = Flask(__name__)
    av.register_avatar_route(app)
    resp = app.test_client().get("/static/assets/img/users/42.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/svg+xml"


def test_detoxify_missing_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(model_cache, "detoxify_installed", lambda: False)
    saved = {}
    monkeypatch.setattr(model_cache, "save_model_cache_path", lambda d: Path(d))
    monkeypatch.setattr(
        model_cache, "_persist_download_state", lambda p: saved.update(p) or p
    )
    state = model_cache.start_detoxify_download(tmp_path)
    assert state["status"] == "error"
    assert "ysocial[toxicity]" in state["message"]


def test_pyproject_extras_and_python():
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert cfg["project"]["requires-python"] == ">=3.12"
    assert "toxicity" in cfg["tool"]["setuptools"]["dynamic"]["optional-dependencies"]
    assert "detoxify" not in (ROOT / "requirements/base.in").read_text()
    assert "detoxify" in (ROOT / "requirements/toxicity.in").read_text()
    excl = cfg["tool"]["setuptools"]["exclude-package-data"]["y_web"]
    assert "static/assets/img/users/*" in excl
