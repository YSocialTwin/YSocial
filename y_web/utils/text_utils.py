import re
from html.parser import HTMLParser
from y_web.models import User_mgmt, Hashtags, Post_Toxicity, Admin_users
from io import StringIO
from nltk.sentiment import SentimentIntensityAnalyzer
from perspective import PerspectiveAPI


def vader_sentiment(text):
    """
    Calculate the sentiment of the text using the VADER sentiment analysis tool.

    :param text:
    :return:
    """

    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment


def toxicity(text, username, post_id, db):
    """
    Calculate the toxicity of the text using the Perspective API.

    :param text:
    :param username:
    :param post_id:
    :param db:
    :return:
    """

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
    Augment the text by adding links to the mentions and hashtags.

    :param text: the text to augment
    :return: the augmented text
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
    Extract the components from the text.

    :param text: the text to extract the components from
    :param c_type: the component type
    :return: the extracted components
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
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


def process_reddit_post(text):
    """
    Process post text for Reddit-style display.
    Handles TITLE: prefix and formats properly.

    :param text: the raw post text
    :return: tuple of (title, content) or (None, text) if no title
    """
    if text.startswith("TITLE: "):
        # Split on first newline after title
        lines = text.split('\n', 1)
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