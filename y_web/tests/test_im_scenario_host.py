"""The host side of applying an instant messaging scenario: it runs the runtime's script and reports what it says."""

import json
import sys

import pytest

from y_web.src.im import scenario as host

PLAN = {"scenario_id": "s1", "chats": [], "messages": []}

OK = (
    "import json, sys\n"
    "plan = json.load(open(sys.argv[2]))\n"
    "print(json.dumps({'chats': {'created': 0}, 'seen': plan['scenario_id'], 'dry': '--dry-run' in sys.argv}))\n"
)
REFUSE = "import sys\nprint('message m1: text is required', file=sys.stderr)\nprint('chat c: title is required', file=sys.stderr)\nsys.exit(2)\n"
CRASH = "import sys\nprint('boom', file=sys.stderr)\nsys.exit(1)\n"


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    repo = tmp_path / "runtime"
    repo.mkdir()
    folder = tmp_path / "exp"
    folder.mkdir()
    monkeypatch.setattr("y_web.src.im.gateway_process.server_up", lambda f: False)

    def write(code):
        (repo / "run_apply_scenario.py").write_text(code)

    return repo, folder, write


def call(repo, folder, **kw):
    return host.apply_plan(
        str(folder), PLAN, repo_dir=str(repo), python_cmd=sys.executable, **kw
    )


def test_the_plan_reaches_the_runtime_and_its_answer_comes_back(runtime):
    repo, folder, write = runtime
    write(OK)
    assert call(repo, folder) == {"chats": {"created": 0}, "seen": "s1", "dry": False}
    assert call(repo, folder, dry_run=True)["dry"] is True


def test_a_refused_plan_lists_every_reason(runtime):
    repo, folder, write = runtime
    write(REFUSE)
    with pytest.raises(host.ScenarioApplyError) as caught:
        call(repo, folder)
    assert caught.value.errors == [
        "message m1: text is required",
        "chat c: title is required",
    ]


def test_what_is_not_the_plans_fault_is_unavailable(runtime, monkeypatch):
    repo, folder, write = runtime
    write(CRASH)
    with pytest.raises(host.ScenarioApplyUnavailable, match="boom"):
        call(repo, folder)
    (repo / "run_apply_scenario.py").unlink()
    with pytest.raises(host.ScenarioApplyUnavailable, match="update it"):
        call(repo, folder)
    write(OK)
    monkeypatch.setattr("y_web.src.im.gateway_process.server_up", lambda f: True)
    with pytest.raises(host.ScenarioApplyUnavailable, match="stop the experiment"):
        call(repo, folder)
    with pytest.raises(host.ScenarioApplyUnavailable, match="no folder"):
        host.apply_plan(
            str(folder / "missing"), PLAN, repo_dir=str(repo), python_cmd=sys.executable
        )


def test_the_plan_file_does_not_stay_behind(runtime, tmp_path, monkeypatch):
    repo, folder, write = runtime
    write(OK)
    seen = []
    real = host.tempfile.mkstemp
    monkeypatch.setattr(
        host.tempfile,
        "mkstemp",
        lambda **kw: (lambda h, p: (seen.append(p), (h, p))[1])(*real(**kw)),
    )
    call(repo, folder)
    assert seen and not __import__("os").path.exists(seen[0])
