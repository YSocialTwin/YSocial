import re

with open("y_web/routes/admin/sub/clients/_crud.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "Agent.query.filter_by(id=" in line and "for" in line:
        print(f"{i+1}: {line.strip()}")
