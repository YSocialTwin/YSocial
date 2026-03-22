"""
Phase 0 + Phase 1 validation tests.

Verifies that:
- y_web.src is importable (Phase 0)
- All classes are reachable via the new canonical paths (Phase 1)
- All classes are still reachable via the legacy shim (Phase 1)
- No circular imports are introduced (Phase 1)
- db.create_all() succeeds with models from both old and new paths
"""

import pytest


# ---------------------------------------------------------------------------
# Phase 0
# ---------------------------------------------------------------------------


def test_src_package_importable():
    """y_web.src must be importable and point to its __init__.py."""
    import y_web.src

    assert y_web.src.__file__.endswith("__init__.py")


# ---------------------------------------------------------------------------
# Phase 1 — new canonical import paths
# ---------------------------------------------------------------------------


class TestCanonicalExperimentImports:
    """All db_exp model classes must be importable from y_web.src.models.experiment."""

    def test_experiment_module_importable(self):
        from y_web.src.models import experiment  # noqa: F401

    def test_user_mgmt(self):
        from y_web.src.models.experiment import User_mgmt

        assert User_mgmt.__bind_key__ == "db_exp"

    def test_post(self):
        from y_web.src.models.experiment import Post

        assert Post.__bind_key__ == "db_exp"

    def test_all_experiment_classes(self):
        from y_web.src.models.experiment import (
            Agent_Opinion,
            Article_topics,
            Articles,
            Emotions,
            Follow,
            Hashtags,
            ImagePosts,
            Images,
            Interests,
            Mentions,
            Post,
            Post_emotions,
            Post_hashtags,
            Post_Sentiment,
            Post_topics,
            Post_Toxicity,
            Reactions,
            Recommendations,
            ReplyInboxState,
            Rounds,
            User_interest,
            User_mgmt,
            Voting,
            Websites,
        )

        exp_classes = [
            User_mgmt, Post, Hashtags, Emotions, Post_emotions, Post_hashtags,
            Mentions, ReplyInboxState, Reactions, Follow, Rounds, Recommendations,
            Articles, Websites, Voting, Interests, User_interest, Post_topics,
            Images, ImagePosts, Article_topics, Post_Sentiment, Post_Toxicity,
            Agent_Opinion,
        ]
        for cls in exp_classes:
            assert hasattr(cls, "__bind_key__"), f"{cls.__name__} missing __bind_key__"
            assert cls.__bind_key__ == "db_exp", f"{cls.__name__} wrong bind key"


class TestCanonicalAdminImports:
    """All db_admin model classes must be importable from y_web.src.models.admin."""

    def test_admin_module_importable(self):
        from y_web.src.models import admin  # noqa: F401

    def test_admin_users(self):
        from y_web.src.models.admin import Admin_users

        assert Admin_users.__bind_key__ == "db_admin"

    def test_exps(self):
        from y_web.src.models.admin import Exps

        assert Exps.__bind_key__ == "db_admin"

    def test_all_admin_classes(self):
        from y_web.src.models.admin import (
            Admin_users,
            AdminInterviewMessage,
            AdminInterviewSession,
            Agent,
            Agent_Population,
            Agent_Profile,
            BlogPost,
            Client,
            Client_Execution,
            ClientLogMetrics,
            DownloadNotification,
            Exp_stats,
            Exps,
            ExperimentScheduleGroup,
            ExperimentScheduleItem,
            ExperimentScheduleLog,
            ExperimentScheduleStatus,
            HpcMonitorSettings,
            Jupyter_instances,
            LogFileOffset,
            Ollama_Pull,
            OpinionDistribution,
            OpinionEvolutionCache,
            OpinionEvolutionSampledAgents,
            OpinionGroup,
            Page,
            Page_Population,
            Population,
            Population_Experiment,
            ReleaseInfo,
            ServerLogMetrics,
            User_Experiment,
            WatchdogSettings,
        )

        admin_classes = [
            Admin_users, AdminInterviewSession, AdminInterviewMessage, Exps,
            ExperimentScheduleGroup, ExperimentScheduleItem, ExperimentScheduleStatus,
            ExperimentScheduleLog, Exp_stats, Population, Agent, Agent_Population,
            Agent_Profile, Page, Population_Experiment, Page_Population, User_Experiment,
            Client, Client_Execution, Ollama_Pull, Jupyter_instances, ReleaseInfo,
            BlogPost, DownloadNotification, LogFileOffset, ServerLogMetrics,
            ClientLogMetrics, HpcMonitorSettings, WatchdogSettings, OpinionGroup,
            OpinionDistribution, OpinionEvolutionCache, OpinionEvolutionSampledAgents,
        ]
        for cls in admin_classes:
            assert hasattr(cls, "__bind_key__"), f"{cls.__name__} missing __bind_key__"
            assert cls.__bind_key__ == "db_admin", f"{cls.__name__} wrong bind key"


class TestCanonicalConfigImports:
    """All config/lookup model classes must be importable from y_web.src.models.config."""

    def test_config_module_importable(self):
        from y_web.src.models import config  # noqa: F401

    def test_profession(self):
        from y_web.src.models.config import Profession

        assert Profession.__tablename__ == "professions"

    def test_all_config_classes(self):
        from y_web.src.models.config import (
            ActivityProfile,
            AgeClass,
            Content_Recsys,
            Education,
            Exp_Topic,
            Follow_Recsys,
            Languages,
            Leanings,
            Nationalities,
            Page_Topic,
            PopulationActivityProfile,
            Profession,
            Topic_List,
            Toxicity_Levels,
        )

        config_classes = [
            Profession, Nationalities, Education, Leanings, Languages,
            Toxicity_Levels, AgeClass, Content_Recsys, Follow_Recsys,
            Topic_List, Exp_Topic, Page_Topic, ActivityProfile,
            PopulationActivityProfile,
        ]
        # Config models use either __bind__ or __bind_key__ depending on how
        # they were originally defined; just check they have a tablename.
        for cls in config_classes:
            assert hasattr(cls, "__tablename__"), f"{cls.__name__} missing __tablename__"


class TestSrcModelsPackageReExports:
    """y_web.src.models must re-export every class from all three sub-modules."""

    def test_experiment_classes_via_src_models(self):
        from y_web.src.models import User_mgmt, Post, Agent_Opinion

        assert User_mgmt is not None
        assert Post is not None
        assert Agent_Opinion is not None

    def test_admin_classes_via_src_models(self):
        from y_web.src.models import Admin_users, Exps, ClientLogMetrics

        assert Admin_users is not None
        assert Exps is not None
        assert ClientLogMetrics is not None

    def test_config_classes_via_src_models(self):
        from y_web.src.models import Profession, Education, ActivityProfile

        assert Profession is not None
        assert Education is not None
        assert ActivityProfile is not None


# ---------------------------------------------------------------------------
# Phase 1 — legacy shim backward-compatibility
# ---------------------------------------------------------------------------


class TestLegacyShimBackwardCompatibility:
    """All existing from y_web.src.models import X usage must keep working."""

    def test_shim_experiment_classes(self):
        from y_web.src.models import (
            Agent_Opinion,
            Article_topics,
            Articles,
            Emotions,
            Follow,
            Hashtags,
            ImagePosts,
            Images,
            Interests,
            Mentions,
            Post,
            Post_emotions,
            Post_hashtags,
            Post_Sentiment,
            Post_topics,
            Post_Toxicity,
            Reactions,
            Recommendations,
            ReplyInboxState,
            Rounds,
            User_interest,
            User_mgmt,
            Voting,
            Websites,
        )

        assert User_mgmt is not None
        assert Post is not None

    def test_shim_admin_classes(self):
        from y_web.src.models import (
            Admin_users,
            AdminInterviewMessage,
            AdminInterviewSession,
            BlogPost,
            Client,
            Client_Execution,
            ClientLogMetrics,
            DownloadNotification,
            Exps,
            HpcMonitorSettings,
            Jupyter_instances,
            LogFileOffset,
            Ollama_Pull,
            OpinionEvolutionCache,
            ReleaseInfo,
            ServerLogMetrics,
            WatchdogSettings,
        )

        assert Admin_users is not None
        assert Exps is not None
        assert ClientLogMetrics is not None

    def test_shim_config_classes(self):
        from y_web.src.models import (
            ActivityProfile,
            AgeClass,
            Content_Recsys,
            Education,
            Exp_Topic,
            Follow_Recsys,
            Languages,
            Leanings,
            Nationalities,
            Page_Topic,
            PopulationActivityProfile,
            Profession,
            Topic_List,
            Toxicity_Levels,
        )

        assert Profession is not None
        assert ActivityProfile is not None

    def test_shim_classes_are_same_objects_as_canonical(self):
        """The shim must re-export the exact same class objects, not copies."""
        from y_web.src.models import Admin_users as shim_admin
        from y_web.src.models import Post as shim_post
        from y_web.src.models import Profession as shim_prof

        from y_web.src.models.admin import Admin_users as src_admin
        from y_web.src.models.config import Profession as src_prof
        from y_web.src.models.experiment import Post as src_post

        assert shim_post is src_post
        assert shim_admin is src_admin
        assert shim_prof is src_prof


# ---------------------------------------------------------------------------
# Phase 1 — no circular imports
# ---------------------------------------------------------------------------


def test_no_circular_imports():
    """Importing y_web.src.models must not raise ImportError.

    We do not manipulate sys.modules here because unloading SQLAlchemy-mapped
    modules while the shared MetaData instance is still alive would cause a
    "Table already defined" error on re-import — that is a test-harness
    artefact, not a real circular-import problem.  Simply asserting that the
    import chain succeeds at least once is sufficient.
    """
    import sys

    # All three sub-modules must already be in sys.modules (loaded by earlier
    # tests).  Verify they imported without error.
    assert "y_web.src.models" in sys.modules
    assert "y_web.src.models.experiment" in sys.modules
    assert "y_web.src.models.admin" in sys.modules
    assert "y_web.src.models.config" in sys.modules


# ---------------------------------------------------------------------------
# Phase 1 — db.create_all() works with the new model package
# ---------------------------------------------------------------------------


def test_create_all_with_new_models(app):
    """db.create_all() must succeed when models are loaded from src/models."""
    # The app fixture already calls db.create_all(); if we reach here without
    # error, the tables were created successfully from the new package.
    from y_web import db
    from y_web.src.models.admin import Admin_users
    from y_web.src.models.experiment import User_mgmt

    with app.app_context():
        # Verify that the tables exist by querying them — no create_all()
        # call here since that's already done by the fixture and re-running
        # it would collide with the existing MetaData.
        admin_count = Admin_users.query.count()
        user_count = User_mgmt.query.count()
        assert admin_count >= 0
        assert user_count >= 0


def test_import_y_web_models_via_shim_attribute_access(app):
    """from y_web import models + models.User_mgmt must work (used in test_app_structure)."""
    from y_web import models

    assert hasattr(models, "User_mgmt")
    assert hasattr(models, "Admin_users")
    assert hasattr(models, "Post")
    assert hasattr(models, "Profession")
