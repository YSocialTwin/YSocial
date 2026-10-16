"""YSOCIAL_LANGUAGES withdraws a language without a deploy (phase 6)."""
import importlib

import y_web.config as config


def _languages(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("YSOCIAL_LANGUAGES", raising=False)
    else:
        monkeypatch.setenv("YSOCIAL_LANGUAGES", value)
    return importlib.reload(config).BaseConfig.SUPPORTED_LANGUAGES


def test_default_and_kill_switch(monkeypatch):
    try:
        assert _languages(monkeypatch, None) == ("en", "it")
        assert _languages(monkeypatch, "en") == ("en",)
        assert _languages(monkeypatch, "it") == ("en", "it")
    finally:
        monkeypatch.delenv("YSOCIAL_LANGUAGES", raising=False)
        importlib.reload(config)
