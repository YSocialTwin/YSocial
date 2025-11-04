-- ================================================
-- PostgreSQL Schema for YSocial Platform (Dashboard)
-- Aligned with SQLite database_dashboard.db schema
-- ================================================

-- -----------------------------
-- Admin users
-- -----------------------------
CREATE TABLE admin_users (
    id              SERIAL PRIMARY KEY,
    username        TEXT,
    email           TEXT,
    password        TEXT,
    last_seen       TEXT,
    role            TEXT,
    llm             TEXT DEFAULT '',
    profile_pic     TEXT DEFAULT '',
    perspective_api TEXT DEFAULT NULL,
    llm_url         TEXT DEFAULT ''
);

-- -----------------------------
-- Experiments
-- -----------------------------
CREATE TABLE exps (
    idexp              SERIAL PRIMARY KEY,
    exp_name           TEXT,
    db_name            TEXT,
    owner              TEXT,
    exp_descr          TEXT,
    status             INTEGER DEFAULT 0 NOT NULL,
    running            INTEGER DEFAULT 0 NOT NULL,
    port               INTEGER NOT NULL,
    server             TEXT DEFAULT '127.0.0.1',
    platform_type      TEXT DEFAULT 'microblogging',
    annotations        TEXT DEFAULT '' NOT NULL,
    server_pid         INTEGER DEFAULT NULL,
    llm_agents_enabled INTEGER DEFAULT 1 NOT NULL
);

CREATE TABLE exp_stats (
    id        SERIAL PRIMARY KEY,
    exp_id    INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    rounds    INTEGER DEFAULT 0 NOT NULL,
    agents    INTEGER DEFAULT 0 NOT NULL,
    posts     INTEGER DEFAULT 0 NOT NULL,
    reactions INTEGER DEFAULT 0 NOT NULL,
    mentions  INTEGER DEFAULT 0 NOT NULL
);

-- -----------------------------
-- Activity profiles
-- -----------------------------
CREATE TABLE activity_profiles (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(120) NOT NULL UNIQUE,
    hours VARCHAR(100) NOT NULL
);

-- -----------------------------
-- Populations
-- -----------------------------
CREATE TABLE population (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    descr         TEXT NOT NULL,
    size          INTEGER DEFAULT 0,
    llm           TEXT,
    age_min       INTEGER,
    age_max       INTEGER,
    education     TEXT,
    leanings      TEXT,
    nationalities TEXT,
    interests     TEXT,
    toxicity      TEXT,
    languages     TEXT,
    frecsys       TEXT,
    crecsys       TEXT,
    llm_url       TEXT
);

-- -----------------------------
-- Agents
-- -----------------------------
CREATE TABLE agents (
    id                   SERIAL PRIMARY KEY,
    name                 TEXT NOT NULL,
    ag_type              TEXT DEFAULT '',
    leaning              TEXT,
    oe                   TEXT,
    co                   TEXT,
    ex                   TEXT,
    ag                   TEXT,
    ne                   TEXT,
    language             TEXT,
    education_level      TEXT,
    round_actions        TEXT,
    nationality          TEXT,
    toxicity             TEXT,
    age                  INTEGER,
    gender               TEXT,
    crecsys              TEXT,
    frecsys              TEXT,
    profile_pic          TEXT DEFAULT '',
    daily_activity_level INTEGER DEFAULT 1,
    profession           TEXT,
    activity_profile     INTEGER REFERENCES activity_profiles(id)
);

CREATE TABLE agent_profile (
    id       SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    profile  TEXT
);

CREATE TABLE agent_population (
    id            SERIAL PRIMARY KEY,
    agent_id      INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    population_id INTEGER NOT NULL REFERENCES population(id) ON DELETE CASCADE
);

-- -----------------------------
-- Pages
-- -----------------------------
CREATE TABLE pages (
    id               SERIAL PRIMARY KEY,
    name             TEXT NOT NULL,
    descr            TEXT,
    page_type        TEXT NOT NULL,
    feed             TEXT,
    keywords         TEXT,
    logo             TEXT,
    pg_type          TEXT,
    leaning          TEXT DEFAULT '',
    activity_profile INTEGER NOT NULL REFERENCES activity_profiles(id) ON DELETE CASCADE
);

CREATE TABLE page_population (
    id            SERIAL PRIMARY KEY,
    page_id       INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    population_id INTEGER NOT NULL REFERENCES population(id) ON DELETE CASCADE
);

-- -----------------------------
-- Clients
-- -----------------------------
CREATE TABLE client (
    id                                  SERIAL PRIMARY KEY,
    name                                TEXT NOT NULL,
    descr                               TEXT,
    days                                INTEGER,
    percentage_new_agents_iteration     REAL,
    percentage_removed_agents_iteration REAL,
    max_length_thread_reading           INTEGER,
    reading_from_follower_ratio         REAL,
    probability_of_daily_follow         REAL,
    attention_window                    INTEGER,
    visibility_rounds                   INTEGER,
    post                                REAL,
    share                               REAL,
    image                               REAL,
    comment                             REAL,
    read                                REAL,
    news                                REAL,
    search                              REAL,
    vote                                REAL,
    llm                                 TEXT,
    llm_api_key                         TEXT,
    llm_max_tokens                      INTEGER,
    llm_temperature                     REAL,
    llm_v_agent                         TEXT,
    llm_v                               TEXT,
    llm_v_api_key                       TEXT,
    llm_v_max_tokens                    INTEGER,
    llm_v_temperature                   REAL,
    status                              INTEGER DEFAULT 0 NOT NULL,
    id_exp                              INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    population_id                       INTEGER NOT NULL REFERENCES population(id) ON DELETE CASCADE,
    network_type                        TEXT,
    probability_of_secondary_follow     REAL DEFAULT 0,
    share_link                          REAL DEFAULT 0,
    crecsys                             TEXT,
    frecsys                             TEXT,
    pid                                 INTEGER DEFAULT NULL
);

CREATE TABLE client_execution (
    id                       SERIAL PRIMARY KEY,
    elapsed_time             INTEGER DEFAULT 0 NOT NULL,
    client_id                INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    expected_duration_rounds INTEGER DEFAULT 0 NOT NULL,
    last_active_hour         INTEGER DEFAULT -1 NOT NULL,
    last_active_day          INTEGER DEFAULT -1 NOT NULL
);

-- -----------------------------
-- Recommendation systems
-- -----------------------------
CREATE TABLE content_recsys (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE follow_recsys (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    value TEXT NOT NULL
);

-- -----------------------------
-- Auxiliary tables
-- -----------------------------
CREATE TABLE education (
    id              SERIAL PRIMARY KEY,
    education_level TEXT NOT NULL
);

CREATE TABLE leanings (
    id      SERIAL PRIMARY KEY,
    leaning TEXT NOT NULL
);

CREATE TABLE languages (
    id       SERIAL PRIMARY KEY,
    language TEXT NOT NULL
);

CREATE TABLE nationalities (
    id          SERIAL PRIMARY KEY,
    nationality TEXT NOT NULL
);

CREATE TABLE toxicity_levels (
    id             SERIAL PRIMARY KEY,
    toxicity_level TEXT NOT NULL
);

CREATE TABLE age_classes (
    id        SERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    age_start INTEGER NOT NULL,
    age_end   INTEGER NOT NULL
);

CREATE TABLE professions (
    id         SERIAL PRIMARY KEY,
    profession TEXT NOT NULL,
    background TEXT NOT NULL
);

-- -----------------------------
-- Relations
-- -----------------------------
CREATE TABLE population_experiment (
    id            SERIAL PRIMARY KEY,
    id_exp        INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    id_population INTEGER NOT NULL REFERENCES population(id) ON DELETE CASCADE
);

CREATE TABLE population_activity_profile (
    id               SERIAL PRIMARY KEY,
    population       INTEGER NOT NULL REFERENCES population(id) ON DELETE CASCADE,
    activity_profile INTEGER NOT NULL REFERENCES activity_profiles(id) ON DELETE CASCADE,
    percentage       REAL NOT NULL
);

-- -----------------------------
-- Topics
-- -----------------------------
CREATE TABLE topic_list (
    id   SERIAL PRIMARY KEY,
    name TEXT
);

CREATE TABLE exp_topic (
    id       SERIAL PRIMARY KEY,
    exp_id   INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topic_list(id) ON DELETE CASCADE
);

CREATE TABLE page_topic (
    id       SERIAL PRIMARY KEY,
    page_id  INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topic_list(id) ON DELETE CASCADE
);

CREATE TABLE user_experiment (
    id      SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES admin_users(id) ON DELETE CASCADE,
    exp_id  INTEGER REFERENCES exps(idexp) ON DELETE CASCADE
);

-- -----------------------------
-- Ollama and Jupyter
-- -----------------------------
CREATE TABLE ollama_pull (
    id         SERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    status     REAL DEFAULT 0 NOT NULL
);

CREATE TABLE jupyter_instances (
    id           SERIAL PRIMARY KEY,
    exp_id       INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    port         INTEGER NOT NULL,
    notebook_dir VARCHAR(300) NOT NULL,
    process      INTEGER,
    status       VARCHAR(10) NOT NULL DEFAULT 'active'
);

-- ================================================
-- DATA INSERTIONS (same as original)
-- ================================================

INSERT INTO content_recsys (name, value) VALUES
  ('ContentRecSys', 'Random'),
  ('ReverseChrono', '(RC) Reverse Chrono'),
  ('ReverseChronoPopularity', '(RCP) Popularity'),
  ('ReverseChronoFollowers', '(RCF) Followers'),
  ('ReverseChronoFollowersPopularity', '(FP) Followers-Popularity'),
  ('ReverseChronoComments', '(RCC) Reverse Chrono Comments'),
  ('CommonInterests', '(CI) Common Interests'),
  ('CommonUserInterests', '(CUI) Common User Interests'),
  ('SimilarUsersReactions', '(SIR) Similar Users Reactions'),
  ('SimilarUsersPosts', '(SIP) Similar Users Posts');

INSERT INTO follow_recsys (name, value) VALUES
('FollowRecSys', 'Random'),
('CommonNeighbors', 'Common Neighbors'),
('Jaccard', 'Jaccard'),
('AdamicAdar', 'Adamic Adar'),
('PreferentialAttachment', 'Preferential Attachment');

INSERT INTO leanings (leaning) VALUES
('democrat'),
('republican'),
('centrist');

INSERT INTO toxicity_levels (toxicity_level) VALUES
('none'),
('low'),
('medium'),
('high');

INSERT INTO age_classes (name, age_start, age_end) VALUES
('Youth', 14, 24),
('Adults', 25, 44),
('Middle-aged', 45, 64),
('Elderly', 65, 100);

INSERT INTO education (education_level) VALUES
  ('high school'),
  ('bachelor'),
  ('master'),
  ('phd');

-- (Professions, languages, nationalities, and activity_profiles data same as original - abbreviated for brevity)
