"""E2: user data lives in YSOCIAL_HOME, never in the installed package; a checkout behaves as before."""

import os
import sys

import pytest

from y_web.src.system import path_utils

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("YSOCIAL_HOME", raising=False)


def test_source_checkout_uses_the_repository_root():
    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(path_utils.__file__)))
    )
    root = os.path.dirname(root)
    assert path_utils.get_writable_path() == root
    assert path_utils.get_writable_path("external") == os.path.join(root, "external")


def test_ysocial_home_overrides_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("YSOCIAL_HOME", str(tmp_path / "data"))
    assert path_utils.get_writable_path() == str((tmp_path / "data").resolve())
    assert os.path.isdir(tmp_path / "data")
    assert path_utils.get_external_path("YServer") == os.path.join(
        str((tmp_path / "data").resolve()), "external", "YServer"
    )


def test_installed_package_uses_the_per_system_default(tmp_path, monkeypatch):
    monkeypatch.setattr(path_utils, "_is_source_checkout", lambda root: False)
    monkeypatch.setattr(path_utils, "_default_home_dir", lambda: tmp_path / "home")
    assert path_utils.get_writable_path() == str(tmp_path / "home")
    assert os.path.isdir(tmp_path / "home")


def test_frozen_bundle_keeps_the_default_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(path_utils, "_default_home_dir", lambda: tmp_path / "h")
    assert path_utils.get_writable_path("x") == os.path.join(str(tmp_path / "h"), "x")


def test_default_folder_per_system(monkeypatch):
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    assert str(path_utils._default_home_dir()).endswith(
        "Library/Application Support/YSocial"
    )
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    assert (
        str(path_utils._default_home_dir())
        .replace("\\", "/")
        .endswith("AppData/Local/YSocial")
    )
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert str(path_utils._default_home_dir()).endswith(".ysocial")


def test_external_repo_prefers_the_bundled_then_the_data_folder(tmp_path, monkeypatch):
    base = tmp_path / "site-packages"
    home = tmp_path / "home"
    (home / "external" / "YServer").mkdir(parents=True)
    monkeypatch.setenv("YSOCIAL_HOME", str(home))
    # installed package: no external/ next to the code -> the data folder copy
    assert path_utils.resolve_external_repo(str(base), "YServer") == str(
        (home / "external" / "YServer").resolve()
    )
    # a bundle that carries the repository wins
    (base / "external" / "YServer").mkdir(parents=True)
    assert path_utils.resolve_external_repo(str(base), "YServer") == str(
        base / "external" / "YServer"
    )


def test_child_processes_inherit_the_data_folder(tmp_path, monkeypatch):
    from y_web.src.simulation.subprocess_env import build_subprocess_env

    monkeypatch.setenv("YSOCIAL_HOME", str(tmp_path))
    assert build_subprocess_env()["YSOCIAL_HOME"] == str(tmp_path.resolve())


def test_sqlite_databases_are_created_in_the_data_folder(tmp_path, monkeypatch):
    import importlib.util

    from flask import Flask

    # the suite's conftest redirects y_web.db_init.sqlite.create_sqlite_db: load the real module
    import y_web.db_init.sqlite as redirected

    spec = importlib.util.spec_from_file_location(
        "real_sqlite_init", redirected.__file__
    )
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    create_sqlite_db = real.create_sqlite_db

    home = tmp_path.resolve()
    monkeypatch.setenv("YSOCIAL_HOME", str(home))
    app = Flask("x")
    create_sqlite_db(app)
    assert (home / "y_web" / "db" / "dashboard.db").is_file()
    assert (home / "y_web" / "db" / "dummy.db").is_file()
    assert str(home) in app.config["SQLALCHEMY_DATABASE_URI"]
