"""A person can enter an IM experiment with the server off (account created by the runtime, not by YWeb)."""

import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_register_offline_runs_the_runtime_script(tmp_path):
    from y_web.src.im.gateway_process import register_offline

    (tmp_path / "run_register_human.py").write_text(
        "import sys; print('ok'); sys.exit(0 if sys.argv[2] == 'k' else 2)"
    )
    assert register_offline("f", str(tmp_path), "k", "u", sys.executable) is True
    assert register_offline("f", str(tmp_path), "other", "u", sys.executable) is False
    assert register_offline("f", str(tmp_path / "missing"), "k", "u") is False


def test_banner_tells_why_the_account_is_pending():
    text = open("y_web/templates/im/base.html", encoding="utf-8").read()
    assert "pending_reason == 'not_running'" in text and "pending_reason == 'refused'" in text
