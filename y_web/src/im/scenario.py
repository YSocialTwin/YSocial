"""Scenario content for instant messaging experiments (Scenario Design).

YWeb never writes the runtime's database: the plan of a scenario (chats and messages, see
``yinstantmessaging.server.scenario``) is handed to the runtime's own service through ``run_apply_scenario.py``,
with the experiment stopped. This module is the thin host side of that call, used by the Scenario Design plugin
(``adapters/im.py``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

TIMEOUT = 120
SCENARIO_DB_FILE = "scenario_design_im.db"  # the drafts of Scenario Design, beside the run's database


class ScenarioApplyError(Exception):
    """The runtime refused the plan (nothing was written); ``errors`` says why, one reason per item."""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class ScenarioApplyUnavailable(Exception):
    """The plan could not be applied for a reason that is not the plan's (runtime missing, server running...)."""


def apply_plan(
    exp_folder: str,
    plan: Dict[str, Any],
    dry_run: bool = False,
    repo_dir: Optional[str] = None,
    python_cmd: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply *plan* to the run in *exp_folder*; returns the runtime's counts and ids.

    ``dry_run`` computes the same figures and writes nothing. Raises ``ScenarioApplyError`` when the plan is
    rejected and ``ScenarioApplyUnavailable`` when it cannot be tried (no folder, server running, runtime too old).
    """
    from y_web.src.im.gateway_process import server_up

    if not exp_folder or not os.path.isdir(exp_folder):
        raise ScenarioApplyUnavailable("the experiment has no folder yet")
    if server_up(exp_folder):
        raise ScenarioApplyUnavailable("stop the experiment before applying a scenario to it")
    if repo_dir is None:
        from y_web.src.hpc.platforms import get_hpc_platform
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir(get_hpc_platform("instant_messaging").runtime_repo)
    if python_cmd is None:
        from y_web.src.simulation.server import detect_env_handler

        python_cmd = detect_env_handler()
    script = os.path.join(repo_dir, "run_apply_scenario.py")
    if not os.path.exists(script):
        raise ScenarioApplyUnavailable("the instant messaging runtime cannot apply scenarios: update it")

    handle, plan_path = tempfile.mkstemp(prefix="im_scenario_", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(plan, out)
        command = [python_cmd or sys.executable, script, exp_folder, plan_path]
        if dry_run:
            command.append("--dry-run")
        try:
            done = subprocess.run(command, cwd=repo_dir, capture_output=True, text=True, timeout=TIMEOUT)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ScenarioApplyUnavailable(f"the scenario could not be applied: {exc}") from exc
    finally:
        try:
            os.unlink(plan_path)
        except OSError:
            pass

    if done.returncode == 2:
        reasons = [line for line in (done.stderr or "").splitlines() if line.strip()]
        raise ScenarioApplyError(reasons or ["the scenario was rejected"])
    try:
        return json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        detail = (done.stderr or "").strip().splitlines()[-1:] or [f"exit code {done.returncode}"]
        raise ScenarioApplyUnavailable(f"the scenario could not be applied: {detail[0]}") from exc
