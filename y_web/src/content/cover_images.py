"""
Helpers for profile cover/header image selection.
"""

import os
import random

DEFAULT_COVER_IMAGE_PATH = "/static/assets/img/demo/bg/4.png"
_STATIC_PREFIX = "/static/assets/img/demo/bg/"


def _cover_image_directory() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "static",
        "assets",
        "img",
        "demo",
        "bg",
    )


def available_cover_image_urls() -> list:
    try:
        filenames = sorted(
            filename
            for filename in os.listdir(_cover_image_directory())
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        )
    except Exception:
        return [DEFAULT_COVER_IMAGE_PATH]

    if not filenames:
        return [DEFAULT_COVER_IMAGE_PATH]

    return [f"{_STATIC_PREFIX}{filename}" for filename in filenames]


def random_cover_image_url() -> str:
    options = available_cover_image_urls()
    if not options:
        return DEFAULT_COVER_IMAGE_PATH
    return random.SystemRandom().choice(options)


def normalize_cover_image_url(value: str) -> str:
    normalized = str(value or "").strip()
    return normalized or DEFAULT_COVER_IMAGE_PATH
