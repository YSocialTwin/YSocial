CREATE TABLE emotions (
    id SERIAL PRIMARY KEY,
    emotion TEXT NOT NULL,
    icon TEXT
);

CREATE TABLE hashtags (
    id SERIAL PRIMARY KEY,
    hashtag TEXT NOT NULL
);

CREATE TABLE interests (
    iid SERIAL PRIMARY KEY,
    interest TEXT
);

CREATE TABLE rounds (
    id SERIAL PRIMARY KEY,
    day INTEGER,
    hour INTEGER
);

CREATE TABLE user_mgmt (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(50),
    password  VARCHAR(400) NOT NULL,
    user_type TEXT,
    leaning TEXT,
    age INTEGER,
    oe TEXT,
    co TEXT,
    ex TEXT,
    ag TEXT,
    ne TEXT,
    recsys_type TEXT,
    language TEXT,
    owner TEXT,
    education_level TEXT,
    joined_on INTEGER,
    frecsys_type TEXT,
    round_actions INTEGER NOT NULL DEFAULT 3,
    gender TEXT,
    nationality TEXT,
    toxicity TEXT,
    is_page INTEGER NOT NULL DEFAULT 0,
    left_on INTEGER,
    daily_activity_level INTEGER DEFAULT 1,
    profession TEXT,
    activity_profile TEXT
);

CREATE TABLE follow (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user_mgmt(id) ON DELETE CASCADE,
    follower_id INTEGER NOT NULL REFERENCES user_mgmt(id) ON DELETE CASCADE,
    action TEXT,
    round INTEGER REFERENCES rounds(id) ON DELETE CASCADE
);

CREATE TABLE recommendations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user_mgmt(id) ON DELETE CASCADE,
    post_ids TEXT,
    round INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE
);

CREATE TABLE user_interest (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES user_mgmt(id) ON DELETE CASCADE,
    interest_id INTEGER REFERENCES interests(iid) ON DELETE CASCADE,
    round_id INTEGER REFERENCES rounds(id) ON DELETE CASCADE
);

CREATE TABLE voting (
    vid SERIAL PRIMARY KEY,
    round INTEGER,
    user_id INTEGER REFERENCES user_mgmt(id) ON DELETE CASCADE,
    preference TEXT,
    content_type TEXT,
    content_id INTEGER
);

CREATE TABLE websites (
    id SERIAL PRIMARY KEY,
    name TEXT,
    rss TEXT,
    leaning TEXT,
    category TEXT,
    last_fetched INTEGER,
    country TEXT,
    language TEXT
);

CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    website_id INTEGER NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    fetched_on INTEGER NOT NULL,
    link TEXT
);

CREATE TABLE article_topics (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES interests(iid) ON DELETE CASCADE,
    CONSTRAINT article_topic UNIQUE (article_id, topic_id)
);

CREATE TABLE images (
    id SERIAL PRIMARY KEY,
    url TEXT,
    description TEXT,
    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE
);

CREATE TABLE post (
    id SERIAL PRIMARY KEY,
    tweet TEXT NOT NULL,
    post_img VARCHAR(20),
    user_id INTEGER NOT NULL REFERENCES user_mgmt(id) ON DELETE CASCADE,
    comment_to INTEGER DEFAULT -1,
    thread_id INTEGER,
    round INTEGER REFERENCES rounds(id) ON DELETE CASCADE,
    news_id INTEGER DEFAULT -1 REFERENCES articles(id) ON DELETE CASCADE,
    shared_from INTEGER DEFAULT -1,
    image_id INTEGER REFERENCES images(id) ON DELETE CASCADE,
    reaction_count INTEGER DEFAULT 0
);

CREATE TABLE mentions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES user_mgmt(id) ON DELETE CASCADE,
    post_id INTEGER REFERENCES post(id) ON DELETE CASCADE,
    round INTEGER,
    answered INTEGER DEFAULT 0
);

CREATE TABLE post_emotions (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES post(id) ON DELETE CASCADE,
    emotion_id INTEGER REFERENCES emotions(id) ON DELETE CASCADE
);

CREATE TABLE post_hashtags (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES post(id) ON DELETE CASCADE,
    hashtag_id INTEGER REFERENCES hashtags(id) ON DELETE CASCADE
);

CREATE TABLE post_sentiment (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES post(id) ON DELETE CASCADE,
    neg REAL,
    pos REAL,
    neu REAL,
    compound REAL,
    user_id INTEGER NOT NULL REFERENCES user_mgmt(id) ON DELETE CASCADE,
    round INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    sentiment_parent TEXT,
    topic_id INTEGER NOT NULL REFERENCES interests(iid) ON DELETE CASCADE,
    is_post INTEGER NOT NULL DEFAULT 0,
    is_comment INTEGER NOT NULL DEFAULT 0,
    is_reaction INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE post_topics (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES post(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES interests(iid) ON DELETE CASCADE
);

CREATE TABLE post_toxicity (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES post(id) ON DELETE CASCADE,
    toxicity REAL DEFAULT 0 NOT NULL,
    severe_toxicity REAL DEFAULT 0,
    identity_attack REAL DEFAULT 0,
    insult REAL DEFAULT 0,
    profanity REAL DEFAULT 0,
    threat REAL DEFAULT 0,
    sexually_explicit REAL DEFAULT 0,
    flirtation REAL DEFAULT 0
);

CREATE TABLE reactions (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES post(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES user_mgmt(id) ON DELETE CASCADE,
    type TEXT,
    round INTEGER REFERENCES rounds(id) ON DELETE CASCADE
);


-- Indexes on user_mgmt
CREATE INDEX idx_user_mgmt_username ON user_mgmt(username);
CREATE INDEX idx_user_mgmt_email ON user_mgmt(email);
CREATE INDEX idx_user_mgmt_round_actions ON user_mgmt(round_actions);
CREATE INDEX idx_user_mgmt_nationality ON user_mgmt(nationality);

-- Indexes for follow table
CREATE INDEX idx_follow_user_id ON follow(user_id);
CREATE INDEX idx_follow_follower_id ON follow(follower_id);
CREATE INDEX idx_follow_round ON follow(round);

-- Indexes for recommendations
CREATE INDEX idx_recommendations_user_id ON recommendations(user_id);
CREATE INDEX idx_recommendations_round ON recommendations(round);

-- Indexes for user_interest
CREATE INDEX idx_user_interest_user_id ON user_interest(user_id);
CREATE INDEX idx_user_interest_interest_id ON user_interest(interest_id);
CREATE INDEX idx_user_interest_round_id ON user_interest(round_id);

-- Indexes for voting
CREATE INDEX idx_voting_user_id ON voting(user_id);
CREATE INDEX idx_voting_round ON voting(round);

-- Indexes for articles and article_topics
CREATE INDEX idx_articles_website_id ON articles(website_id);
CREATE INDEX idx_article_topics_article_id ON article_topics(article_id);
CREATE INDEX idx_article_topics_topic_id ON article_topics(topic_id);

-- Indexes for images
CREATE INDEX idx_images_article_id ON images(article_id);

-- Indexes for post
CREATE INDEX idx_post_user_id ON post(user_id);
CREATE INDEX idx_post_round ON post(round);
CREATE INDEX idx_post_thread_id ON post(thread_id);
CREATE INDEX idx_post_news_id ON post(news_id);
CREATE INDEX idx_post_image_id ON post(image_id);

-- Indexes for mentions
CREATE INDEX idx_mentions_user_id ON mentions(user_id);
CREATE INDEX idx_mentions_post_id ON mentions(post_id);
CREATE INDEX idx_mentions_round ON mentions(round);

-- Indexes for post_emotions
CREATE INDEX idx_post_emotions_post_id ON post_emotions(post_id);
CREATE INDEX idx_post_emotions_emotion_id ON post_emotions(emotion_id);

-- Indexes for post_hashtags
CREATE INDEX idx_post_hashtags_post_id ON post_hashtags(post_id);
CREATE INDEX idx_post_hashtags_hashtag_id ON post_hashtags(hashtag_id);

-- Indexes for post_sentiment
CREATE INDEX idx_post_sentiment_post_id ON post_sentiment(post_id);
CREATE INDEX idx_post_sentiment_user_id ON post_sentiment(user_id);
CREATE INDEX idx_post_sentiment_round ON post_sentiment(round);
CREATE INDEX idx_post_sentiment_topic_id ON post_sentiment(topic_id);

-- Indexes for post_topics
CREATE INDEX idx_post_topics_post_id ON post_topics(post_id);
CREATE INDEX idx_post_topics_topic_id ON post_topics(topic_id);

-- Indexes for post_toxicity
CREATE INDEX idx_post_toxicity_post_id ON post_toxicity(post_id);

-- Indexes for reactions
CREATE INDEX idx_reactions_post_id ON reactions(post_id);
CREATE INDEX idx_reactions_user_id ON reactions(user_id);
CREATE INDEX idx_reactions_round ON reactions(round);


INSERT INTO emotions (emotion, icon) VALUES
('amusement', 'mdi-emoticon-happy'),
('admiration', 'mdi-weather-sunny'),
('anger', 'mdi-emoticon-devil'),
('annoyance', 'mdi-emoticon-tongue'),
('approval', 'mdi-thumb-up-outline'),
('caring', 'mdi-cake'),
('confusion', 'mdi-emoticon-neutral'),
('curiosity', 'mdi-beaker-outline'),
('desire', 'mdi-cash-multiple'),
('disappointment', 'mdi-close-circle'),
('disapproval', 'mdi-thumb-down-outline'),
('disgust', 'mdi-emoticon-poop'),
('embarrassment', 'mdi-minus-circle'),
('excitement', 'mdi-rocket'),
('fear', 'mdi-weather-lightning'),
('gratitude', 'mdi-panda'),
('grief', 'mdi-weather-pouring'),
('joy', 'mdi-emoticon'),
('love', 'mdi-heart'),
('nervousness', 'mdi-alert'),
('optimism', 'mdi-leaf'),
('pride', 'mdi-emoticon-cool'),
('realization', 'mdi-lightbulb-outline'),
('relief', 'mdi-weather-sunset-up'),
('remorse', 'mdi-ambulance'),
('sadness', 'mdi-emoticon-sad'),
('surprise', 'mdi-wallet-giftcard'),
('trust', 'mdi-brightness-5');
