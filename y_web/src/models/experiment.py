"""
Experiment-simulation ORM models for YSocial.

All models in this module are bound to the ``db_exp`` database.
They represent the social network content generated during a running
simulation: users, posts, reactions, follows, etc.
"""

from flask_login import UserMixin

from y_web import db


class User_mgmt(UserMixin, db.Model):
    """
    User management model for experiment participants.

    Stores user profile information including personality traits (Big Five),
    demographic information, preferences, and activity settings. Used in
    experimental simulations to represent both human and AI-driven agents.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), nullable=False, unique=True)
    email = db.Column(db.String(50), nullable=True, default="")
    password = db.Column(db.String(80), nullable=False)
    leaning = db.Column(db.String(10), default="neutral")
    user_type = db.Column(db.String(10), nullable=False, default="user")
    age = db.Column(db.Integer, default=0)
    oe = db.Column(db.String(50))
    co = db.Column(db.String(50))
    ex = db.Column(db.String(50))
    ag = db.Column(db.String(50))
    ne = db.Column(db.String(50))
    recsys_type = db.Column(db.String(50), default="default")
    frecsys_type = db.Column(db.String(50), default="default")
    language = db.Column(db.String(10), default="en")
    owner = db.Column(db.String(10), default=None)
    education_level = db.Column(db.String(10), default=None)
    joined_on = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(10), default=None)
    nationality = db.Column(db.String(15), default=None)
    round_actions = db.Column(db.Integer, default=3)
    toxicity = db.Column(db.String(10), default="no")
    is_page = db.Column(db.Integer, default=0)
    left_on = db.Column(db.Integer, default=None)
    daily_activity_level = db.Column(db.Integer(), default=1)
    profession = db.Column(db.String(50), default="")
    activity_profile = db.Column(db.String(50), default="Always On")
    archetype = db.Column(db.String(50), nullable=True, default=None)

    posts = db.relationship("Post", backref="author", lazy=True)
    liked = db.relationship("Reactions", backref="liked_by", lazy=True)


class Post(db.Model):
    """
    Post/content model representing user-generated content.

    Stores posts, tweets, comments, and shared content within the social network.
    Supports threading, image attachments, news article links, and tracks reactions.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    tweet = db.Column(db.String(500), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    post_img = db.Column(db.String(20))
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    comment_to = db.Column(db.Integer, default=-1)
    thread_id = db.Column(db.Integer)
    news_id = db.Column(db.String(50), db.ForeignKey("articles.id"), default=None)
    image_id = db.Column(db.Integer(), db.ForeignKey("images.id"), default=None)
    image_post_id = db.Column(
        db.Integer(), db.ForeignKey("image_posts.id"), default=None
    )
    dedupe_key = db.Column(db.String(64), nullable=True, default=None)
    client_action_id = db.Column(db.String(96), nullable=True, default=None)
    created_at = db.Column(db.DateTime, nullable=True, default=db.func.now())
    shared_from = db.Column(db.Integer, default=-1)
    reaction_count = db.Column(db.Integer, default=0)
    moderated = db.Column(db.Integer, default=0, nullable=False)
    is_moderation_comment = db.Column(db.Integer, default=0, nullable=False)


class Hashtags(db.Model):
    """Hashtag model for tracking and categorizing content by topics."""

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    hashtag = db.Column(db.String(20), nullable=False)


class Emotions(db.Model):
    """Emotion types for post reactions (e.g., like, love, angry, sad)."""

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    emotion = db.Column(db.String(20), nullable=False)
    icon = db.Column(db.String(20), nullable=False)


class Post_emotions(db.Model):
    """Association table linking posts with emotion reactions."""

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    emotion_id = db.Column(db.Integer, db.ForeignKey("emotions.id"), nullable=False)


class Post_hashtags(db.Model):
    """Association table linking posts with hashtags."""

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    hashtag_id = db.Column(db.Integer, db.ForeignKey("hashtags.id"), nullable=False)


class Mentions(db.Model):
    """
    User mention tracking in posts.

    Records when users are mentioned (@username) in posts, tracks whether
    the mention was responded to, and the round in which it occurred.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    answered = db.Column(db.Integer, default=0)


class ReplyInboxState(db.Model):
    """
    Tracks the last seen reply notification for a user.

    This provides Reddit-style unread notifications without storing one row per
    reply event inside the experiment database.
    """

    __bind_key__ = "db_exp"
    __tablename__ = "reply_inbox_state"

    user_id = db.Column(
        db.Integer, db.ForeignKey("user_mgmt.id"), primary_key=True, nullable=False
    )
    last_seen_reply_id = db.Column(db.Integer, nullable=False, default=0)


class ForumChatSession(db.Model):
    """
    Persistent private chat thread between a forum user and a simulation agent.

    Stored inside the experiment database so chat history follows the experiment.
    """

    __bind_key__ = "db_exp"
    __tablename__ = "forum_chat_sessions"

    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False, index=True
    )
    owner_username = db.Column(db.String(50), nullable=False, index=True)
    target_user_id = db.Column(
        db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False, index=True
    )
    target_username = db.Column(db.String(50), nullable=False, index=True)
    target_profile_pic = db.Column(db.String(400), nullable=True)
    run_id = db.Column(db.Text, nullable=True, index=True)
    llm_model = db.Column(db.String(200), nullable=True)
    llm_base_url = db.Column(db.String(300), nullable=True)
    persona_snapshot = db.Column(db.Text, nullable=True)
    memory_snapshot_json = db.Column(db.Text, nullable=True)
    last_message_preview = db.Column(db.Text, nullable=True)
    last_message_at = db.Column(db.DateTime, nullable=True, default=db.func.now())
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.now(),
        onupdate=db.func.now(),
    )

    messages = db.relationship(
        "ForumChatMessage",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan",
    )


class ForumChatMessage(db.Model):
    """One message inside a forum chat session."""

    __bind_key__ = "db_exp"
    __tablename__ = "forum_chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("forum_chat_sessions.id"),
        nullable=False,
        index=True,
    )
    role = db.Column(db.String(12), nullable=False)
    content = db.Column(db.Text, nullable=False)
    meta_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())


class Reactions(db.Model):
    """
    User reactions to posts (likes, shares, etc.).

    Tracks all types of reactions users have to posts, including the round
    when the reaction occurred and the type of reaction.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    round = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    type = db.Column(db.String(10), nullable=False)


class Follow(db.Model):
    """
    Follow/unfollow relationship tracking.

    Records follower relationships between users, including follow and
    unfollow actions with timestamps (rounds).
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    follower_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(10), nullable=False)


class Rounds(db.Model):
    """
    Simulation time tracking.

    Represents time units in the simulation, mapping to specific days and hours
    for coordinating agent activities and content generation.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Integer, nullable=False)
    hour = db.Column(db.Integer, nullable=False)


class Recommendations(db.Model):
    """
    Content recommendation history.

    Stores recommended post IDs for users at specific rounds, supporting
    personalized content feed generation.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_ids = db.Column(db.String(500), nullable=False)
    round = db.Column(db.Integer, nullable=False)


class SysMessage(db.Model):
    __bind_key__ = "db_exp"
    __tablename__ = "sys_messages"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    to_uid = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=True)
    message = db.Column(db.Text, nullable=False)
    from_round = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=True)
    duration = db.Column(db.Integer, nullable=True)


class Reported(db.Model):
    __bind_key__ = "db_exp"
    __tablename__ = "reported"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    to_uid = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=True)
    to_post = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=True)
    from_uid = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    tid = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)


class Articles(db.Model):
    """
    News article metadata.

    Stores articles fetched from RSS feeds, including title, summary, source
    website, and fetch timestamp for news sharing in the platform.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.String(500), nullable=False)
    website_id = db.Column(db.Integer, db.ForeignKey("websites.id"), nullable=False)
    link = db.Column(db.String(200), nullable=False)
    fetched_on = db.Column(db.Integer, nullable=False)


class Websites(db.Model):
    """
    News source configuration.

    Defines news websites/RSS feeds used for article generation, including
    their political leaning, category, language, and country information.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    rss = db.Column(db.String(200), nullable=False)
    leaning = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    last_fetched = db.Column(db.Integer, nullable=False)
    language = db.Column(db.String(10), nullable=False)
    country = db.Column(db.String(10), nullable=False)
    fetch_images_from_url = db.Column(db.Boolean, default=False)
    fetch_images_timeout = db.Column(db.Integer, default=10)


class Voting(db.Model):
    """
    Voting/preference tracking for content.

    Records user voting preferences (upvote/downvote) on different content types
    for Reddit-style voting mechanisms.
    """

    __bind_key__ = "db_exp"
    vid = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    preference = db.Column(db.String(10), nullable=False)
    content_type = db.Column(db.String(10), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)


class Interests(db.Model):
    """Topic/interest categories for content classification."""

    __bind_key__ = "db_exp"
    iid = db.Column(db.Integer, primary_key=True)
    interest = db.Column(db.String(20), nullable=False)


class User_interest(db.Model):
    """Association table linking users with their interests/topics."""

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    interest_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)


class Post_topics(db.Model):
    """Association table linking posts with topic categories."""

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)


class Images(db.Model):
    """
    Image metadata for posts.

    Stores image URLs, LLM-generated descriptions, and optional associations
    with news articles for multimodal content.
    """

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200), nullable=True)
    description = db.Column(db.String(400), nullable=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=True)
    remote_article_id = db.Column(db.Integer, nullable=True)


class ImagePosts(db.Model):
    """
    Pre-fetched standalone images that forum agents can share.
    """

    __tablename__ = "image_posts"
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    source_url = db.Column(db.String(500), nullable=True)
    title = db.Column(db.String(300), nullable=True)
    subreddit = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    fetched_on = db.Column(db.String(20), nullable=True)
    used = db.Column(db.Boolean, default=False)
    local_path = db.Column(db.String(500), nullable=True)
    high_res_url = db.Column(db.String(500), nullable=True)


class Article_topics(db.Model):
    """Association table linking articles with topic categories."""

    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)


class Post_Sentiment(db.Model):
    """
    Sentiment analysis results for posts.

    Stores VADER sentiment scores (negative, neutral, positive, compound)
    for posts and comments, tracking sentiment over time and by topic.
    """

    __bind_key__ = "db_exp"
    __tablename__ = "post_sentiment"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    round = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)
    is_post = db.Column(db.Integer, default=0)
    is_comment = db.Column(db.Integer, default=0)
    is_reaction = db.Column(db.Integer, default=0)
    neg = db.Column(db.REAL)
    neu = db.Column(db.REAL)
    pos = db.Column(db.REAL)
    compound = db.Column(db.REAL)
    sentiment_parent = db.Column(db.String(5), default="")


class Post_Toxicity(db.Model):
    """
    Toxicity analysis results for posts.

    Stores Perspective API toxicity scores for various dimensions including
    toxicity, severe_toxicity, identity_attack, insult, profanity, threat,
    sexually_explicit content, and flirtation.
    """

    __bind_key__ = "db_exp"
    __tablename__ = "post_toxicity"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    toxicity = db.Column(db.REAL, default=0)
    severe_toxicity = db.Column(db.REAL, default=0)
    identity_attack = db.Column(db.REAL, default=0)
    insult = db.Column(db.REAL, default=0)
    profanity = db.Column(db.REAL, default=0)
    threat = db.Column(db.REAL, default=0)
    sexually_explicit = db.Column(db.REAL, default=0)
    flirtation = db.Column(db.REAL, default=0)


class Agent_Opinion(db.Model):
    """
    Agent opinion tracking for interactions.

    Stores opinions that agents form about topics, posts, and other agents
    during their interactions in the simulation. The opinion is stored as
    a float value representing the agent's sentiment or stance.

    Fields:
        id: Primary key
        agent_id: ID of the agent forming the opinion
        tid: Transaction/interaction ID for this opinion event
        topic_id: ID of the topic being discussed (FK to interests)
        id_interacted_with: ID of the user/agent being interacted with
        id_post: ID of the post that triggered this opinion (FK to post)
        opinion: Numerical opinion value (float) indicating sentiment/stance
    """

    __bind_key__ = "db_exp"
    __tablename__ = "agent_opinion"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, nullable=False)
    tid = db.Column(db.Integer, nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)
    id_interacted_with = db.Column(db.Integer, nullable=False)
    id_post = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    opinion = db.Column(db.REAL, nullable=False)
