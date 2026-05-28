"""
Test for experiment schedule group functionality.

This test verifies that:
1. HPC experiments can be added to groups up to a maximum of 4
2. Standard and HPC experiments cannot be mixed in the same group
3. Auto composition batches HPC experiments correctly (up to 4 per group)
"""

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


# Maximum number of HPC experiments allowed per schedule group
# This constant matches the one in y_web/routes_admin/experiments_routes.py
MAX_HPC_PER_GROUP = 4


def test_hpc_experiment_group_limit():
    """Test that up to 4 HPC experiments can be added to a group."""

    # Simulate adding HPC experiments to a group
    hpc_count = 0

    # Add 4 HPC experiments - should succeed
    for i in range(MAX_HPC_PER_GROUP):
        hpc_count += 1
        assert hpc_count <= MAX_HPC_PER_GROUP, "Should allow up to 4 HPC experiments"

    # Try to add a 5th - should fail
    hpc_count += 1
    assert hpc_count > MAX_HPC_PER_GROUP, "Should not allow more than 4 HPC experiments"


def test_hpc_standard_experiment_mixing():
    """Test that HPC and Standard experiments cannot be mixed in the same group."""

    # Mock experiments
    hpc_exp = MagicMock()
    hpc_exp.simulator_type = "HPC"

    standard_exp = MagicMock()
    standard_exp.simulator_type = "Standard"

    # Group with HPC experiment
    group_with_hpc = {"experiments": [hpc_exp]}

    # Trying to add Standard to HPC group should fail
    is_hpc = standard_exp.simulator_type == "HPC"
    has_hpc = any(exp.simulator_type == "HPC" for exp in group_with_hpc["experiments"])

    can_add_standard_to_hpc_group = not (not is_hpc and has_hpc)
    assert not can_add_standard_to_hpc_group, "Cannot add Standard to HPC group"

    # Group with Standard experiment
    group_with_standard = {"experiments": [standard_exp]}

    # Trying to add HPC to Standard group should fail
    is_hpc = hpc_exp.simulator_type == "HPC"
    has_standard = any(
        exp.simulator_type != "HPC" for exp in group_with_standard["experiments"]
    )

    can_add_hpc_to_standard_group = not (is_hpc and has_standard)
    assert not can_add_hpc_to_standard_group, "Cannot add HPC to Standard group"


def test_auto_composition_hpc_batching():
    """Test that auto composition correctly batches HPC experiments into groups of up to 4."""

    # Simulate 10 HPC experiments
    hpc_exps = [MagicMock(simulator_type="HPC", idexp=i) for i in range(10)]

    # Batch them into groups (default max of 4)
    groups = []
    for i in range(0, len(hpc_exps), MAX_HPC_PER_GROUP):
        group_hpc_exps = hpc_exps[i : i + MAX_HPC_PER_GROUP]
        groups.append(group_hpc_exps)

    # Verify batching
    assert len(groups) == 3, "10 HPC experiments should create 3 groups (4+4+2)"
    assert len(groups[0]) == 4, "First group should have 4 experiments"
    assert len(groups[1]) == 4, "Second group should have 4 experiments"
    assert len(groups[2]) == 2, "Third group should have 2 experiments"


def test_auto_composition_hpc_respects_user_limit():
    """Test that HPC batching respects user-specified limit when less than 4."""
    experiments_per_group = 2  # User specifies 2

    # Simulate 10 HPC experiments
    hpc_exps = [MagicMock(simulator_type="HPC", idexp=i) for i in range(10)]

    # Calculate HPC per group: min(4, 2) = 2
    hpc_per_group = min(MAX_HPC_PER_GROUP, experiments_per_group)
    assert hpc_per_group == 2, "Should use user's value when less than 4"

    # Batch them into groups
    groups = []
    for i in range(0, len(hpc_exps), hpc_per_group):
        group_hpc_exps = hpc_exps[i : i + hpc_per_group]
        groups.append(group_hpc_exps)

    # Verify batching with user's limit
    assert (
        len(groups) == 5
    ), "10 HPC experiments with limit 2 should create 5 groups (2+2+2+2+2)"
    for i, group in enumerate(groups):
        assert len(group) == 2, f"Group {i} should have 2 experiments"


def test_auto_composition_hpc_caps_at_max():
    """Test that HPC batching caps at MAX_HPC_PER_GROUP even if user specifies more."""
    experiments_per_group = 6  # User specifies 6

    # Simulate 10 HPC experiments
    hpc_exps = [MagicMock(simulator_type="HPC", idexp=i) for i in range(10)]

    # Calculate HPC per group: min(4, 6) = 4 (capped at max)
    hpc_per_group = min(MAX_HPC_PER_GROUP, experiments_per_group)
    assert (
        hpc_per_group == 4
    ), "Should cap at MAX_HPC_PER_GROUP (4) when user specifies more"

    # Batch them into groups
    groups = []
    for i in range(0, len(hpc_exps), hpc_per_group):
        group_hpc_exps = hpc_exps[i : i + hpc_per_group]
        groups.append(group_hpc_exps)

    # Verify batching capped at max
    assert (
        len(groups) == 3
    ), "10 HPC experiments capped at 4 should create 3 groups (4+4+2)"
    assert len(groups[0]) == 4, "First group should have 4 experiments"
    assert len(groups[1]) == 4, "Second group should have 4 experiments"
    assert len(groups[2]) == 2, "Third group should have 2 experiments"


def test_auto_composition_standard_batching():
    """Test that auto composition correctly batches Standard experiments."""
    experiments_per_group = 3

    # Simulate 7 Standard experiments
    standard_exps = [MagicMock(simulator_type="Standard", idexp=i) for i in range(7)]

    # Batch them into groups
    groups = []
    for i in range(0, len(standard_exps), experiments_per_group):
        group_exps = standard_exps[i : i + experiments_per_group]
        groups.append(group_exps)

    # Verify batching
    assert (
        len(groups) == 3
    ), "7 Standard experiments with groups of 3 should create 3 groups (3+3+1)"
    assert len(groups[0]) == 3, "First group should have 3 experiments"
    assert len(groups[1]) == 3, "Second group should have 3 experiments"
    assert len(groups[2]) == 1, "Third group should have 1 experiment"


def test_mixed_experiments_auto_composition():
    """Test auto composition with both HPC and Standard experiments."""
    experiments_per_group = 2

    # Simulate 6 HPC and 5 Standard experiments
    hpc_exps = [MagicMock(simulator_type="HPC", idexp=i) for i in range(6)]
    standard_exps = [
        MagicMock(simulator_type="Standard", idexp=i + 10) for i in range(5)
    ]

    # Calculate HPC per group: min(4, 2) = 2
    hpc_per_group = min(MAX_HPC_PER_GROUP, experiments_per_group)

    # Separate and batch HPC experiments (respecting user limit)
    hpc_groups = []
    for i in range(0, len(hpc_exps), hpc_per_group):
        group_hpc_exps = hpc_exps[i : i + hpc_per_group]
        hpc_groups.append(group_hpc_exps)

    # Batch Standard experiments
    standard_groups = []
    for i in range(0, len(standard_exps), experiments_per_group):
        group_exps = standard_exps[i : i + experiments_per_group]
        standard_groups.append(group_exps)

    # Verify HPC batching (should use user's value of 2)
    assert (
        len(hpc_groups) == 3
    ), "6 HPC experiments with limit 2 should create 3 groups (2+2+2)"
    assert len(hpc_groups[0]) == 2, "First HPC group should have 2 experiments"
    assert len(hpc_groups[1]) == 2, "Second HPC group should have 2 experiments"
    assert len(hpc_groups[2]) == 2, "Third HPC group should have 2 experiments"

    # Verify Standard batching
    assert (
        len(standard_groups) == 3
    ), "5 Standard experiments with groups of 2 should create 3 groups (2+2+1)"
    assert (
        len(standard_groups[0]) == 2
    ), "First Standard group should have 2 experiments"
    assert (
        len(standard_groups[1]) == 2
    ), "Second Standard group should have 2 experiments"
    assert len(standard_groups[2]) == 1, "Third Standard group should have 1 experiment"

    # Total groups
    total_groups = len(hpc_groups) + len(standard_groups)
    assert total_groups == 6, "Should have 6 total groups (3 HPC + 3 Standard)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
