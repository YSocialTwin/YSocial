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


def augment_text(text, exp_id):
    """
    Augment text by converting mentions and hashtags to clickable links.

    Replaces @username mentions with links to user profiles and #hashtag
    with links to hashtag pages. Also capitalizes the first letter and
    removes surrounding quote characters.

    Args:
        text: Raw text with mentions and hashtags
        exp_id: ID of the experiment

    Returns:
        HTML string with hyperlinked mentions and hashtags
    """
    # Remove leading/trailing quote characters
    text = text.strip('"')

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
            # Try exact match first
            hashtag_obj = Hashtags.query.filter_by(hashtag=h).first()
            if hashtag_obj:
                used_hastag[h] = hashtag_obj.id
            else:
                # Try without # prefix for HPC compatibility
                hashtag_obj = Hashtags.query.filter_by(hashtag=h[1:]).first()
                if hashtag_obj:
                    used_hastag[h] = hashtag_obj.id
        except:
            pass

    # Replace the mentions and hashtags with the links
    for m, uid in mentioned_users.items():
        text = text.replace(m, f'<a href="/{exp_id}/user_profile/{uid}"> {m} </a>')

    for h, hid in used_hastag.items():
        text = text.replace(h, f'<a href="/{exp_id}/hashtag_posts/{hid}/1"> {h} </a>')

    # remove first character it is a space
    if len(text) > 0 and text[0] == " ":
        text = text[1:]

    # capitalize the first letter of the text
    if len(text) > 0:
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


def strip_markdown_artifacts(text):
    """
    Remove markdown headers and common article structure artifacts.
    """
    if not text:
        return text

    text = re.sub(
        r"^#+\s*(Conclusion|Call to Action|Key Points?|Summary|Overview|"
        r"Introduction|Background|TL;?DR|Final Thoughts?|Takeaway|"
        r"What\'s Next|Next Steps?|Resources?)[:\s]*",
        "",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    text = re.sub(r"^#+\s+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def calculate_text_similarity(text1, text2):
    """
    Calculate similarity between two texts using Jaccard word overlap.
    """
    if not text1 or not text2:
        return 0.0

    words1 = set(re.findall(r"\b\w+\b", text1.lower()))
    words2 = set(re.findall(r"\b\w+\b", text2.lower()))
    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return intersection / union if union > 0 else 0.0


def strip_reproduced_article_content(
    post_body, article_summary, similarity_threshold=0.6
):
    """
    Strip post body fragments that substantially reproduce the article summary.
    """
    if not post_body or not article_summary:
        return post_body, False

    article_words = set(re.findall(r"\b\w+\b", article_summary.lower()))
    similarity = calculate_text_similarity(post_body, article_summary)
    if similarity < similarity_threshold:
        return post_body, False

    sentences = re.split(r"(?<=[.!?])\s+", post_body)
    filtered_sentences = []
    sentence_threshold = similarity_threshold * 0.6

    for sentence in sentences:
        sentence_similarity = calculate_text_similarity(sentence, article_summary)
        sentence_words = set(re.findall(r"\b\w+\b", sentence.lower()))
        overlap_ratio = (
            len(sentence_words & article_words) / len(sentence_words)
            if sentence_words
            else 0
        )
        if sentence_similarity < sentence_threshold and overlap_ratio < 0.7:
            filtered_sentences.append(sentence)

    if filtered_sentences:
        return " ".join(filtered_sentences), True
    return "", True


def normalize_punctuation_spacing(text):
    """
    Add a single missing space after common punctuation marks.
    """
    if not text:
        return text

    preserved = {}

    def _preserve(match):
        key = f"__URL_{len(preserved)}__"
        preserved[key] = match.group(0)
        return key

    normalized = re.sub(r"https?://\S+", _preserve, str(text))
    normalized = re.sub(
        r"(?<!\d)([.!?;:])(?!\s|$)(?=[A-Za-z])",
        r"\1 ",
        normalized,
    )
    normalized = re.sub(
        r"(?<!\d),(?!\s|$)(?=[A-Za-z])",
        ", ",
        normalized,
    )

    for key, url in preserved.items():
        normalized = normalized.replace(key, url)

    return normalized


def process_reddit_post(text, allow_legacy_blankline_title=True):
    """
    Process and format Reddit-style post text.

    Handles TITLE prefix variants and strips markdown artifacts from the body.
    """
    if not text:
        return None, ""

    text = text.strip()
    title_match = re.match(
        r"^[\*_]{0,2}(TITLE|TITTLE|TITEL)\s*:\s*", text, re.IGNORECASE
    )

    if title_match:
        remaining = text[title_match.end() :]
        lines = remaining.split("\n", 1)
        title = re.sub(r"[\*_]{1,2}$", "", lines[0].strip()).strip()
        if len(lines) > 1:
            content = lines[1].lstrip()
        else:
            content = ""
            if len(title) >= 200:
                t = title
                min_idx, max_idx = 40, 160
                split_at = None
                for pat in [r"\.\s+", r"!\s+", r"\?\s+", r"\.\.\.\s+"]:
                    match = re.search(pat, t)
                    if match and min_idx <= match.end() <= max_idx:
                        split_at = match.end()
                        break
                if split_at is None:
                    cut = t.rfind(" ", 0, max_idx)
                    if cut >= min_idx:
                        split_at = cut + 1
                if split_at is not None and split_at < len(t) - 1:
                    title = t[:split_at].strip()
                    content = t[split_at:].lstrip()
    else:
        title = None
        content = text.lstrip()
        if allow_legacy_blankline_title:
            blocks = re.split(r"\n\s*\n", text, maxsplit=1)
            if len(blocks) > 1:
                candidate_title = blocks[0].strip()
                candidate_body = blocks[1].lstrip()
                if candidate_title and candidate_body and len(candidate_title) <= 300:
                    title = candidate_title
                    content = candidate_body

    content = strip_markdown_artifacts(content)
    content = re.sub(
        r"^[\*_]{0,2}(TITLE|TITTLE|TITEL)\s*:\s*",
        "",
        content,
        flags=re.IGNORECASE,
    ).lstrip()
    return title, content
