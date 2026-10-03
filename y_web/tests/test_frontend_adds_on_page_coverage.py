"""
Regression tests for extending Frontend Adds-on frontend-plugin (post_annotation)
support beyond the feed page, and for correctly distinguishing a "post"
target from a "comment" target when the annotated element is a comment.

Background: `shared/plugin_loader.html` is the single template include that
injects `window.YS_FRONTEND_ADDS_ON_MODULES` + `plugin-core.js`; it only renders
anything when the route also passes `frontend_adds_on_modules=
active_modules_context(exp_id)` into `render_template()`. Both pieces
(the include AND the route kwarg) are required for a page to support
annotation at all. `/profile` and `/hashtag_posts` were missing both.

Separately, `post_annotation`'s frontend `findAnchors()` must label a
`.media.is-comment` element as `targetType: "comment"` (keyed by its OWN
id) unless it is genuinely the root post of a `/thread` page -- the
backend gates real behavior on this label (`annotate_posts` vs
`annotate_comments` config, in
`external/frontend_adds-on/modules/post_annotation/backend/__init__.py`), so
mislabeling every comment as "post" (the previous behavior) silently
misapplies that per-type config and, on pages without a nested
`.card.is-post` per comment (the feed/profile/hashtag comment-preview
list), even points the annotation at the wrong target id entirely (the
parent post's, not the comment's own).

These are static-analysis tests (in the spirit of this repo's existing
`test_microblog_follow_links.py`, but resolving paths from `__file__` --
per `conftest.py`'s `_REPO_ROOT = Path(__file__).resolve().parents[2]`
convention -- rather than hardcoding this machine's absolute path, so
they run the same wherever the repo is checked out). Behavioral
verification of the JS logic itself was done separately via a jsdom
harness (no permanent JS test infra exists in this repo, per prior
Frontend Adds-on commits' own stated rationale).
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

COMMON_PY = _REPO_ROOT / "y_web" / "routes" / "social" / "common.py"
MICROBLOGGING_PY = _REPO_ROOT / "y_web" / "routes" / "social" / "microblogging.py"
PROFILE_HTML = _REPO_ROOT / "y_web" / "templates" / "microblogging" / "profile.html"
HASHTAG_HTML = _REPO_ROOT / "y_web" / "templates" / "microblogging" / "hashtag.html"
FEED_HTML = _REPO_ROOT / "y_web" / "templates" / "microblogging" / "feed.html"
THREAD_HTML = _REPO_ROOT / "y_web" / "templates" / "microblogging" / "thread.html"
PLUGIN_LOADER_INCLUDE = '{% include "shared/plugin_loader.html" %}'

PLUGIN_JS = (
    _REPO_ROOT
    / "external"
    / "frontend_adds-on"
    / "modules"
    / "post_annotation"
    / "frontend"
    / "plugin.js"
)


def test_profile_route_imports_and_passes_active_modules_context():
    source = COMMON_PY.read_text(encoding="utf-8")
    assert (
        "from y_web.src.external_runtime.plugin_loader import active_modules_context"
        in source
    )
    assert 'render_template(\n        "microblogging/profile.html"' in source
    # The microblogging profile render must pass frontend_adds_on_modules, not just
    # import the helper -- otherwise shared/plugin_loader.html's `{% if
    # frontend_adds_on_modules %}` guard always renders nothing on this page.
    render_call_start = source.index(
        'render_template(\n        "microblogging/profile.html"'
    )
    render_call = source[render_call_start : render_call_start + 400]
    assert "frontend_adds_on_modules=active_modules_context(exp_id)" in render_call


def test_hashtag_route_passes_active_modules_context():
    source = MICROBLOGGING_PY.read_text(encoding="utf-8")
    assert (
        "from y_web.src.external_runtime.plugin_loader import active_modules_context"
        in source
    )
    render_call_start = source.index(
        'render_template(\n        "microblogging/hashtag.html"'
    )
    render_call = source[render_call_start : render_call_start + 700]
    assert "frontend_adds_on_modules=active_modules_context(exp_id)" in render_call


def test_profile_and_hashtag_templates_include_plugin_loader():
    for template_path in (PROFILE_HTML, HASHTAG_HTML):
        template = template_path.read_text(encoding="utf-8")
        assert PLUGIN_LOADER_INCLUDE in template
        # Must be near the end of body, same placement convention as
        # feed.html/thread.html -- after it, only the closing tags.
        tail = template[template.index(PLUGIN_LOADER_INCLUDE) :]
        assert tail.strip().endswith("</body>\n</html>")


def test_feed_and_thread_templates_still_include_plugin_loader():
    # Guard against ever losing the original two working call sites while
    # editing this area of the templates.
    assert PLUGIN_LOADER_INCLUDE in FEED_HTML.read_text(encoding="utf-8")
    assert PLUGIN_LOADER_INCLUDE in THREAD_HTML.read_text(encoding="utf-8")


def test_find_anchors_labels_comments_by_their_own_id_not_the_threadroots():
    """
    Regression for the bug where EVERY `.media.is-comment` element was
    labeled `targetType: 'post'` using the nearest ancestor
    `.card.is-post[id^="feed-post-"]` -- correct only for a thread's own
    root post, wrong for every reply (mislabeled type) and wrong for a
    flat feed/profile/hashtag comment preview (wrong type AND wrong id,
    since those have no wrapper card of their own and would silently
    resolve to the PARENT post's id instead).
    """
    source = PLUGIN_JS.read_text(encoding="utf-8")

    # The fix must derive each comment's OWN id from a comment-scoped
    # marker (comment_form-/like-count-/etc.), not solely from whichever
    # `.card.is-post` ancestor happens to be nearest.
    assert "ownCommentId" in source
    assert "comment_form-" in source

    # It must distinguish "this IS the thread's own root post" (owns an
    # un-nested wrapper card matching its own id) from "this is a
    # comment/reply" (no such wrapper, or a wrapper nested inside another
    # post card) -- both cases must resolve to `targetType: 'comment'`.
    assert "isThreadRoot" in source
    assert "wrapperNested" in source

    # The old unconditional "any `.media.is-comment` with a `.card.is-post`
    # ancestor is a post" branch must be gone.
    assert (
        "anchors.push({ el: content, targetType: 'post', targetId: pid })" not in source
    )
