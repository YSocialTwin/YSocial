import glob
import os
import re
import shutil

Y = "/tmp/ws/YSocial/y_web"
F = "/tmp/ws/YForum/ysocial_platform"
ADMIN = [
    "_forum_communities",
    "client_details_forum",
    "clients_forum",
    "clients_forum_hpc",
    "experiment_details_forum",
    "forum_image_resources",
    "forum_rss_resources",
    "opinion_configuration_forum",
    "prompts_forum",
]
moved = []
for p in glob.glob(f"{Y}/templates/forum/**/*.html", recursive=True):
    moved.append(os.path.relpath(p, f"{Y}/templates"))
for a in ADMIN:
    moved.append(f"admin/{a}.html")


def retarget(text):
    for m in sorted(moved, key=len, reverse=True):
        text = re.sub(r"(?<![\w@/])" + re.escape(m), "@forum/" + m, text)
    text = re.sub(
        r"url_for\(\s*(['\"])static\1\s*,\s*filename\s*=\s*(['\"])assets/css/reddit/",
        r"url_for(\1platform_static_forum\1, filename=\2css/",
        text,
    )
    text = re.sub(
        r"url_for\(\s*(['\"])static\1\s*,\s*filename\s*=\s*(['\"])assets/js/reddit/",
        r"url_for(\1platform_static_forum\1, filename=\2js/",
        text,
    )
    text = re.sub(
        r"url_for\(\s*(['\"])static\1\s*,\s*filename\s*=\s*(['\"])assets/js/(forum-profile[\w-]*\.js)",
        r"url_for(\1platform_static_forum\1, filename=\2js/\3",
        text,
    )
    return text


for rel in moved:
    t = open(f"{Y}/templates/{rel}").read()
    t = retarget(t)
    dst = f"{F}/templates/{rel}"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "w").write(t)
for p in glob.glob(f"{Y}/static/assets/css/reddit/*"):
    dst = f"{F}/static/css/{os.path.basename(p)}"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(p, dst)
for p in glob.glob(f"{Y}/static/assets/js/reddit/*") + glob.glob(
    f"{Y}/static/assets/js/forum-profile*.js"
):
    dst = f"{F}/static/js/{os.path.basename(p)}"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(p, dst)
# python of moved routes
for p in glob.glob(f"{F}/routes/*.py") + [f"{F}/provider.py"]:
    t = open(p).read()
    n = retarget(t)
    if n != t:
        open(p, "w").write(n)
open("/tmp/ws/moved_forum_templates.txt", "w").write("\n".join(moved))
print(len(moved))
