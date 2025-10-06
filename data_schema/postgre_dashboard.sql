CREATE TABLE admin_users (
    id              SERIAL PRIMARY KEY,
    username        TEXT,
    email           TEXT,
    password        TEXT,
    last_seen       TEXT,
    role            TEXT,
    llm             TEXT DEFAULT '',
    llm_url         TEXT DEFAULT '',
    profile_pic     TEXT DEFAULT '',
    perspective_api TEXT DEFAULT NULL
);

CREATE TABLE agents (
    id                   SERIAL PRIMARY KEY,
    name                 TEXT NOT NULL,
    ag_type              TEXT NOT NULL,
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
    profession           TEXT
);

CREATE TABLE agent_profile (
    id       SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    profile  TEXT
);

CREATE TABLE content_recsys (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE education (
    id              SERIAL PRIMARY KEY,
    education_level TEXT NOT NULL
);

CREATE TABLE exps (
    idexp         SERIAL PRIMARY KEY,
    exp_name      TEXT,
    db_name       TEXT,
    owner         TEXT,
    exp_descr     TEXT,
    status        INTEGER DEFAULT 0,
    running       INTEGER DEFAULT 0 NOT NULL,
    port          INTEGER NOT NULL,
    server        TEXT DEFAULT '127.0.0.1',
    platform_type TEXT DEFAULT 'microblogging'
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

CREATE TABLE follow_recsys (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE languages (
    id       SERIAL PRIMARY KEY,
    language TEXT NOT NULL
);

CREATE TABLE leanings (
    id      SERIAL PRIMARY KEY,
    leaning TEXT NOT NULL
);

CREATE TABLE nationalities (
    id          SERIAL PRIMARY KEY,
    nationality TEXT NOT NULL
);

CREATE TABLE toxicity_levels (
    id             SERIAL PRIMARY KEY,
    toxicity_level TEXT NOT NULL
);

CREATE TABLE ollama_pull (
    id         SERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    status     REAL DEFAULT 0 NOT NULL
);

CREATE TABLE pages (
    id        SERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    descr     TEXT,
    page_type TEXT NOT NULL,
    feed      TEXT,
    keywords  TEXT,
    logo      TEXT,
    pg_type   TEXT,
    leaning   TEXT DEFAULT ''
);

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
    crecsys       TEXT
);

CREATE TABLE agent_population (
    id            SERIAL PRIMARY KEY,
    agent_id      INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    population_id INTEGER NOT NULL REFERENCES population(id) ON DELETE CASCADE
);

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
    share_link                          REAL DEFAULT 0
);

CREATE TABLE client_execution (
    id                       SERIAL PRIMARY KEY,
    elapsed_time             INTEGER DEFAULT 0 NOT NULL,
    client_id                INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    expected_duration_rounds INTEGER NOT NULL,
    last_active_hour         INTEGER NOT NULL,
    last_active_day          INTEGER NOT NULL
);

CREATE TABLE page_population (
    id            SERIAL PRIMARY KEY,
    page_id       INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    population_id INTEGER NOT NULL REFERENCES population(id) ON DELETE CASCADE
);

CREATE TABLE population_experiment (
    id            SERIAL PRIMARY KEY,
    id_exp        INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    id_population INTEGER NOT NULL REFERENCES population(id) ON DELETE CASCADE
);

CREATE TABLE professions (
    id         SERIAL PRIMARY KEY,
    profession TEXT NOT NULL,
    background TEXT NOT NULL
);

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
('Scavenger', 'Informal Work');

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
