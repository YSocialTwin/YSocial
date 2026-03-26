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

    def test_audit_script_file_exists(self):
        assert os.path.isfile(
            AUDIT_SCRIPT
        ), f"scripts/audit_templates.sh not found at {AUDIT_SCRIPT}"

    def test_audit_script_is_executable(self):
        assert os.access(
            AUDIT_SCRIPT, os.X_OK
        ), "scripts/audit_templates.sh is not executable (chmod +x)"

    def test_audit_script_has_shebang(self):
        with open(AUDIT_SCRIPT, encoding="utf-8") as fh:
            first_line = fh.readline().rstrip()
        assert first_line.startswith(
            "#!"
        ), f"audit_templates.sh should start with a shebang, got: {first_line!r}"


# ---------------------------------------------------------------------------
# 2. Audit script runs successfully
# ---------------------------------------------------------------------------


class TestAuditScriptRuns:
    """Running audit_templates.sh from the repo root must exit 0."""

    def test_audit_script_exits_zero(self, live_audit_result):
        # The fixture already asserts exit 0; this test just makes it explicit.
        _kv, _stdout = live_audit_result
        assert _kv is not None

    def test_audit_script_outputs_overall_totals_section(self, live_audit_result):
        _kv, stdout = live_audit_result
        assert (
            "## Overall Totals" in stdout
        ), "audit output should contain '## Overall Totals' section"

    def test_audit_script_outputs_per_section_breakdown(self, live_audit_result):
        _kv, stdout = live_audit_result
        assert (
            "## Per-Section Breakdown" in stdout
        ), "audit output should contain '## Per-Section Breakdown' section"

    def test_audit_script_outputs_expected_keys(self, live_audit_result):
        kv, _stdout = live_audit_result
        for key in BASELINE:
            assert key in kv, f"Expected key '{key}' missing from audit output"


# ---------------------------------------------------------------------------
# 3. Baseline file exists and is parseable
# ---------------------------------------------------------------------------


class TestBaselineFileExists:
    """docs/template_audit_baseline.txt must exist with expected content."""

    def test_docs_directory_exists(self):
        assert os.path.isdir(
            os.path.join(REPO_ROOT, "docs")
        ), "docs/ directory not found at repo root"

    def test_baseline_file_exists(self):
        assert os.path.isfile(
            BASELINE_FILE
        ), f"docs/template_audit_baseline.txt not found at {BASELINE_FILE}"

    def test_baseline_file_not_empty(self):
        assert (
            os.path.getsize(BASELINE_FILE) > 0
        ), "docs/template_audit_baseline.txt is empty"

    def test_baseline_file_contains_overall_totals_section(self):
        content = open(BASELINE_FILE, encoding="utf-8").read()
        assert (
            "## Overall Totals" in content
        ), "Baseline file should contain '## Overall Totals' section"

    @pytest.mark.parametrize("key,expected", list(BASELINE.items()))
    def test_baseline_file_contains_correct_value(self, key, expected):
        content = open(BASELINE_FILE, encoding="utf-8").read()
        kv = _parse_kv(content)
        assert key in kv, f"Key '{key}' not found in baseline file"
        assert (
            kv[key] == expected
        ), f"Baseline '{key}': expected {expected}, got {kv[key]}"


# ---------------------------------------------------------------------------
# 4. Live metrics match the baseline (reproducibility check)
# ---------------------------------------------------------------------------


class TestLiveMetricsMatchBaseline:
    """
    The live template directory must produce the same numbers as the baseline.
    This confirms the baseline file is current and the audit is reproducible.
    """

    @pytest.mark.parametrize("key,expected", list(BASELINE.items()))
    def test_live_metric_matches_baseline(self, key, expected, live_audit_result):
        kv, _stdout = live_audit_result
        assert key in kv, f"Key '{key}' missing from live audit output"
        assert kv[key] == expected, (
            f"Live metric '{key}' = {kv[key]}, "
            f"but baseline says {expected}. "
            "Re-run 'bash scripts/audit_templates.sh > docs/template_audit_baseline.txt' "
            "to update the baseline after a completed phase."
        )
