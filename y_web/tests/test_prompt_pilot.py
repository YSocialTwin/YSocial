"""The prompt pilot script: renders each language's prompts like a client, scores replies, writes a report."""

import importlib.util
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pilot", ROOT / "scripts" / "prompts" / "pilot.py")
pilot = importlib.util.module_from_spec(spec)
sys.modules["pilot"] = pilot
spec.loader.exec_module(pilot)


def _messages(language, task):
    with tempfile.TemporaryDirectory() as folder:
        pilot.use_language(language, folder)
        rng = random.Random(3)
        agent = pilot.Agent(rng, pilot.pack("en", "profile_values.json"), language)
        return pilot.build_messages(task, agent, pilot.pack(language, "prompts.json"), rng, language)


def test_italian_prompts_are_italian_and_keep_the_protocol_tokens_in_english():
    system, user = (m["content"] for m in _messages("it", "action"))
    assert system.startswith("Stai interpretando") and "years old" not in system
    assert "POST" in user and "COMMENT" in user and "NONE" in user
    english = _messages("en", "action")[1]["content"]
    assert user != english


def test_profile_values_and_the_follow_action_are_shown_in_italian():
    system, user = (m["content"] for m in _messages("it", "follow"))
    assert "seguire" in user and "follow its author" not in user
    assert not any(word in system for word in ("female", "male", "democrat "))


def test_english_prompts_do_not_change_with_the_pilot_machinery():
    system, _ = (m["content"] for m in _messages("en", "post"))
    assert system.startswith("You are role playing as ")


def test_a_dry_run_writes_runs_and_a_report(tmp_path):
    out, report = tmp_path / "runs", tmp_path / "report.md"
    pilot.main(["run", "--simulate", "--models", "fake", "--agents", "4", "--days", "2", "--seeds", "1", "--out", str(out)])
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.jsonl"))
    assert files == ["fake/en/seed1.jsonl", "fake/it/seed1.jsonl"]
    rows = [json.loads(line) for line in (out / "fake/it/seed1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4 * 2 * len(pilot.TASKS)
    pilot.main(["run", "--simulate", "--models", "fake", "--agents", "4", "--days", "2", "--seeds", "1", "--out", str(out)])  # resumes
    pilot.main(["analyze", "--out", str(out), "--report", str(report)])
    text = report.read_text(encoding="utf-8")
    assert "| fake | it | action |" in text and "Italian versus English" in text


def test_the_report_without_runs_is_a_template(tmp_path):
    report = tmp_path / "report.md"
    pilot.main(["analyze", "--out", str(tmp_path / "none"), "--report", str(report)])
    assert "No runs yet" in report.read_text(encoding="utf-8")


def test_score_understands_loose_replies_and_flags_meta_text():
    row = {"task": "follow", "language": "it", "reply": "Direi YES, mi interessa."}
    assert pilot.score(row) == {"ok": True, "exact": False, "choice": "YES"}
    post = {"task": "post", "language": "it", "reply": "Ecco il post: oggi la città non è come prima, non mi piace"}
    assert pilot.score(post)["meta"] is True and pilot.score(post)["lang"] is True


def test_agents_do_not_depend_on_language():
    """The only thing that varies between languages in the pilot is the language itself."""
    import random

    values = pilot.pack("en", "profile_values.json")
    seen = []
    for language in ("en", "it"):
        rng = random.Random("1")
        agent = pilot.Agent(rng, values, language)
        seen.append((agent.name, agent.age, agent.profession, agent.nationality))
    assert seen[0] == seen[1]


def test_safe_name_is_a_plain_folder_name():
    assert pilot.safe_name("feadxus/Llama:Q2_K") == "feadxus_Llama_Q2_K"
