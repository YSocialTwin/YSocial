"""Ad hoc (plugin) agents speak the prompt language chosen for their experiment."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from y_web.src.simulation import adhoc_client

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "language,expected", [("it", {"YSOCIAL_PROMPT_LANGUAGE": "it"}), ("en", {})]
)
def test_adhoc_client_is_started_with_the_experiment_language(
    tmp_path, language, expected
):
    experiment = SimpleNamespace(idexp=1, prompt_language=language)
    config = tmp_path / "adhoc_client_a.json"
    with (
        patch.object(adhoc_client, "config_path_for_client", return_value=config),
        patch.object(adhoc_client, "ensure_state_for_config", return_value={}),
        patch.object(
            adhoc_client, "state_path_for_config", return_value=tmp_path / "s.json"
        ),
        patch.object(
            adhoc_client, "_runner_command", return_value=(["true"], str(tmp_path))
        ),
        patch.object(adhoc_client, "write_json"),
        patch.object(adhoc_client, "_register_process"),
        patch.object(
            adhoc_client.subprocess, "Popen", return_value=MagicMock(pid=1)
        ) as popen,
    ):
        adhoc_client.start_adhoc_client(experiment, "a")
    env = popen.call_args.kwargs["env"]
    assert env.get("YSOCIAL_PROMPT_LANGUAGE") == expected.get("YSOCIAL_PROMPT_LANGUAGE")
