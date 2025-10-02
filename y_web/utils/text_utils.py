"""
Text processing utilities for social media content.

Provides functions for sentiment analysis, toxicity detection, text augmentation
with hyperlinks, component extraction (hashtags, mentions), HTML tag stripping,
and Reddit-style post formatting.
"""

import re
from html.parser import HTMLParser
from io import StringIO

from y_web.models import Admin_users, Hashtags, Post_Toxicity, User_mgmt

# Optional imports
try:
    from nltk.sentiment import SentimentIntensityAnalyzer

    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    from perspective import PerspectiveAPI

    PERSPECTIVE_AVAILABLE = True
except ImportError:
    PERSPECTIVE_AVAILABLE = False


def vader_sentiment(text):
    """
    Calculate sentiment scores using VADER sentiment analysis.

    VADER (Valence Aware Dictionary and sEntiment Reasoner) is specifically
    tuned for social media text sentiment analysis.

    Args:
        text: Text content to analyze

    Returns:
        Dictionary with sentiment scores: {'neg', 'neu', 'pos', 'compound'}
    """
    if not NLTK_AVAILABLE:
        # Return mock sentiment if NLTK is not available
        return {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0}

    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment


def toxicity(text, username, post_id, db):
    """
    Calculate toxicity scores using Google's Perspective API.

    Analyzes text for various dimensions of toxicity including general toxicity,
    severe toxicity, identity attacks, insults, profanity, threats, sexually
    explicit content, and flirtation. Results are stored in the database.

    Args:
        text: Text content to analyze
        username: Username of the admin user (for API key lookup)
        post_id: ID of the post being analyzed
        db: Database session for storing results

    Returns:
        None (stores results in Post_Toxicity table)
    """
    if not PERSPECTIVE_AVAILABLE:
        # Return None if Perspective API is not available
        return None

    user = Admin_users.query.filter_by(username=username).first()

    if user is not None:
        api_key = user.perspective_api
        if api_key is not None:
            try:
                p = PerspectiveAPI(api_key)
                toxicity_score = p.score(
                    text,
                    tests=[
                        "TOXICITY",
                        "SEVERE_TOXICITY",
                        "IDENTITY_ATTACK",
                        "INSULT",
                        "PROFANITY",
                        "THREAT",
                        "SEXUALLY_EXPLICIT",
                        "FLIRTATION",
                    ],
                )
                post_toxicity = Post_Toxicity(
                    post_id=post_id,
                    toxicity=toxicity_score["TOXICITY"],
                    severe_toxicity=toxicity_score["SEVERE_TOXICITY"],
                    identity_attack=toxicity_score["IDENTITY_ATTACK"],
                    insult=toxicity_score["INSULT"],
                    profanity=toxicity_score["PROFANITY"],
                    threat=toxicity_score["THREAT"],
                    sexually_explicit=toxicity_score["SEXUALLY_EXPLICIT"],
                    flirtation=toxicity_score["FLIRTATION"],
                )

                db.session.add(post_toxicity)
                db.session.commit()

            except Exception as e:
                print(e)
                return


def augment_text(text):
    """
    Augment text by converting mentions and hashtags to clickable links.

    Replaces @username mentions with links to user profiles and #hashtag
    with links to hashtag pages. Also capitalizes the first letter.

    Args:
        text: Raw text with mentions and hashtags

    Returns:
        HTML string with hyperlinked mentions and hashtags
    """
    # text = text.split("(")[0]

    # Extract the mentions and hashtags
    mentions = extract_components(text, c_type="mentions")
    hashtags = extract_components(text, c_type="hashtags")

    # Define the dictionary to store the mentioned users and used hashtags
    mentioned_users = {}
    used_hastag = {}

    # Get the mentioned user id
    for m in mentions:
        try:
            mentioned_users[m] = User_mgmt.query.filter_by(username=m[1:]).first().id
        except:
            pass

    # Get the used hashtag id
    for h in hashtags:
        try:
            used_hastag[h] = Hashtags.query.filter_by(hashtag=h).first().id
        except:
            pass

    # Replace the mentions and hashtags with the links
    for m, uid in mentioned_users.items():
        text = text.replace(m, f'<a href="/user_profile/{uid}"> {m} </a>')

    for h, hid in used_hastag.items():
        text = text.replace(h, f'<a href="/hashtag_posts/{hid}/1"> {h} </a>')

    # remove first character it is a space
    if text[0] == " ":
        text = text[1:]

    # capitalize the first letter of the text
    text = text[0].upper() + text[1:]

    return text


def extract_components(text, c_type="hashtags"):
    """
    Extract hashtags or mentions from text using regex patterns.

    Args:
        text: Text to extract components from
        c_type: Component type - "hashtags" for #tags or "mentions" for @users

    Returns:
        List of extracted components (including # or @ prefix)
    """
    # Define the regex pattern
    if c_type == "hashtags":
        pattern = re.compile(r"#\w+")
    elif c_type == "mentions":
        pattern = re.compile(r"@\w+")
    else:
        return []
    # Find all matches in the input text
    hashtags = pattern.findall(text)
    return hashtags


class MLStripper(HTMLParser):
    """HTML parser subclass that strips all HTML tags from text."""

    def __init__(self):
        """Handle   init   operation."""
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        """Display handle data page."""
        self.text.write(d)

    def get_data(self):
        """
        Get extracted text data.

        Returns:
            String containing extracted text
        """
        return self.text.getvalue()


def strip_tags(html):
    """
    Remove all HTML tags from text content.

    Args:
        html: HTML string to strip tags from

    Returns:
        Plain text with all HTML tags removed
    """
    s = MLStripper()
    s.feed(html)
    return s.get_data()


def process_reddit_post(text):
    """
    Process and format Reddit-style post text.

    Handles posts with "TITLE: " prefix by splitting into title and content,
    and removes leading whitespace from content.

    Args:
        text: Raw post text to process

    Returns:
        Tuple of (title, content) where title is None if no TITLE prefix exists
    """
    if text.startswith("TITLE: "):
        # Split on first newline after title
        lines = text.split("\n", 1)
        title = lines[0].replace("TITLE: ", "").strip()
        if len(lines) > 1:
            # Remove all leading whitespace from the content
            content = lines[1].lstrip()
        else:
            content = ""
        return title, content
    else:
        # For non-title posts, still remove leading whitespace
        return None, text.lstrip()
