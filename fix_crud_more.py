import re

with open("y_web/routes/admin/sub/clients/_crud.py", "r") as f:
    content = f.read()

# Pattern 6 (Page batch fetch)
old6 = """        page_pops = Page_Population.query.filter_by(population_id=population_id).all()
        pages_list = [Page.query.filter_by(id=pp.page_id).first() for pp in page_pops]"""

new6 = """        page_pops = Page_Population.query.filter_by(population_id=population_id).all()
        # ⚡ Bolt: Fix N+1 query by batch fetching pages
        page_ids = [pp.page_id for pp in page_pops]
        pages_list = Page.query.filter(Page.id.in_(page_ids)).all() if page_ids else []"""

content = content.replace(old6, new6)

# Pattern 7 (Agent name fetch)
old7 = """        agents = Agent_Population.query.filter(
            Agent_Population.population_id.in_([p.id for p in populations])
        ).all()
        # get agent ids for all agents in populations
        agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]"""

new7 = """        agents = Agent_Population.query.filter(
            Agent_Population.population_id.in_([p.id for p in populations])
        ).all()
        # get agent ids for all agents in populations
        # ⚡ Bolt: Fix N+1 query by batch fetching agents
        a_ids = [a.agent_id for a in agents]
        fetched_agents = Agent.query.filter(Agent.id.in_(a_ids)).all() if a_ids else []
        agent_ids = [a.name for a in fetched_agents if a]"""

content = content.replace(old7, new7)

# Pattern 8 (Agent name fetch)
old8 = """        agents = Agent_Population.query.filter(
            Agent_Population.population_id.in_([p.id for p in populations])
        ).all()
        # get agent ids for all agents in populations
        agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]"""

content = content.replace(old8, new7) # Replace all occurrences

with open("y_web/routes/admin/sub/clients/_crud.py", "w") as f:
    f.write(content)

print("Done")
