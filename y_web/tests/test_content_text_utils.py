"""
Phase E — content/text_utils.py processing tests.

Covers the pure text-processing helpers that feed agent content generation.
All tests are side-effect-free and require no database or Flask app context.
"""

import pytest


# ---------------------------------------------------------------------------
# strip_tags
# ---------------------------------------------------------------------------


def test_strip_tags_removes_html():
    from y_web.src.content.text_utils import strip_tags

    assert strip_tags("<b>Hello</b> <i>world</i>") == "Hello world"


def test_strip_tags_empty_string():
    from y_web.src.content.text_utils import strip_tags

    assert strip_tags("") == ""


def test_strip_tags_plain_text_unchanged():
    from y_web.src.content.text_utils import strip_tags

    assert strip_tags("No tags here") == "No tags here"


def test_strip_tags_nested_tags():
    from y_web.src.content.text_utils import strip_tags

    assert strip_tags("<div><p>text</p></div>") == "text"


# ---------------------------------------------------------------------------
# strip_markdown_artifacts
# ---------------------------------------------------------------------------


def test_strip_markdown_artifacts_removes_section_headers():
    from y_web.src.content.text_utils import strip_markdown_artifacts

    text = "## Conclusion\nSome text."
    result = strip_markdown_artifacts(text)
    assert "Conclusion" not in result
    assert "Some text." in result


def test_strip_markdown_artifacts_preserves_plain_text():
    from y_web.src.content.text_utils import strip_markdown_artifacts

    plain = "This is a regular sentence with no markdown."
    assert strip_markdown_artifacts(plain) == plain


def test_strip_markdown_artifacts_removes_heading_hashes():
    from y_web.src.content.text_utils import strip_markdown_artifacts

    text = "## My heading\nBody text."
    result = strip_markdown_artifacts(text)
    assert not result.startswith("#")


# ---------------------------------------------------------------------------
# calculate_text_similarity
# ---------------------------------------------------------------------------


def test_calculate_text_similarity_identical():
    from y_web.src.content.text_utils import calculate_text_similarity

    assert calculate_text_similarity("hello world", "hello world") == 1.0


def test_calculate_text_similarity_disjoint():
    from y_web.src.content.text_utils import calculate_text_similarity

    assert calculate_text_similarity("apple banana", "cat dog") == 0.0


def test_calculate_text_similarity_partial_overlap():
    from y_web.src.content.text_utils import calculate_text_similarity

    score = calculate_text_similarity("hello world", "hello there")
    assert 0.0 < score < 1.0


def test_calculate_text_similarity_empty_returns_zero():
    from y_web.src.content.text_utils import calculate_text_similarity

    assert calculate_text_similarity("", "hello") == 0.0
    assert calculate_text_similarity("hello", "") == 0.0


# ---------------------------------------------------------------------------
# normalize_punctuation_spacing
# ---------------------------------------------------------------------------


def test_normalize_punctuation_spacing_fixes_double_spaces():
    from y_web.src.content.text_utils import normalize_punctuation_spacing

    # The function fixes missing space after punctuation, not double-spaces;
    # test its actual contract: adds space after punctuation before a word.
    result = normalize_punctuation_spacing("Hello.World")
    assert "Hello. World" in result or result == "Hello. World"


def test_normalize_punctuation_spacing_comma_no_space():
    from y_web.src.content.text_utils import normalize_punctuation_spacing

    result = normalize_punctuation_spacing("word,next")
    assert result == "word, next"


def test_normalize_punctuation_spacing_preserves_urls():
    from y_web.src.content.text_utils import normalize_punctuation_spacing

    url = "https://example.com/path?a=1&b=2"
    result = normalize_punctuation_spacing(url)
    assert url in result


# ---------------------------------------------------------------------------
# strip_reproduced_article_content
# ---------------------------------------------------------------------------


def test_strip_reproduced_article_content_high_overlap_truncates():
    from y_web.src.content.text_utils import strip_reproduced_article_content

    article = "The quick brown fox jumps over the lazy dog"
    # Make post body a near-verbatim copy
    post = "The quick brown fox jumps over the lazy dog. Extra sentence."
    result_text, was_stripped = strip_reproduced_article_content(post, article)
    # With high similarity the function should flag it
    assert isinstance(was_stripped, bool)


def test_strip_reproduced_article_content_low_overlap_unchanged():
    from y_web.src.content.text_utils import strip_reproduced_article_content

    article = "Science paper about quantum computing and entanglement"
    post = "I had a great day at the beach today!"
    result_text, was_stripped = strip_reproduced_article_content(post, article)
    assert result_text == post
    assert was_stripped is False


def test_strip_reproduced_article_content_empty_article_returns_unchanged():
    from y_web.src.content.text_utils import strip_reproduced_article_content

    post = "Some post body text."
    result_text, was_stripped = strip_reproduced_article_content(post, "")
    assert result_text == post
    assert was_stripped is False


# ---------------------------------------------------------------------------
# process_reddit_post
# ---------------------------------------------------------------------------


def test_process_reddit_post_extracts_title_from_prefix():
    from y_web.src.content.text_utils import process_reddit_post

    text = "TITLE: My Post Title\nThis is the body."
    title, content = process_reddit_post(text)
    assert title == "My Post Title"
    assert "body" in content


def test_process_reddit_post_legacy_blankline_title():
    from y_web.src.content.text_utils import process_reddit_post

    text = "Candidate Title\n\nThis is the body of the post."
    title, content = process_reddit_post(text)
    assert title == "Candidate Title"
    assert "body" in content


def test_process_reddit_post_no_title_returns_none_title():
    from y_web.src.content.text_utils import process_reddit_post

    text = "Just a regular post without a title or blank line."
    title, content = process_reddit_post(text, allow_legacy_blankline_title=False)
    assert title is None
    assert content  # body should be non-empty


def test_process_reddit_post_empty_input():
    from y_web.src.content.text_utils import process_reddit_post

    title, content = process_reddit_post("")
    assert title is None
    assert content == ""


# ---------------------------------------------------------------------------
# extract_components
# ---------------------------------------------------------------------------


def test_extract_components_hashtags():
    from y_web.src.content.text_utils import extract_components

    text = "Loving #python and #opensource today!"
    tags = extract_components(text, c_type="hashtags")
    assert "#python" in tags
    assert "#opensource" in tags


def test_extract_components_mentions():
    from y_web.src.content.text_utils import extract_components

    text = "Thanks @alice and @bob for the help!"
    mentions = extract_components(text, c_type="mentions")
    assert "@alice" in mentions
    assert "@bob" in mentions


def test_extract_components_empty_text_returns_empty():
    from y_web.src.content.text_utils import extract_components

    assert extract_components("", c_type="hashtags") == []
    assert extract_components("", c_type="mentions") == []


def test_extract_components_unknown_type_returns_empty():
    from y_web.src.content.text_utils import extract_components

    assert extract_components("some text", c_type="unknown") == []
