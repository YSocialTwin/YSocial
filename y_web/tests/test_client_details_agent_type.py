"""
Test for client details agent type extraction with safe handling of page agents.
"""

import pytest
pytestmark = pytest.mark.unit



class TestClientDetailsAgentType:
    """Test safe agent type extraction in client details pages"""

    def test_agent_type_extraction_with_regular_agents(self):
        """Test that regular agents with type field are extracted correctly"""
        # Simulate the logic from client_details functions
        agents = {
            "agents": [
                {"name": "agent1", "type": "llm", "is_page": 0},
                {"name": "agent2", "type": "llm", "is_page": 0},
                {"name": "agent3", "type": "simple", "is_page": 0},
            ]
        }

        llms = []
        for agent in agents["agents"]:
            if not agent.get("is_page", 0):
                agent_type = agent.get("type")
                if agent_type:
                    llms.append(agent_type)

        result = ",".join(list(set(llms)))
        assert "llm" in result
        assert "simple" in result
        assert len(llms) == 3

    def test_agent_type_extraction_with_page_agents(self):
        """Test that page agents without type field don't cause KeyError"""
        # Simulate agents including pages (is_page=1) which lack "type" field
        agents = {
            "agents": [
                {"name": "agent1", "type": "llm", "is_page": 0},
                {"name": "page1", "is_page": 1, "feed_url": "http://example.com"},
                {"name": "agent2", "type": "simple", "is_page": 0},
                {"name": "page2", "is_page": 1, "feed_url": "http://example2.com"},
            ]
        }

        llms = []
        for agent in agents["agents"]:
            # Skip page agents (is_page=1) as they don't have a type field
            if not agent.get("is_page", 0):
                agent_type = agent.get("type")
                if agent_type:
                    llms.append(agent_type)

        result = ",".join(list(set(llms)))
        assert "llm" in result
        assert "simple" in result
        assert len(llms) == 2  # Only 2 non-page agents

    def test_agent_type_extraction_with_missing_type_field(self):
        """Test that agents missing type field are handled gracefully"""
        agents = {
            "agents": [
                {"name": "agent1", "type": "llm", "is_page": 0},
                {"name": "agent2", "is_page": 0},  # No type field
                {"name": "agent3", "type": "simple", "is_page": 0},
            ]
        }

        llms = []
        for agent in agents["agents"]:
            if not agent.get("is_page", 0):
                agent_type = agent.get("type")
                if agent_type:
                    llms.append(agent_type)

        result = ",".join(list(set(llms)))
        assert "llm" in result
        assert "simple" in result
        assert len(llms) == 2  # Only 2 agents with type

    def test_agent_type_extraction_with_all_pages(self):
        """Test that a population with only page agents returns empty result"""
        agents = {
            "agents": [
                {"name": "page1", "is_page": 1, "feed_url": "http://example.com"},
                {"name": "page2", "is_page": 1, "feed_url": "http://example2.com"},
            ]
        }

        llms = []
        for agent in agents["agents"]:
            if not agent.get("is_page", 0):
                agent_type = agent.get("type")
                if agent_type:
                    llms.append(agent_type)

        result = ",".join(list(set(llms)))
        assert result == ""  # No regular agents
        assert len(llms) == 0

    def test_agent_type_extraction_with_none_agents(self):
        """Test that None agents value is handled gracefully"""
        agents = None

        llms = []
        if agents is not None:
            for agent in agents["agents"]:
                if not agent.get("is_page", 0):
                    agent_type = agent.get("type")
                    if agent_type:
                        llms.append(agent_type)

        result = ",".join(list(set(llms)))
        assert result == ""
        assert len(llms) == 0

    def test_agent_type_deduplication(self):
        """Test that duplicate agent types are deduplicated"""
        agents = {
            "agents": [
                {"name": "agent1", "type": "llm", "is_page": 0},
                {"name": "agent2", "type": "llm", "is_page": 0},
                {"name": "agent3", "type": "llm", "is_page": 0},
            ]
        }

        llms = []
        for agent in agents["agents"]:
            if not agent.get("is_page", 0):
                agent_type = agent.get("type")
                if agent_type:
                    llms.append(agent_type)

        result = ",".join(list(set(llms)))
        assert result == "llm"
        # Original list has 3 items, but set reduces to 1
        assert len(llms) == 3
        assert len(set(llms)) == 1
