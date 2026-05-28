"""
Lookup / configuration ORM models for YSocial.

These models are bound to the ``db_admin`` database and contain reference
data used when building experiment populations and agents: available
professions, nationalities, education levels, political leanings, languages,
toxicity levels, age classes, recommendation system options, topic lists,
and activity profiles.
"""

from y_web import db


class Profession(db.Model):
    """Professional occupation definitions with background context."""

    __bind__ = "db_admin"
    __tablename__ = "professions"
    id = db.Column(db.Integer, primary_key=True)
    profession = db.Column(db.String(50), nullable=False)
    background = db.Column(db.String(200), nullable=False)


class Nationalities(db.Model):
    """Available nationality options for agent profiles."""

    __bind__ = "db_admin"
    __tablename__ = "nationalities"
    id = db.Column(db.Integer, primary_key=True)
    nationality = db.Column(db.String(50), nullable=False)


class Education(db.Model):
    """Available education level options for agent profiles."""

    __bind__ = "db_admin"
    __tablename__ = "education"
    id = db.Column(db.Integer, primary_key=True)
    education_level = db.Column(db.String(50), nullable=False)


class Leanings(db.Model):
    """Available political leaning options for agent and page profiles."""

    __bind__ = "db_admin"
    __tablename__ = "leanings"
    id = db.Column(db.Integer, primary_key=True)
    leaning = db.Column(db.String(50), nullable=False)


class Languages(db.Model):
    """Available language options for agent profiles and content."""

    __bind__ = "db_admin"
    __tablename__ = "languages"
    id = db.Column(db.Integer, primary_key=True)
    language = db.Column(db.String(50), nullable=False)


class Toxicity_Levels(db.Model):
    """Available toxicity level options for agent profiles."""

    __bind__ = "db_admin"
    __tablename__ = "toxicity_levels"
    id = db.Column(db.Integer, primary_key=True)
    toxicity_level = db.Column(db.String(50), nullable=False)


class AgeClass(db.Model):
    """Available age class options for agent profiles with age ranges."""

    __bind__ = "db_admin"
    __tablename__ = "age_classes"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    age_start = db.Column(db.Integer, nullable=False)
    age_end = db.Column(db.Integer, nullable=False)


class Content_Recsys(db.Model):
    """Content recommendation system configuration options."""

    __bind__ = "db_admin"
    __tablename__ = "content_recsys"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    enabled = db.Column(db.String(100), nullable=True)


class Follow_Recsys(db.Model):
    """Follower recommendation system configuration options."""

    __bind__ = "db_admin"
    __tablename__ = "follow_recsys"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    enabled = db.Column(db.String(100), nullable=True)


class Topic_List(db.Model):
    """Master list of available topics for experiments and content."""

    __bind_key__ = "db_admin"
    __tablename__ = "topic_list"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)


class Exp_Topic(db.Model):
    """Association table linking experiments with topics."""

    __bind_key__ = "db_admin"
    __tablename__ = "exp_topic"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topic_list.id"), nullable=False)


class Page_Topic(db.Model):
    """Association table linking pages with topics."""

    __bind_key__ = "db_admin"
    __tablename__ = "page_topic"
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("pages.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("topic_list.id"), nullable=False)


class ActivityProfile(db.Model):
    """
    Hourly activity profiles for social media agents.

    Defines when agents are active during a 24-hour period. Each profile
    stores a comma-separated list of hours (0-23) representing active hours.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "activity_profiles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    hours = db.Column(
        db.String(100), nullable=False
    )  # Comma-separated list of active hours

    def to_dict(self):
        return {"id": self.id, "name": self.name, "hours": self.hours}


class PopulationActivityProfile(db.Model):
    """
    Association table linking a population with an activity profile.
    Defines what percentage of the population follows a given profile.
    """

    __bind_key__ = "db_admin"
    __tablename__ = "population_activity_profile"

    id = db.Column(db.Integer, primary_key=True)
    population = db.Column(
        db.Integer, db.ForeignKey("population.id", ondelete="CASCADE"), nullable=False
    )
    activity_profile = db.Column(
        db.Integer,
        db.ForeignKey("activity_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    percentage = db.Column(db.Float, nullable=False)
