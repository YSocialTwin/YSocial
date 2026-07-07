from y_web.routes.admin.sub.experiments._crud import generate_hpc_config
from y_web.src.simulation.agent_sampler import _is_fatal_reply_error


def test_generate_hpc_config_does_not_emit_deprecated_recommendations():
    config = generate_hpc_config(
        exp_name="exp",
        platform_type="microblogging",
        db_type="sqlite",
        db_uri="sqlite:///tmp.db",
        redis_enabled=False,
        redis_host="localhost",
        redis_port=6379,
        redis_password="",
        redis_sliding_window_days=1,
        perspective_api="",
        toxicity_annotation=False,
        sentiment_annotation=False,
        emotion_annotation=False,
        topics=[],
        data_path="/tmp",
    )

    assert "recommendations" not in config


def test_fatal_reply_error_detection_matches_ray_actor_death_messages():
    assert _is_fatal_reply_error(
        RuntimeError(
            "The actor died unexpectedly before finishing this task. "
            "Owner worker exit type: SYSTEM_ERROR."
        )
    )

    assert not _is_fatal_reply_error(RuntimeError("temporary timeout"))
