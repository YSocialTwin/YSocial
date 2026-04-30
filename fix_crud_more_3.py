with open("y_web/routes/admin/sub/clients/_crud.py", "r") as f:
    content = f.read()

old_page_fetch = """    pages = Page_Population.query.filter_by(population_id=population.id).all()
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]"""

new_page_fetch = """    page_pops = Page_Population.query.filter_by(population_id=population.id).all()
    # ⚡ Bolt: Fix N+1 query by batch fetching pages
    p_ids = [p.page_id for p in page_pops]
    pages = Page.query.filter(Page.id.in_(p_ids)).all() if p_ids else []"""

content = content.replace(old_page_fetch, new_page_fetch)

with open("y_web/routes/admin/sub/clients/_crud.py", "w") as f:
    f.write(content)

print("Done")
