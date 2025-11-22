"""
Simple test to verify blog post checking logic.
"""


def test_fetch_latest_blog_post_handles_errors():
    """Test that fetch_latest_blog_post handles errors gracefully."""
    from y_web.utils.check_blog import fetch_latest_blog_post

    # This should return None since the domain is unreachable in this environment
    result = fetch_latest_blog_post()
    assert result is None or isinstance(result, dict)

    if result:
        # If we got a result, verify it has the expected keys
        assert "title" in result
        assert "link" in result
        assert "published_at" in result


def test_rss_parsing_logic():
    """Test RSS parsing logic with sample data."""
    import xml.etree.ElementTree as ET

    # Sample RSS 2.0 feed
    rss_sample = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Test Blog</title>
            <item>
                <title>Test Post</title>
                <link>https://example.com/test</link>
                <pubDate>2024-01-01T00:00:00Z</pubDate>
            </item>
        </channel>
    </rss>"""

    root = ET.fromstring(rss_sample)
    item = root.find(".//item")

    assert item is not None
    title = item.find("title")
    link = item.find("link")
    pub_date = item.find("pubDate")

    assert title.text == "Test Post"
    assert link.text == "https://example.com/test"
    assert pub_date.text == "2024-01-01T00:00:00Z"


def test_atom_parsing_logic():
    """Test Atom parsing logic with sample data."""
    import xml.etree.ElementTree as ET

    # Sample Atom feed
    atom_sample = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Test Blog</title>
        <entry>
            <title>Test Post</title>
            <link href="https://example.com/test" rel="alternate"/>
            <published>2024-01-01T00:00:00Z</published>
        </entry>
    </feed>"""

    root = ET.fromstring(atom_sample)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find(".//atom:entry", ns)

    assert entry is not None
    title = entry.find("atom:title", ns)
    link = entry.find("atom:link[@rel='alternate']", ns)
    published = entry.find("atom:published", ns)

    assert title.text == "Test Post"
    assert link.get("href") == "https://example.com/test"
    assert published.text == "2024-01-01T00:00:00Z"


if __name__ == "__main__":
    print("Running blog post tests...")
    test_fetch_latest_blog_post_handles_errors()
    print("✓ test_fetch_latest_blog_post_handles_errors passed")
    test_rss_parsing_logic()
    print("✓ test_rss_parsing_logic passed")
    test_atom_parsing_logic()
    print("✓ test_atom_parsing_logic passed")
    print("\nAll tests passed!")
