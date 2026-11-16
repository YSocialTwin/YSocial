"""A platform without threads (the microblogging feed) still gets a display time and a title/body split."""

import re
from pathlib import Path

import pytest

from y_web.platforms import registry
from y_web.src.commons import flat_threads

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_the_default_threads_answer_what_the_feed_asks():
    assert flat_threads.split_title("") == (None, "")
    assert flat_threads.split_title("hello there") == (None, "hello there")
    assert flat_threads.split_title("TITLE: A title\nThe body") == (
        "A title",
        "The body",
    )
    assert flat_threads.display_time(
        None, 3, 7
    )  # the clock of the experiment, whatever it shows


def test_a_provider_without_threads_is_served_by_the_default():
    without = [p for p in registry.all_providers() if p.threads is None]
    if not without:
        pytest.skip(
            "no installed platform lacks threads (the platform repositories are not installed)"
        )
    for provider in without:
        threads = provider.threads or flat_threads
        assert callable(threads.display_time) and callable(threads.split_title)


def test_no_feed_code_uses_the_threads_of_a_provider_unguarded():
    """``provider.threads`` is ``None`` for most platforms: the core either falls back or checks before it asks."""
    for path in (ROOT / "y_web").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if "/tests/" in relative or "/sdk/" in relative:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(\w+)\s*=\s*([\w.()]*\.)?threads\b[^\n]*", text):
            line = match.group(0)
            assert (
                " or flat_threads" in line
                or "getattr(" in line
                or "provider" not in line
            ), f"{relative}: {line}"
