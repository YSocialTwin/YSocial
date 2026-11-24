"""Annotations belong to the recommender in force: when the feed is swapped in place, the annotation add-on forgets the old posts."""

from pathlib import Path

import pytest

from y_web.tests._platform_repos import EXTERNAL, microblogging_file


def test_the_feed_announces_that_its_posts_were_swapped_and_the_add_on_forgets_what_it_knew():
    feed = Path(microblogging_file("y_web/static/assets/js/mb-feed.js")).read_text(
        encoding="utf-8"
    )
    assert (
        feed.count("ys:feed-swapped") == 2
    )  # a tab switch and a soft reload, each before the posts are replaced
    assert feed.index("ys:feed-swapped") < feed.index(
        "state.postsContainer.innerHTML = payload.html"
    )
    plugin = (
        EXTERNAL
        / "frontend_adds-on"
        / "modules"
        / "post_annotation"
        / "frontend"
        / "plugin.js"
    )
    if not plugin.is_file():
        pytest.skip("frontend_adds-on is not checked out")
    js = plugin.read_text(encoding="utf-8")
    assert "addEventListener('ys:feed-swapped', resetAnnotationState)" in js
    reset = js[js.index("function resetAnnotationState") : js.index("function init()")]
    assert (
        "annotationState.clear()" in reset
        and "hydratedTargets.clear()" in reset
        and "edu-annot-summary" in reset
    )
