-- ================================================
-- PostgreSQL Schema for YSocial Platform (Dashboard)
-- Aligned with SQLite database_dashboard.db schema
-- ================================================

-- -----------------------------
-- Admin users
-- -----------------------------
CREATE TABLE admin_users (
    id                    SERIAL PRIMARY KEY,
    username              TEXT,
    email                 TEXT,
    password              TEXT,
    last_seen             TEXT,
    role                  TEXT,
    llm                   TEXT DEFAULT '',
    profile_pic           TEXT DEFAULT '',
    perspective_api       TEXT DEFAULT NULL,
    llm_url               TEXT DEFAULT '',
    telemetry_enabled     BOOLEAN DEFAULT TRUE,
    telemetry_notice_shown BOOLEAN DEFAULT FALSE
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

-- -----------------------------
-- Release Information
-- -----------------------------
CREATE TABLE release_info (
    id                  SERIAL PRIMARY KEY,
    latest_version_tag  TEXT,
    release_name        TEXT,
    published_at        TEXT,
    download_url        TEXT,
    size                TEXT,
    sha256              TEXT,
    latest_check_on     TEXT
);

-- -----------------------------
-- Blog Posts
-- -----------------------------
CREATE TABLE blog_posts (
    id                  SERIAL PRIMARY KEY,
    title               TEXT,
    published_at        TEXT,
    link                TEXT,
    is_read             BOOLEAN DEFAULT FALSE,
    latest_check_on     TEXT
);

-- ================================================
-- DATA INSERTIONS
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

INSERT INTO professions (profession, background) VALUES
('Doctor', 'Healthcare'),
('Nurse', 'Healthcare'),
('Paramedic', 'Healthcare'),
('Dentist', 'Healthcare'),
('Pharmacist', 'Healthcare'),
('Surgeon', 'Healthcare'),
('Veterinarian', 'Healthcare'),
('Psychologist', 'Healthcare'),
('Physiotherapist', 'Healthcare'),
('Medical Assistant', 'Healthcare'),
('Home Health Aide', 'Healthcare'),
('Caregiver', 'Healthcare'),
('Teacher', 'Education'),
('Professor', 'Education'),
('Librarian', 'Education'),
('Tutor', 'Education'),
('School Counselor', 'Education'),
('Special Education Teacher', 'Education'),
('Software Engineer', 'Technology'),
('Data Scientist', 'Technology'),
('Cybersecurity Analyst', 'Technology'),
('Web Developer', 'Technology'),
('IT Technician', 'Technology'),
('Network Administrator', 'Technology'),
('Mechanical Engineer', 'Engineering'),
('Civil Engineer', 'Engineering'),
('Electrical Engineer', 'Engineering'),
('Robotics Engineer', 'Engineering'),
('Electrician', 'Skilled Trades'),
('Plumber', 'Skilled Trades'),
('Carpenter', 'Skilled Trades'),
('Construction Worker', 'Skilled Trades'),
('Welder', 'Skilled Trades'),
('Mechanic', 'Skilled Trades'),
('Truck Driver', 'Transportation'),
('Janitor', 'Service'),
('Garbage Collector', 'Service'),
('Factory Worker', 'Manufacturing'),
('Fisherman', 'Agriculture'),
('Miner', 'Skilled Trades'),
('Blacksmith', 'Skilled Trades'),
('Textile Worker', 'Manufacturing'),
('Handyman', 'Service'),
('Police Officer', 'Public Service'),
('Firefighter', 'Public Service'),
('Judge', 'Law'),
('Lawyer', 'Law'),
('Paralegal', 'Law'),
('Corrections Officer', 'Public Service'),
('Postal Worker', 'Public Service'),
('Security Guard', 'Public Service'),
('Military Officer', 'Military'),
('Soldier', 'Military'),
('Actor', 'Arts & Entertainment'),
('Musician', 'Arts & Entertainment'),
('Painter', 'Arts & Entertainment'),
('Photographer', 'Arts & Entertainment'),
('Journalist', 'Media'),
('Writer', 'Media'),
('Filmmaker', 'Media'),
('Graphic Designer', 'Arts & Entertainment'),
('Tattoo Artist', 'Arts & Entertainment'),
('Dancer', 'Arts & Entertainment'),
('Comedian', 'Arts & Entertainment'),
('Street Performer', 'Arts & Entertainment'),
('Accountant', 'Finance'),
('Bank Teller', 'Finance'),
('Financial Analyst', 'Finance'),
('Real Estate Agent', 'Business'),
('Stockbroker', 'Finance'),
('Entrepreneur', 'Business'),
('Business Consultant', 'Business'),
('Human Resources Manager', 'Business'),
('Retail Salesperson', 'Sales & Service'),
('Cashier', 'Sales & Service'),
('Waiter', 'Hospitality'),
('Bartender', 'Hospitality'),
('Hotel Receptionist', 'Hospitality'),
('Customer Service Representative', 'Sales & Service'),
('Call Center Agent', 'Sales & Service'),
('Chef', 'Food Industry'),
('Baker', 'Food Industry'),
('Butcher', 'Food Industry'),
('Food Delivery Driver', 'Transportation'),
('Barista', 'Food Industry'),
('Fast Food Worker', 'Food Industry'),
('Farmer', 'Agriculture'),
('Rancher', 'Agriculture'),
('Agricultural Worker', 'Agriculture'),
('Beekeeper', 'Agriculture'),
('Winemaker', 'Agriculture'),
('Fisherman', 'Agriculture'),
('Pilot', 'Transportation'),
('Flight Attendant', 'Transportation'),
('Taxi Driver', 'Transportation'),
('Courier', 'Transportation'),
('Dock Worker', 'Transportation'),
('Railway Worker', 'Transportation'),
('Scientist', 'Science & Research'),
('Researcher', 'Science & Research'),
('Lab Technician', 'Science & Research'),
('Archaeologist', 'Science & Research'),
('Biologist', 'Science & Research'),
('Astronomer', 'Science & Research'),
('Athlete', 'Sports & Fitness'),
('Personal Trainer', 'Sports & Fitness'),
('Sports Coach', 'Sports & Fitness'),
('Yoga Instructor', 'Sports & Fitness'),
('Referee', 'Sports & Fitness'),
('Street Vendor', 'Informal Work'),
('Housekeeper', 'Informal Work'),
('Babysitter', 'Informal Work'),
('Dog Walker', 'Informal Work'),
('Personal Assistant', 'Service'),
('Day Laborer', 'Informal Work'),
('Fortune Teller', 'Informal Work'),
('Clown', 'Entertainment'),
('Busker', 'Informal Work'),
('Escort', 'Informal Work'),
('Gambler', 'Informal Work'),
('Scavenger', 'Informal Work'),
('Student', 'Student');

INSERT INTO languages (language) VALUES
('English'),
('Spanish'),
('Armenian'),
('German'),
('Azerbaijani'),
('Bengali'),
('Dutch'),
('Portuguese'),
('Bulgarian'),
('Chinese'),
('Croatian'),
('Czech'),
('Danish'),
('Estonian'),
('Finnish'),
('French'),
('Georgian'),
('Greek'),
('Hungarian'),
('Hindi'),
('Indonesian'),
('Persian'),
('Irish'),
('Hebrew'),
('Italian'),
('Japanese'),
('Latvian'),
('Lithuanian'),
('Nepali'),
('Norwegian'),
('Polish'),
('Romanian'),
('Russian'),
('Slovak'),
('Slovenian'),
('Swedish'),
('Thai'),
('Turkish'),
('Ukrainian');

INSERT INTO nationalities (nationality) VALUES
('American'),
('Argentine'),
('Armenian'),
('Austrian'),
('Azerbaijani'),
('Bangladeshi'),
('Belgian'),
('Brazilian'),
('British'),
('Bulgarian'),
('Chilean'),
('Chinese'),
('Colombian'),
('Croatian'),
('Czech'),
('Danish'),
('Dutch'),
('Estonian'),
('Finnish'),
('French'),
('Georgian'),
('German'),
('Greek'),
('Hungarian'),
('Indian'),
('Indonesian'),
('Iranian'),
('Irish'),
('Israeli'),
('Italian'),
('Japanese'),
('Latvian'),
('Lithuanian'),
('Mexican'),
('Nepalese'),
('New Zealander'),
('Norwegian'),
('Palestinian'),
('Polish'),
('Portuguese'),
('Romanian'),
('Russian'),
('Saudi'),
('Slovak'),
('Slovenian'),
('South African'),
('South Korean'),
('Spanish'),
('Swedish'),
('Swiss'),
('Taiwanese'),
('Thai'),
('Turkish'),
('Ukrainian');


INSERT INTO activity_profiles (name, hours) VALUES
('Always On', '0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23'),
('Morning Enthusiast', '6,7,8,9,10,11,12'),
('Coffee Break User', '9,10,13,15,17'),
('News Tracker', '7,8,12,18,19,20'),
('Researcher Mode', '8,9,10,11,14,15,16,17'),
('Professional Broadcaster', '8,9,10,11,12,13,14,15,16,17'),
('Evening Commentator', '18,19,20,21,22,23'),
('Night Owl', '22,23,0,1,2,3'),
('Activist Pulse', '10,11,12,18,19,20,21'),
('Global Connector', '6,7,9,11,13,15,17,19,21,23,1,3'),
('Casual Scroller', '8,12,19,21'),
('Trend Surfer', '11,12,18,19,20,21'),
('Quiet Observer', '9,10,22,23'),
('Early Poster', '5,6,7,8,9'),
('Late Poster', '18,19,20,21,22'),
('Hyper Connected', '0,2,4,8,12,16,20,23'),
('Minimalist User', '12,18'),
('Community Builder', '8,9,10,11,18,19,20,21'),
('Storyteller', '10,11,12,13,19,20,21'),
('Casual Poster', '8,13,19');

-- -----------------------------
-- Log File Offsets for Incremental Reading
-- -----------------------------
CREATE TABLE log_file_offsets (
    id            SERIAL PRIMARY KEY,
    exp_id        INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    log_file_type VARCHAR(50) NOT NULL,  -- 'server' or 'client'
    client_id     INTEGER REFERENCES client(id) ON DELETE CASCADE,  -- NULL for server logs
    file_path     VARCHAR(500) NOT NULL,
    last_offset   BIGINT NOT NULL DEFAULT 0,
    last_updated  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_log_file_offset_lookup ON log_file_offsets(exp_id, log_file_type, client_id);

-- -----------------------------
-- Server Log Metrics (Aggregated)
-- -----------------------------
CREATE TABLE server_log_metrics (
    id                SERIAL PRIMARY KEY,
    exp_id            INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    aggregation_level VARCHAR(10) NOT NULL,  -- 'daily' or 'hourly'
    day               INTEGER NOT NULL,
    hour              INTEGER,  -- NULL for daily aggregation
    path              VARCHAR(200) NOT NULL,
    call_count        INTEGER NOT NULL DEFAULT 0,
    total_duration    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    min_time          TIMESTAMP,
    max_time          TIMESTAMP
);
CREATE INDEX idx_server_log_metrics_lookup ON server_log_metrics(exp_id, aggregation_level, day, hour, path);

-- -----------------------------
-- Client Log Metrics (Aggregated)
-- -----------------------------
CREATE TABLE client_log_metrics (
    id                   SERIAL PRIMARY KEY,
    exp_id               INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    client_id            INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    aggregation_level    VARCHAR(10) NOT NULL,  -- 'daily' or 'hourly'
    day                  INTEGER NOT NULL,
    hour                 INTEGER,  -- NULL for daily aggregation
    method_name          VARCHAR(200) NOT NULL,
    call_count           INTEGER NOT NULL DEFAULT 0,
    total_execution_time DOUBLE PRECISION NOT NULL DEFAULT 0.0
);
CREATE INDEX idx_client_log_metrics_lookup ON client_log_metrics(exp_id, client_id, aggregation_level, day, hour, method_name);