"""
Administrative ORM models for YSocial.

All models in this module are bound to the ``db_admin`` database.
They represent researcher/admin accounts, experiment metadata, client
configurations, populations, agents, and infrastructure tracking tables.
"""

from flask_login import UserMixin

from y_web import db


class Admin_users(UserMixin, db.Model):
    """
    Administrative user accounts.

    Manages user accounts for the YSocial dashboard, including authentication,
    roles, LLM preferences, and API keys for external services.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "admin_users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), nullable=False, unique=True)
    email = db.Column(db.String(50), nullable=False, unique=True)
    password = db.Column(db.String(80), nullable=False)
    last_seen = db.Column(db.String(30), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    llm = db.Column(db.String(50), default="")
    llm_url = db.Column(db.String(200), default="")
    profile_pic = db.Column(db.String(400), default="")
    perspective_api = db.Column(db.String(300), default=None)
    telemetry_enabled = db.Column(db.Boolean, default=True)
    telemetry_notice_shown = db.Column(db.Boolean, default=False)
    tutorial_shown = db.Column(db.Boolean, default=False)
    exp_details_tutorial_shown = db.Column(db.Boolean, default=False)

    def get_id(self):
        """Return user ID with 'admin_' prefix for Flask-Login."""
        return f"admin_{self.id}"


class AdminInterviewSession(db.Model):
    """
    Stores an admin interview session for a specific experiment and agent.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "admin_interview_sessions"

    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(db.Integer, nullable=False, index=True)
    admin_username = db.Column(db.String(50), nullable=False, index=True)

    agent_user_id = db.Column(db.Integer, nullable=False)
    agent_username = db.Column(db.String(50), nullable=False)

    run_id = db.Column(db.Text, nullable=True, index=True)

    backend_mode = db.Column(db.String(20), nullable=False, default="agent_runtime")
    llm_model = db.Column(db.String(200), nullable=True)
    llm_base_url = db.Column(db.String(300), nullable=True)

    persona_snapshot = db.Column(db.Text, nullable=True)
    interests_snapshot_json = db.Column(db.Text, nullable=True)
    memory_snapshot_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.now(),
        onupdate=db.func.now(),
    )

    messages = db.relationship(
        "AdminInterviewMessage",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan",
    )


class AdminInterviewMessage(db.Model):
    """Stores one message in an admin interview session."""

    __bind_key__ = "db_admin"
    __tablename__ = "admin_interview_messages"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("admin_interview_sessions.id"),
        nullable=False,
        index=True,
    )
    role = db.Column(db.String(12), nullable=False)
    content = db.Column(db.Text, nullable=False)
    meta_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())


class Exps(db.Model):
    """
    Experiment configuration and metadata.

    Defines simulation experiments including platform type (microblogging/reddit),
    database connections, ownership, status tracking, and server configuration.

    exp_status values:
    - "stopped": Experiment is not running (default)
    - "active": Experiment server is running
    - "completed": All clients have finished execution
    - "scheduled": Experiment is scheduled to run
    """

    __bind_key__ = "db_admin"
    __tablename__ = "exps"
    idexp = db.Column(db.Integer, primary_key=True, autoincrement=True)
    platform_type = db.Column(db.String(50), nullable=False, default="microblogging")
    exp_name = db.Column(db.String(50), nullable=False)
    db_name = db.Column(db.String(50), nullable=False)
    owner = db.Column(db.String(50), nullable=False)
    exp_descr = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Integer, nullable=False)
    running = db.Column(db.Integer, nullable=False, default=0)
    port = db.Column(db.Integer, nullable=False)
    server = db.Column(db.String(50), nullable=False, default="127.0.0.1")
    annotations = db.Column(db.String(500), nullable=False, default="")
    server_pid = db.Column(db.Integer, nullable=True, default=None)
    llm_agents_enabled = db.Column(db.Integer, nullable=False, default=1)
    exp_status = db.Column(db.String(20), nullable=False, default="stopped")
    simulator_type = db.Column(db.String(20), nullable=False, default="Standard")
    is_remote = db.Column(db.Integer, nullable=False, default=0)
    exp_group = db.Column(db.String(100), nullable=True, default="")


class ExperimentScheduleGroup(db.Model):
    """
    Experiment schedule group for batch execution.

    Groups experiments together for sequential execution as part of a schedule.
    Experiments in the same group run in parallel, groups run sequentially.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "experiment_schedule_groups"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    is_completed = db.Column(db.Integer, nullable=False, default=0)


class ExperimentScheduleItem(db.Model):
    """
    Links experiments to schedule groups.

    Associates experiments with groups for scheduled batch execution.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "experiment_schedule_items"
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer,
        db.ForeignKey("experiment_schedule_groups.id"),
        nullable=False,
    )
    experiment_id = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=0)


class ExperimentScheduleStatus(db.Model):
    """
    Tracks the status of scheduled experiment execution.

    Monitors which group is currently running and overall schedule state.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "experiment_schedule_status"
    id = db.Column(db.Integer, primary_key=True)
    is_running = db.Column(db.Integer, nullable=False, default=0)
    current_group_id = db.Column(db.Integer, nullable=True, default=None)
    started_at = db.Column(db.DateTime, nullable=True, default=None)


class ExperimentScheduleLog(db.Model):
    """
    Stores execution logs for the experiment schedule.

    Persists log messages so they are available across page navigations.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "experiment_schedule_logs"
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    log_type = db.Column(db.String(20), nullable=False, default="info")


class Exp_stats(db.Model):
    """
    Experiment statistics tracking.

    Aggregates key metrics for experiments including total rounds, agents,
    posts, reactions, and mentions for monitoring simulation progress.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "exp_stats"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)
    rounds = db.Column(db.Integer, nullable=False)
    agents = db.Column(db.Integer, nullable=False)
    posts = db.Column(db.Integer, nullable=False)
    reactions = db.Column(db.Integer, nullable=False)
    mentions = db.Column(db.Integer, nullable=False)


class Population(db.Model):
    """
    Agent population configuration.

    Defines groups of agents with shared characteristics including demographics
    (age, education, nationality), personality traits, interests, toxicity levels,
    language preferences, and recommendation system settings.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "population"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    descr = db.Column(db.String(200), nullable=False)
    size = db.Column(db.Integer)
    llm = db.Column(db.String(50))
    age_min = db.Column(db.Integer)
    age_max = db.Column(db.Integer)
    education = db.Column(db.String(100))
    leanings = db.Column(db.String(200))
    nationalities = db.Column(db.String(200))
    interests = db.Column(db.String(300))
    toxicity = db.Column(db.String(50))
    languages = db.Column(db.String(100))
    crecsys = db.Column(db.String(50))
    frecsys = db.Column(db.String(50))
    llm_url = db.Column(db.String(100))
    username_type = db.Column(db.String(50), nullable=False, default="microblogging")
    pop_type = db.Column(db.String(50), nullable=True, default=None)


class Agent(db.Model):
    """
    Individual AI agent profile.

    Represents an AI-driven social media user with complete demographic profile,
    Big Five personality traits (oe, co, ex, ag, ne), political leaning,
    toxicity level, and behavioral settings for simulation participation.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "agents"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    ag_type = db.Column(db.String(50), nullable=True)
    gender = db.Column(db.String(10))
    leaning = db.Column(db.String(50))
    age = db.Column(db.Integer)
    education_level = db.Column(db.String(50))
    oe = db.Column(db.String(50))
    co = db.Column(db.String(50))
    ex = db.Column(db.String(50))
    ag = db.Column(db.String(50))
    ne = db.Column(db.String(50))
    language = db.Column(db.String(10))
    toxicity = db.Column(db.String(50))
    round_actions = db.Column(db.String(50))
    nationality = db.Column(db.String(50))
    crecsys = db.Column(db.String(50))
    frecsys = db.Column(db.String(50))
    profile_pic = db.Column(db.String(400), default="")
    daily_activity_level = db.Column(db.Integer, default=1)
    profession = db.Column(db.String(50), default="")
    activity_profile = db.Column(
        db.Integer, db.ForeignKey("activity_profiles.id"), nullable=True
    )
    archetype = db.Column(db.String(50), nullable=True, default=None)


class Agent_Ext(db.Model):
    """Stores plugin-specific agent features outside the core agent schema."""

    __bind_key__ = "db_admin"
    __tablename__ = "agent_ext"
    agent_id = db.Column(
        db.Integer, db.ForeignKey("agents.id"), primary_key=True, nullable=False
    )
    feature_name = db.Column(db.String(100), primary_key=True, nullable=False)
    feature_value = db.Column(db.Text, nullable=True)


class Agent_Custom_Feature(db.Model):
    """Stores structured agent interests, opinions, and custom key/value features."""

    __bind_key__ = "db_admin"
    __tablename__ = "agents_custom_features"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(
        db.Integer, db.ForeignKey("agents.id"), nullable=False, index=True
    )
    feature_type = db.Column(db.String(20), nullable=False)
    key = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Text, nullable=True)


class Agent_Population(db.Model):
    """Association table linking agents to populations."""

    __bind_key__ = "db_admin"
    __tablename__ = "agent_population"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=False)
    population_id = db.Column(
        db.Integer, db.ForeignKey("population.id"), nullable=False
    )


class Agent_Profile(db.Model):
    """Extended textual profile information for agents."""

    __bind_key__ = "db_admin"
    __tablename__ = "agent_profile"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=False)
    profile = db.Column(db.String(300))


class Page(db.Model):
    """
    Page/news organization accounts.

    Represents institutional accounts (news outlets, organizations) that
    generate content from RSS feeds with specific topics, political leanings,
    and visual branding.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "pages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    descr = db.Column(db.String(200))
    page_type = db.Column(db.String(50), nullable=False)
    feed = db.Column(db.String(200))
    keywords = db.Column(db.String(200))
    logo = db.Column(db.String(300))
    pg_type = db.Column(db.String(100))
    leaning = db.Column(db.String(50), default="")
    activity_profile = db.Column(
        db.Integer, db.ForeignKey("activity_profiles.id"), nullable=True
    )


class ForumRssFeedResource(db.Model):
    """Reusable RSS feed definitions for forum experiments."""

    __bind_key__ = "db_admin"
    __tablename__ = "forum_rss_feed_resources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    feed_url = db.Column(db.String(500), nullable=False, unique=True)
    url_site = db.Column(db.String(500), nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.now(),
        onupdate=db.func.now(),
    )


class ForumImageFeedResource(db.Model):
    """Reusable subreddit-backed image feed definitions for forum experiments."""

    __bind_key__ = "db_admin"
    __tablename__ = "forum_image_feed_resources"

    id = db.Column(db.Integer, primary_key=True)
    subreddit = db.Column(db.String(200), nullable=False, unique=True)
    interests = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=db.func.now(),
        onupdate=db.func.now(),
    )


class Population_Experiment(db.Model):
    """Association table linking populations to experiments."""

    __bind_key__ = "db_admin"
    __tablename__ = "population_experiment"
    id = db.Column(db.Integer, primary_key=True)
    id_population = db.Column(
        db.Integer, db.ForeignKey("population.id"), nullable=False
    )
    id_exp = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)


class Page_Population(db.Model):
    """Association table linking pages to populations."""

    __bind_key__ = "db_admin"
    __tablename__ = "page_population"
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("pages.id"), nullable=False)
    population_id = db.Column(
        db.Integer, db.ForeignKey("population.id"), nullable=False
    )


class User_Experiment(db.Model):
    """Association table linking admin users to experiments."""

    __bind_key__ = "db_admin"
    __tablename__ = "user_experiment"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=False)
    exp_id = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)


class Client(db.Model):
    """
    Simulation client configuration.

    Defines simulation parameters including agent behavior probabilities
    (posting, sharing, commenting, reading), attention window, LLM settings
    for content generation, network topology configuration, and recommendation
    system settings for both content and follow recommendations.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "client"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    descr = db.Column(db.String(200))
    days = db.Column(db.Integer)
    percentage_new_agents_iteration = db.Column(db.REAL)
    percentage_removed_agents_iteration = db.Column(db.REAL)
    max_length_thread_reading = db.Column(db.Integer)
    reading_from_follower_ratio = db.Column(db.REAL)
    probability_of_daily_follow = db.Column(db.REAL)
    attention_window = db.Column(db.Integer)
    visibility_rounds = db.Column(db.Integer)
    post = db.Column(db.REAL)
    share = db.Column(db.REAL)
    image = db.Column(db.REAL)
    comment = db.Column(db.REAL)
    read = db.Column(db.REAL)
    news = db.Column(db.REAL)
    search = db.Column(db.REAL)
    vote = db.Column(db.REAL)
    share_link = db.Column(db.REAL)
    follow = db.Column(db.REAL, default=0.0)
    llm = db.Column(db.String(100))
    llm_api_key = db.Column(db.String(300))
    llm_max_tokens = db.Column(db.Integer)
    llm_temperature = db.Column(db.REAL)
    llm_v_agent = db.Column(db.String(100))
    llm_v = db.Column(db.String(100))
    llm_v_api_key = db.Column(db.String(300))
    llm_v_max_tokens = db.Column(db.Integer)
    llm_v_temperature = db.Column(db.REAL)
    status = db.Column(db.Integer, nullable=False, default=0)
    id_exp = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)
    probability_of_secondary_follow = db.Column(db.REAL, default=0.0)
    population_id = db.Column(
        db.Integer, db.ForeignKey("population.id"), nullable=False
    )
    network_type = db.Column(db.String(50), default="")
    crecsys = db.Column(db.String(50))
    frecsys = db.Column(db.String(50))
    pid = db.Column(db.Integer, nullable=True, default=None)
    # Agent archetype percentages
    archetype_validator = db.Column(db.REAL, default=0.52)
    archetype_broadcaster = db.Column(db.REAL, default=0.20)
    archetype_explorer = db.Column(db.REAL, default=0.28)
    # Transition probabilities (3x3 matrix)
    trans_val_val = db.Column(db.REAL, default=0.853)
    trans_val_broad = db.Column(db.REAL, default=0.081)
    trans_val_expl = db.Column(db.REAL, default=0.066)
    trans_broad_broad = db.Column(db.REAL, default=0.729)
    trans_broad_val = db.Column(db.REAL, default=0.195)
    trans_broad_expl = db.Column(db.REAL, default=0.075)
    trans_expl_expl = db.Column(db.REAL, default=0.490)
    trans_expl_val = db.Column(db.REAL, default=0.364)
    trans_expl_broad = db.Column(db.REAL, default=0.146)


class Client_Execution(db.Model):
    """
    Client execution state tracking.

    Monitors simulation progress including elapsed time, expected duration,
    and current time position (day/hour) for running simulations.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "client_execution"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    elapsed_time = db.Column(db.Integer, default=0)
    expected_duration_rounds = db.Column(db.Integer, default=0)
    last_active_hour = db.Column(db.Integer, default=-1)
    last_active_day = db.Column(db.Integer, default=-1)


class Ollama_Pull(db.Model):
    """
    Ollama model download tracking.

    Tracks status of LLM model downloads from Ollama registry,
    with progress percentage for monitoring long-running downloads.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "ollama_pull"
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(50), nullable=False)
    status = db.Column(db.REAL, nullable=False, default=0)


class Jupyter_instances(db.Model):
    """
    Jupyter Lab instance tracking.

    Stores information about running Jupyter Lab instances including
    instance ID, notebook directory, port, and start time.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "jupyter_instances"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    notebook_dir = db.Column(db.String(300), nullable=False)
    process = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="stopped")


class ReleaseInfo(db.Model):
    """
    Latest YSocial release information.

    Stores information about the latest available YSocial release for
    update notifications. Single-row table updated on each application startup.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "release_info"
    id = db.Column(db.Integer, primary_key=True)
    latest_version_tag = db.Column(db.String(50), nullable=True)
    release_name = db.Column(db.String(200), nullable=True)
    published_at = db.Column(db.String(50), nullable=True)
    download_url = db.Column(db.String(500), nullable=True)
    size = db.Column(db.String(50), nullable=True)
    sha256 = db.Column(db.String(100), nullable=True)
    latest_check_on = db.Column(db.String(50), nullable=True)


class BlogPost(db.Model):
    """
    Latest blog post information.

    Stores information about the latest blog post from y-not.social/blog
    for announcement notifications. Tracks read status per post.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=True)
    published_at = db.Column(db.String(50), nullable=True)
    link = db.Column(db.String(500), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    latest_check_on = db.Column(db.String(50), nullable=True)


class DownloadNotification(db.Model):
    """
    Async download notification for admin users.

    Tracks long-running archive generation jobs and stores links to generated
    resources in temp_data so users can download when ready.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "download_notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(
        db.String(20), nullable=False, default="processing"
    )  # processing|ready|failed|cancelled
    resource_path = db.Column(db.String(500), nullable=True)
    resource_name = db.Column(db.String(255), nullable=True)
    error_message = db.Column(db.String(500), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    updated_at = db.Column(
        db.DateTime, nullable=False, default=db.func.now(), onupdate=db.func.now()
    )


class LogFileOffset(db.Model):
    """
    Track last read offset for log files to enable incremental reading.

    Stores the byte offset of the last successfully processed position
    in each log file, allowing the system to read only new entries on
    subsequent updates.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "log_file_offsets"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(
        db.Integer, db.ForeignKey("exps.idexp", ondelete="CASCADE"), nullable=False
    )
    log_file_type = db.Column(db.String(50), nullable=False)  # 'server', 'client'
    client_id = db.Column(
        db.Integer, db.ForeignKey("client.id", ondelete="CASCADE"), nullable=True
    )  # NULL for server logs
    file_path = db.Column(
        db.String(500), nullable=False
    )  # relative path from experiment folder
    last_offset = db.Column(
        db.BigInteger, nullable=False, default=0
    )  # byte offset in file
    last_updated = db.Column(db.DateTime, nullable=False)  # timestamp of last update


class ServerLogMetrics(db.Model):
    """
    Aggregated metrics from server log files.

    Stores pre-computed aggregations of server API call metrics including
    call counts, total durations, and timing information. Supports both
    daily and hourly aggregation levels.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "server_log_metrics"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(
        db.Integer, db.ForeignKey("exps.idexp", ondelete="CASCADE"), nullable=False
    )
    aggregation_level = db.Column(db.String(10), nullable=False)  # 'daily' or 'hourly'
    day = db.Column(db.Integer, nullable=False)
    hour = db.Column(db.Integer, nullable=True)  # NULL for daily aggregation
    path = db.Column(db.String(200), nullable=False)  # API path
    call_count = db.Column(db.Integer, nullable=False, default=0)
    total_duration = db.Column(
        db.Float, nullable=False, default=0.0
    )  # sum of all durations
    min_time = db.Column(db.DateTime, nullable=True)  # earliest timestamp
    max_time = db.Column(db.DateTime, nullable=True)  # latest timestamp


class ClientLogMetrics(db.Model):
    """
    Aggregated metrics from client log files.

    Stores pre-computed aggregations of client method execution metrics
    including call counts and execution times. Supports both daily and
    hourly aggregation levels.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "client_log_metrics"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(
        db.Integer, db.ForeignKey("exps.idexp", ondelete="CASCADE"), nullable=False
    )
    client_id = db.Column(
        db.Integer, db.ForeignKey("client.id", ondelete="CASCADE"), nullable=False
    )
    aggregation_level = db.Column(db.String(10), nullable=False)  # 'daily' or 'hourly'
    day = db.Column(db.Integer, nullable=False)
    hour = db.Column(db.Integer, nullable=True)  # NULL for daily aggregation
    method_name = db.Column(db.String(200), nullable=False)
    call_count = db.Column(db.Integer, nullable=False, default=0)
    total_execution_time = db.Column(
        db.Float, nullable=False, default=0.0
    )  # sum of all execution times
    __table_args__ = (
        db.Index(
            "idx_client_log_metrics_lookup",
            "exp_id",
            "client_id",
            "aggregation_level",
            "day",
            "hour",
            "method_name",
        ),
        {"extend_existing": True},
    )


# Add indexes to ServerLogMetrics
ServerLogMetrics.__table_args__ = (
    db.Index(
        "idx_server_log_metrics_lookup",
        "exp_id",
        "aggregation_level",
        "day",
        "hour",
        "path",
    ),
    {"extend_existing": True},
)

# Add index to LogFileOffset
LogFileOffset.__table_args__ = (
    db.Index("idx_log_file_offset_lookup", "exp_id", "log_file_type", "client_id"),
    {"extend_existing": True},
)


class HpcMonitorSettings(db.Model):
    """
    Settings for HPC client execution monitoring.

    Stores configuration for the HPC monitor including whether it's enabled
    and the check frequency in seconds.
    Single-row table that is created on first access if it doesn't exist.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "hpc_monitor_settings"
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    check_interval_seconds = db.Column(
        db.Integer, nullable=False, default=5
    )  # Default 5 seconds
    last_check = db.Column(db.DateTime, nullable=True)  # Last time check was performed


class WatchdogSettings(db.Model):
    """
    Settings for the process watchdog that monitors server/client processes.

    Stores configuration for the watchdog scheduler including whether it's
    enabled, the check interval in minutes, and the last run timestamp.
    Single-row table that is created on first access if it doesn't exist.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "watchdog_settings"
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    run_interval_minutes = db.Column(
        db.Integer, nullable=False, default=15
    )  # Default 15 minutes
    last_run = db.Column(db.DateTime, nullable=True)  # Last time watchdog ran


class OpinionGroup(db.Model):
    """
    Opinion group definitions for opinion dynamics simulations.

    Defines groups of opinions with a name and value range [lower_bound, upper_bound]
    where bounds are in the interval [0, 1].
    """

    __bind_key__ = "db_admin"
    __tablename__ = "opinion_groups"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    lower_bound = db.Column(db.Float, nullable=False)
    upper_bound = db.Column(db.Float, nullable=False)


class OpinionDistribution(db.Model):
    """
    Opinion distribution configurations for opinion dynamics simulations.

    Stores distribution types (uniform, beta, etc.) and their parameters
    as a JSON string for flexible configuration of opinion initialization.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "opinion_distributions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    distribution_type = db.Column(db.String(50), nullable=False)
    parameters = db.Column(db.Text, nullable=False)  # JSON string


class OpinionEvolutionCache(db.Model):
    """
    Cache table for opinion evolution statistics to optimize animation performance.

    Stores pre-computed statistics for each (experiment, day, hour, topic) combination
    to avoid re-querying and re-processing large datasets during animation playback.

    Supports incremental computation: stores latest_opinions state to allow updating
    from a previous cached state rather than recomputing from scratch.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "opinion_evolution_cache"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(
        db.Integer, db.ForeignKey("exps.idexp"), nullable=False, index=True
    )
    day = db.Column(db.Integer, nullable=False, index=True)
    hour = db.Column(db.Integer, nullable=False, index=True)
    topic_id = db.Column(db.Integer, nullable=True, index=True)  # NULL for all topics

    # Pre-computed statistics
    total_opinions = db.Column(db.Integer, nullable=False)
    social_interactions = db.Column(db.Integer, nullable=False)
    unique_agents = db.Column(db.Integer, nullable=False)

    # Binned opinion data (JSON string: {group_name: count})
    binned_data = db.Column(db.Text, nullable=False)

    # Latest opinions state for incremental computation
    # JSON string: {agent_id: {topic_id: {"opinion": float, "day": int, "hour": int}}}
    latest_opinions_state = db.Column(db.Text, nullable=True)

    # Timestamp for cache invalidation
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    # Composite index for fast lookups
    __table_args__ = (
        db.Index("idx_cache_lookup", "exp_id", "day", "hour", "topic_id"),
    )


class OpinionEvolutionSampledAgents(db.Model):
    """
    Stores sampled agent IDs for opinion evolution visualization.

    To maintain stable and efficient visualizations, agents are sampled once
    per (experiment, topic, sample_percentage) combination and reused across
    all animation frames, rather than re-sampling on each frame.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "opinion_evolution_sampled_agents"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(
        db.Integer, db.ForeignKey("exps.idexp"), nullable=False, index=True
    )
    topic_id = db.Column(
        db.String(50), nullable=True, index=True
    )  # NULL for all topics, String to support UUID in HPC
    sample_percentage = db.Column(db.Integer, nullable=False, index=True)

    # JSON array of sampled agent IDs
    sampled_agent_ids = db.Column(db.Text, nullable=False)

    # Timestamp for cache invalidation
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    # Composite unique index to ensure one sample set per combination
    __table_args__ = (
        db.Index(
            "idx_sampled_agents_lookup", "exp_id", "topic_id", "sample_percentage"
        ),
    )
