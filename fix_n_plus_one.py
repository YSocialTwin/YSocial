import re

with open("y_web/routes/admin/sub/clients/_crud.py", "r") as f:
    content = f.read()

# Replace list comprehension N+1 with batch fetch
# agents = [Agent.query.filter_by(id=link.agent_id).first() for link in agent_links]

# Example replacement logic
# agent_ids = [link.agent_id for link in agent_links]
# agents = Agent.query.filter(Agent.id.in_(agent_ids)).all() if agent_ids else []
