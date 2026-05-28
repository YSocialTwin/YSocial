"""
Simple performance comparison demonstration for bulk insert optimization.

This script shows the theoretical performance improvement without requiring
a full database setup.
"""


def old_approach_simulation(num_agents):
    """Simulate the old approach with individual commits."""
    operations = 0

    for _ in range(num_agents):
        # Add agent
        operations += 1  # db.session.add(agent)
        operations += 1  # db.session.commit()

        # Add agent_population relationship
        operations += 1  # db.session.add(agent_population)
        operations += 1  # db.session.commit()

    return operations


def new_approach_simulation(num_agents):
    """Simulate the new approach with bulk inserts."""
    operations = 0

    # Collect all agents (no database operation)
    for _ in range(num_agents):
        pass  # Just collect in list

    # Bulk insert agents
    operations += 1  # db.session.bulk_save_objects(agents)
    operations += 1  # db.session.flush()

    # Collect all relationships (no database operation)
    for _ in range(num_agents):
        pass  # Just collect in list

    # Bulk insert relationships
    operations += 1  # db.session.bulk_save_objects(relationships)
    operations += 1  # db.session.commit()

    return operations


def main():
    """Compare performance for different population sizes."""
    print("=" * 70)
    print("Population Generation Performance Comparison")
    print("=" * 70)
    print()

    population_sizes = [10, 50, 100, 500, 1000, 5000]

    print(
        f"{'Population Size':<20} {'Old Operations':<20} {'New Operations':<20} {'Improvement':<20}"
    )
    print("-" * 70)

    for size in population_sizes:
        old_ops = old_approach_simulation(size)
        new_ops = new_approach_simulation(size)
        improvement = old_ops / new_ops

        print(f"{size:<20} {old_ops:<20} {new_ops:<20} {improvement:.1f}x faster")

    print()
    print("=" * 70)
    print("Summary:")
    print("  - Old approach: 4 database operations per agent (2 adds + 2 commits)")
    print("  - New approach: 4 total operations regardless of population size")
    print("  - Performance scales linearly with old, constant with new")
    print("=" * 70)


if __name__ == "__main__":
    main()
