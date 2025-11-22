"""
Utility module to check for new blog posts from y-not.social/blog.

This module fetches the latest blog posts from the blog's RSS feed and
stores them in the database for display in the admin dashboard.
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime


def fetch_latest_blog_post():
    """
    Fetch the latest blog post from the Y Social blog RSS feed.

    Returns:
        dict: Information about the latest blog post with keys:
              - title: Blog post title
              - published_at: Publication date (ISO format string)
              - link: URL to the blog post
              Returns None if unable to fetch or parse the feed.
    """
    try:
        # Try multiple possible RSS feed URLs
        feed_urls = [
            "https://y-not.social/blog/rss.xml",
            "https://y-not.social/rss.xml",
            "https://y-not.social/blog/feed",
            "https://y-not.social/blog/atom.xml",
        ]

        response = None
        for url in feed_urls:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    break
            except Exception:
                continue

        if not response or response.status_code != 200:
            print(f"Failed to fetch blog feed. Status: {response.status_code if response else 'No response'}")
            return None

        # Parse the RSS/Atom feed
        root = ET.fromstring(response.content)

        # Try RSS format first
        item = None
        # Check for RSS 2.0 format
        item = root.find(".//item")
        if item is not None:
            title_elem = item.find("title")
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")

            if title_elem is not None and link_elem is not None:
                return {
                    "title": title_elem.text,
                    "link": link_elem.text,
                    "published_at": pub_date_elem.text if pub_date_elem is not None else datetime.utcnow().isoformat(),
                }

        # Try Atom format
        # Define namespace for Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find(".//atom:entry", ns)
        if entry is not None:
            title_elem = entry.find("atom:title", ns)
            link_elem = entry.find("atom:link[@rel='alternate']", ns)
            if link_elem is None:
                link_elem = entry.find("atom:link", ns)
            published_elem = entry.find("atom:published", ns)
            if published_elem is None:
                published_elem = entry.find("atom:updated", ns)

            if title_elem is not None and link_elem is not None:
                link = link_elem.get("href") if link_elem.get("href") else link_elem.text
                return {
                    "title": title_elem.text,
                    "link": link,
                    "published_at": published_elem.text if published_elem is not None else datetime.utcnow().isoformat(),
                }

        print("Could not parse blog feed - no valid item/entry found")
        return None

    except Exception as e:
        print(f"Error fetching blog posts: {e}")
        return None


def update_blog_info_in_db():
    """
    Check for new blog posts and store/update blog information in the database.

    This function should be called at application startup to check for new blog posts.
    It updates the blog_posts table with the latest post information and marks it as unread
    if it's a new post (different from the previous one stored).

    Returns:
        tuple: (has_new_post: bool, blog_info: dict or None)
    """
    try:
        print("Checking for new blog posts...")
        blog_post = fetch_latest_blog_post()

        # Import here to avoid circular imports
        from y_web import db
        from y_web.models import BlogPost

        # Get the latest blog post from DB
        latest_in_db = BlogPost.query.order_by(BlogPost.id.desc()).first()

        # Update check time
        check_time = datetime.utcnow().isoformat()

        if blog_post:
            # Check if this is a new blog post
            is_new = True
            if latest_in_db and latest_in_db.link == blog_post.get("link"):
                # Same post as before
                is_new = False
                latest_in_db.latest_check_on = check_time
                db.session.commit()
                print(f"No new blog post (latest: {blog_post.get('title')})")
                
                # Return the unread post if it exists
                if not latest_in_db.is_read:
                    return True, {
                        "id": latest_in_db.id,
                        "title": latest_in_db.title,
                        "published_at": latest_in_db.published_at,
                        "link": latest_in_db.link,
                    }
                return False, None

            if is_new:
                # Create new blog post entry
                new_post = BlogPost(
                    title=blog_post.get("title"),
                    published_at=blog_post.get("published_at"),
                    link=blog_post.get("link"),
                    is_read=False,
                    latest_check_on=check_time,
                )
                db.session.add(new_post)
                db.session.commit()
                print(f"New blog post found: {blog_post.get('title')}")
                return True, {
                    "id": new_post.id,
                    "title": new_post.title,
                    "published_at": new_post.published_at,
                    "link": new_post.link,
                }
        else:
            # Could not fetch blog post, but update check time if record exists
            if latest_in_db:
                latest_in_db.latest_check_on = check_time
                db.session.commit()
            print("Could not fetch blog post")

        return False, None

    except Exception as e:
        print(f"Error checking for blog posts: {e}")
        import traceback
        traceback.print_exc()
        return False, None
