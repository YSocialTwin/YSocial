import re

with open("y_web/routes/admin/sub/clients/_crud.py", "r") as f:
    content = f.read()

# Pattern 1
old1 = """    agent_links = Agent_Population.query.filter_by(population_id=population.id).all()
    agents = [Agent.query.filter_by(id=link.agent_id).first() for link in agent_links]
    agents = [agent for agent in agents if agent is not None]"""

new1 = """    agent_links = Agent_Population.query.filter_by(population_id=population.id).all()
    # ⚡ Bolt: Fix N+1 query by batch fetching agents
    agent_ids = [link.agent_id for link in agent_links]
    agents = Agent.query.filter(Agent.id.in_(agent_ids)).all() if agent_ids else []"""

content = content.replace(old1, new1)

# Pattern 2
old2 = """    agent_links = Agent_Population.query.filter_by(population_id=population_id).all()
    agents = []
    for link in agent_links:
        agent = Agent.query.filter_by(id=link.agent_id).first()
        if agent is not None:
            agents.append(agent)"""

new2 = """    agent_links = Agent_Population.query.filter_by(population_id=population_id).all()
    # ⚡ Bolt: Fix N+1 query by batch fetching agents
    agent_ids = [link.agent_id for link in agent_links]
    agents = Agent.query.filter(Agent.id.in_(agent_ids)).all() if agent_ids else []"""

content = content.replace(old2, new2)

# Pattern 3
old3 = """    # Get agents for this population
    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]"""

new3 = """    # Get agents for this population
    # ⚡ Bolt: Fix N+1 query by batch fetching agents
    agent_pops = Agent_Population.query.filter_by(population_id=population.id).all()
    agent_ids = [a.agent_id for a in agent_pops]
    agents = Agent.query.filter(Agent.id.in_(agent_ids)).all() if agent_ids else []"""

content = content.replace(old3, new3)

# Pattern 4
old4 = """        # Get agents and pages for the population (same logic as Standard)
        agent_pops = Agent_Population.query.filter_by(population_id=population_id).all()
        agents = [Agent.query.filter_by(id=ap.agent_id).first() for ap in agent_pops]"""

new4 = """        # Get agents and pages for the population (same logic as Standard)
        # ⚡ Bolt: Fix N+1 query by batch fetching agents
        agent_pops = Agent_Population.query.filter_by(population_id=population_id).all()
        agent_ids = [ap.agent_id for ap in agent_pops]
        agents = Agent.query.filter(Agent.id.in_(agent_ids)).all() if agent_ids else []"""

content = content.replace(old4, new4)

# Pattern 5
old5 = """    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    # get the agent details
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]"""

new5 = """    # ⚡ Bolt: Fix N+1 query by batch fetching agents
    agent_pops = Agent_Population.query.filter_by(population_id=population.id).all()
    agent_ids = [a.agent_id for a in agent_pops]
    agents = Agent.query.filter(Agent.id.in_(agent_ids)).all() if agent_ids else []"""

content = content.replace(old5, new5)

with open("y_web/routes/admin/sub/clients/_crud.py", "w") as f:
    f.write(content)

print("Done")
