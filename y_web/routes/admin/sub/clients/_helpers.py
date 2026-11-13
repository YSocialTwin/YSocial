"""Shared helper functions for the clients sub-package."""

import random


def allocate_topics_by_percentage(topics, topic_percentages):
    """
    Allocate topics to an agent based on specified interest percentages.

    Args:
        topics: List of topic names
        topic_percentages: Dict mapping topic names to percentage (0-100)

    Returns:
        List of topics the agent is interested in
    """
    agent_topics = []
    for topic in topics:
        percentage = topic_percentages.get(
            topic, 100.0
        )  # Default to 100% if not specified
        # Randomly decide if agent is interested based on percentage
        if random.random() <= percentage / 100.0:
            agent_topics.append(topic)

    # Ensure at least one topic if any topics have non-zero percentage
    if not agent_topics and any(topic_percentages.get(t, 100.0) > 0 for t in topics):
        # Pick one topic probabilistically based on percentages
        valid_topics = [t for t in topics if topic_percentages.get(t, 100.0) > 0]
        if valid_topics:
            weights = [topic_percentages.get(t, 100.0) for t in valid_topics]
            agent_topics = [random.choices(valid_topics, weights=weights)[0]]

    return agent_topics if agent_topics else []
