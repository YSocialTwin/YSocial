import pytest

from y_web.src.external_runtime import registry


class _Admin:
    username = "someone"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_public_state_path", lambda: tmp_path / "vis.json")
    monkeypatch.setattr(registry, "_PUBLIC_STATE", {})
    monkeypatch.setattr(registry, "_PUBLIC_LOADED", False)
    monkeypatch.delenv("YSOCIAL_PLUGIN_VISIBILITY", raising=False)
    return tmp_path


def _private_spec():
    return next(s for s in registry.SUPPORTED_EXTERNAL_REPOS.values() if s.is_private)


def test_private_repo_hidden_until_it_turns_public(isolated, monkeypatch):
    spec = _private_spec()
    monkeypatch.setattr(registry, "_probe_public", lambda repo, timeout: False)
    registry.refresh_public_repos(force=True)
    assert not registry.runtime_visible_to_user(spec, _Admin())

    monkeypatch.setattr(registry, "_probe_public", lambda repo, timeout: True)
    registry.refresh_public_repos(force=True)
    assert registry.runtime_visible_to_user(spec, _Admin())


def test_unknown_answer_keeps_previous_state(isolated, monkeypatch):
    spec = _private_spec()
    monkeypatch.setattr(registry, "_probe_public", lambda repo, timeout: True)
    registry.refresh_public_repos(force=True)
    monkeypatch.setattr(registry, "_probe_public", lambda repo, timeout: None)  # offline
    registry.refresh_public_repos(force=True)
    assert registry.repo_is_public(spec)


def test_public_state_survives_restart(isolated, monkeypatch):
    spec = _private_spec()
    monkeypatch.setattr(registry, "_probe_public", lambda repo, timeout: True)
    registry.refresh_public_repos(force=True)
    monkeypatch.setattr(registry, "_PUBLIC_STATE", {})
    monkeypatch.setattr(registry, "_PUBLIC_LOADED", False)
    assert registry.repo_is_public(spec)


def test_repo_made_private_again_is_hidden(isolated, monkeypatch):
    spec = _private_spec()
    monkeypatch.setattr(registry, "_probe_public", lambda repo, timeout: True)
    registry.refresh_public_repos(force=True)
    monkeypatch.setattr(registry, "_probe_public", lambda repo, timeout: False)
    registry.refresh_public_repos(force=True)
    assert not registry.runtime_visible_to_user(spec, _Admin())
