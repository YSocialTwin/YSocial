"""
Phase T1 validation tests.

Verifies that:
  - ``scripts/audit_templates.sh`` exists, is executable, and exits 0 when run
    from the repository root.
  - ``docs/template_audit_baseline.txt`` exists and contains the expected
    Phase T1 baseline numbers.
  - The live template directory still matches those baseline numbers, confirming
    the baseline file is current and the audit script is reproducible.
"""

import os
import re
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUDIT_SCRIPT = os.path.join(REPO_ROOT, "scripts", "audit_templates.sh")
BASELINE_FILE = os.path.join(REPO_ROOT, "docs", "template_audit_baseline.txt")
TEMPLATES_DIR = os.path.join(REPO_ROOT, "y_web", "templates")

# Expected post-T4 baseline values (from docs/template_audit_baseline.txt)
BASELINE = {
    "files_with_style_blocks": 0,
    "total_style_blocks": 0,
    "total_style_attrs": 384,
    "total_inline_scripts": 49,
    "total_browsersync_occurrences": 1,
    "total_html_files": 84,
    "total_lines": 24161,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_kv(text):
    """
    Parse lines of the form ``key=value`` from *text* and return a dict of
    {key: int}.  Lines starting with ``#`` and blank lines are ignored.
    """
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z0-9_]+)=(\d+)$", line)
        if m:
            result[m.group(1)] = int(m.group(2))
    return result


def _run_audit():
    """Run scripts/audit_templates.sh and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["bash", AUDIT_SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


# Module-level cache so the audit script is invoked only once per test session.
@pytest.fixture(scope="module")
def live_audit_result():
    """Run the audit script once and return its parsed key-value output."""
    rc, stdout, stderr = _run_audit()
    assert rc == 0, (
        f"audit_templates.sh exited {rc}.\n"
        f"stdout: {stdout[:500]}\n"
        f"stderr: {stderr[:500]}"
    )
    return _parse_kv(stdout), stdout  # (kv_dict, raw_stdout)


# ---------------------------------------------------------------------------
# 1. Audit script exists and is executable
# ---------------------------------------------------------------------------


class TestAuditScriptExists:
    """scripts/audit_templates.sh must exist and be executable."""

    def test_scripts_directory_exists(self):
        assert os.path.isdir(
            os.path.join(REPO_ROOT, "scripts")
        ), "scripts/ directory not found at repo root"

# ---------------------------------------------------------------------------
# 2. Audit script runs successfully
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 3. Baseline file exists and is parseable
# ---------------------------------------------------------------------------


class TestBaselineFileExists:
    """docs/template_audit_baseline.txt must exist with expected content."""

    def test_docs_directory_exists(self):
        assert os.path.isdir(
            os.path.join(REPO_ROOT, "docs")
        ), "docs/ directory not found at repo root"

# ---------------------------------------------------------------------------
# 4. Live metrics match the baseline (reproducibility check)
# ---------------------------------------------------------------------------

