import os, re, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rewrite_imports import convert

Y = "/tmp/ws/YSocial/y_web"
F = "/tmp/ws/YForum/ysocial_platform"
os.makedirs(f"{F}/forum/actions", exist_ok=True)
os.makedirs(f"{F}/routes", exist_ok=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)


# --- library
for rel in [
    "client_config",
    "communities",
    "community_icons",
    "experiment_config",
    "network",
    "roster",
    "validation",
    "actions/__init__",
    "actions/media",
    "actions/posts",
    "actions/reactions",
    "__init__",
]:
    t = open(f"{Y}/src/forum/{rel}.py").read()
    t = convert(t, "")
    in_actions = rel.startswith("actions/")
    if in_actions:
        t = re.sub(
            r"from y_web\.src\.forum\.actions\.(\w+) import", r"from .\1 import", t
        )
        t = re.sub(r"from y_web\.src\.forum\.actions import", r"from . import", t)
        t = re.sub(r"from y_web\.src\.forum\.(\w+) import", r"from ..\1 import", t)
    else:
        t = re.sub(
            r"from y_web\.src\.forum\.actions import", r"from .actions import", t
        )
        t = re.sub(r"from y_web\.src\.forum\.(\w[\w.]*) import", r"from .\1 import", t)
        t = re.sub(r"from y_web\.src\.forum import", r"from . import", t)
    write(f"{F}/forum/{rel}.py", t)

# --- routes
RT = {
    "routes/social/forum.py": ("social_forum.py", False),
    "routes/interactions/forum.py": ("interactions_forum.py", False),
    "routes/api/reddit.py": ("api_reddit.py", False),
    "routes/admin/sub/clients/_forum_hpc.py": ("clients_forum_hpc.py", True),
}
for rel, (name, clients) in RT.items():
    t = open(f"{Y}/{rel}").read()
    t = convert(t, "", clients_pkg=clients)
    t = re.sub(
        r"from y_web\.src\.forum import (\w+) as (\w+)",
        r"from ..forum import \1 as \2",
        t,
    )
    t = re.sub(r"from y_web\.src\.forum import", "from ..forum import", t)
    t = re.sub(
        r"from y_web\.src\.forum\.(\w[\w.]*) import", r"from ..forum.\1 import", t
    )
    write(f"{F}/routes/{name}", t)
print("done")
