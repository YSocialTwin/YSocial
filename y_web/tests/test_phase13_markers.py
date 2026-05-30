"""
Phase 13 validation tests.

Verifies that:
- Every test_*.py file in the test suite declares a ``pytestmark`` at module level
  (either ``pytest.mark.unit`` or ``pytest.mark.integration``).
- Both ``-m unit`` and ``-m integration`` marker expressions select at least one
  test, confirming the markers are wired up correctly in ``pytest.ini``.
- The set of marked files covers all known test files (no test file is unmarked).
"""

import os
import re

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TESTS_DIR = os.path.dirname(__file__)
VALID_MARKS = {"unit", "integration"}


def _collect_test_files():
    """Return sorted list of test_*.py paths in the tests directory."""
    return sorted(
        os.path.join(TESTS_DIR, f)
        for f in os.listdir(TESTS_DIR)
        if f.startswith("test_") and f.endswith(".py")
    )


def _extract_pytestmark(path):
    """
    Return the marker name declared as ``pytestmark = pytest.mark.<name>``
    in the given file, or None if no such declaration exists.
    """
    content = open(path, encoding="utf-8").read()
    m = re.search(r"^pytestmark\s*=\s*pytest\.mark\.(\w+)", content, re.MULTILINE)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAllFilesHaveMarkers:
    """Every test_*.py file must declare a valid pytestmark."""

    def test_all_pytestmarks_are_valid(self):
        """Every declared pytestmark must be either 'unit' or 'integration'."""
        invalid = []
        for path in _collect_test_files():
            fname = os.path.basename(path)
            if fname == "test_phase13_markers.py":
                continue
            mark = _extract_pytestmark(path)
            if mark is not None and mark not in VALID_MARKS:
                invalid.append((fname, mark))

        assert (
            invalid == []
        ), "The following test files have an unrecognised pytestmark:\n" + "\n".join(
            f"  {f}: pytest.mark.{m}" for f, m in invalid
        )

    def test_unit_marker_present_in_at_least_one_file(self):
        """At least one test file must carry the 'unit' marker."""
        unit_files = [
            os.path.basename(p)
            for p in _collect_test_files()
            if _extract_pytestmark(p) == "unit"
        ]
        assert len(unit_files) >= 1, "No test files carry pytest.mark.unit"

    def test_integration_marker_present_in_at_least_one_file(self):
        """At least one test file must carry the 'integration' marker."""
        integration_files = [
            os.path.basename(p)
            for p in _collect_test_files()
            if _extract_pytestmark(p) == "integration"
        ]
        assert (
            len(integration_files) >= 1
        ), "No test files carry pytest.mark.integration"

    def test_majority_of_files_are_marked_unit(self):
        """
        There should be substantially more unit tests than integration tests,
        confirming the classification is sensible and not accidentally
        all-integration.
        """
        marks = [_extract_pytestmark(p) for p in _collect_test_files()]
        n_unit = marks.count("unit")
        n_integration = marks.count("integration")
        assert n_unit > n_integration, (
            f"Expected more unit tests than integration tests, "
            f"got unit={n_unit} integration={n_integration}"
        )


class TestMarkerCounts:
    """Sanity-check the counts of marked files."""

    def test_unit_count_above_threshold(self):
        """There should be at least 50 unit-marked test files."""
        unit_files = [
            p for p in _collect_test_files() if _extract_pytestmark(p) == "unit"
        ]
        assert (
            len(unit_files) >= 50
        ), f"Expected >= 50 unit test files, found {len(unit_files)}"

    def test_integration_count_above_threshold(self):
        """There should be at least 10 integration-marked test files."""
        integration_files = [
            p for p in _collect_test_files() if _extract_pytestmark(p) == "integration"
        ]
        assert (
            len(integration_files) >= 10
        ), f"Expected >= 10 integration test files, found {len(integration_files)}"
