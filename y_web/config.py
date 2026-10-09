"""
Centralized configuration for YSocial.

Usage:
    from y_web.config import get_config
    app.config.from_object(get_config())

Environment variables (see .env.example at repository root):
    YSOCIAL_SECRET_KEY  — Flask secret key (required in production)
    FLASK_ENV           — "development" (default) | "production" | "testing"
    LLM_BACKEND         — LLM backend type (ollama, vllm, or custom host:port)
    LLM_URL             — Custom LLM endpoint URL
    REDIS_URL           — Redis connection URL
    RAY_ADDRESS         — Ray cluster address
"""

from __future__ import annotations

import os
import secrets


class BaseConfig:
    """Shared defaults for all environments."""

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}

    # Flask
    SEND_FILE_MAX_AGE_DEFAULT = 0
    TEMPLATES_AUTO_RELOAD = True
    SESSION_COOKIE_NAME = "YSocial_session"

    # LLM
    LLM_BACKEND: str | None = os.environ.get("LLM_BACKEND")
    LLM_URL: str | None = os.environ.get("LLM_URL")

    # Distributed computing
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RAY_ADDRESS: str = os.environ.get("RAY_ADDRESS", "auto")

    @classmethod
    def validate(cls) -> None:
        """Raise RuntimeError if required settings are missing."""
        errors = []
        if not getattr(cls, "SECRET_KEY", None):
            errors.append("YSOCIAL_SECRET_KEY is not set")
        if errors:
            raise RuntimeError(
                "YSocial configuration is incomplete:\n"
                + "\n".join(f"  - {e}" for e in errors)
                + "\n\nCopy .env.example to .env and fill in the required values."
            )


class DevelopmentConfig(BaseConfig):
    """Local development — permissive, auto-generates secret key when missing."""

    DEBUG = True
    TESTING = False
    SECRET_KEY: str = os.environ.get("YSOCIAL_SECRET_KEY") or secrets.token_hex(32)


class TestingConfig(BaseConfig):
    """Pytest — uses in-memory SQLite, CSRF disabled."""

    DEBUG = False
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(BaseConfig):
    """Production — strict, requires explicit SECRET_KEY.

    Validation is lazy: RuntimeError is raised by get_config() / validate()
    rather than at import time, so the module can be imported safely in tests.
    """

    DEBUG = False
    TESTING = False
    # SECRET_KEY is set at runtime by create_app() via the env var check already
    # present in __init__.py; validate() will surface missing key errors.
    SECRET_KEY: str = os.environ.get("YSOCIAL_SECRET_KEY", "")

    @classmethod
    def validate(cls) -> None:
        if not cls.SECRET_KEY:
            raise RuntimeError(
                "YSOCIAL_SECRET_KEY environment variable is not set in production.\n"
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )


_CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env: str | None = None):
    """Return the config class for the given environment name.

    Falls back to the FLASK_ENV environment variable, then to DevelopmentConfig.
    """
    if env is None:
        env = os.environ.get("FLASK_ENV", "development")
    return _CONFIG_MAP.get(env, DevelopmentConfig)
