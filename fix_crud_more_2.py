import re

with open("y_web/routes/admin/sub/clients/_crud.py", "r") as f:
    content = f.read()

# Fix another page one:
# pages = [Page.query.filter_by(id=p.page_id).first() for p in pages] -> multiple occurrences
old9 = """    # get the page details
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]"""

new9 = """    # get the page details
    # ⚡ Bolt: Fix N+1 query by batch fetching pages
    page_ids = [p.page_id for p in pages]
    pages = Page.query.filter(Page.id.in_(page_ids)).all() if page_ids else []"""

content = content.replace(old9, new9)

with open("y_web/routes/admin/sub/clients/_crud.py", "w") as f:
    f.write(content)

print("Done")
