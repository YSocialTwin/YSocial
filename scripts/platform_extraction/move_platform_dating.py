import ast, glob, os, pathlib, subprocess, sys

SRC = pathlib.Path("/tmp/ws/YSocial")
DST = pathlib.Path("/tmp/ws/YDating/ysocial_platform")

# (old module) -> (new module); names kept unless NAME_MAP says otherwise
MODULE_MAP = {
    "y_web.i18n": "y_web.sdk",
    "y_web.src.models": "y_web.sdk.models",
    "y_web.src.system.miscellanea": "y_web.sdk.web",
    "y_web.src.experiment.access": "y_web.sdk.web",
    "y_web.src.system.path_utils": "y_web.sdk.runtime",
    "y_web.src.simulation.server": "y_web.sdk.runtime",
    "y_web.src.simulation.subprocess_env": "y_web.sdk.runtime",
    "y_web.src.hpc.platforms": "y_web.sdk.runtime",
    "y_web.src.hpc.run_length": "y_web.sdk.runtime",
    "y_web.src.im.clone": "y_web.sdk.runtime",
    "y_web.src.external_runtime": "y_web.sdk.runtime",
    "y_web.src.federation": "y_web.sdk.federation",
    "y_web.src.federation.dynamic": "y_web.sdk.federation",
    "y_web.src.federation.humans": "y_web.sdk.federation",
    "y_web.src.agents": "y_web.sdk.agents",
    "y_web.src.agents.profile_pictures": "y_web.sdk.agents",
    "y_web.routes.admin.sub.experiments._helpers": "y_web.sdk.web",
    "y_web.routes.social.helpers": "y_web.sdk.web",
    ".._crud": "y_web.sdk.web",
}
NAME_MAP = {
    "_current_admin_user_or_none": "current_admin_user_or_none",
    "_experiment_configuration_update_required": "experiment_configuration_update_required",
    "_experiment_uses_llm_agents": "experiment_uses_llm_agents",
    "_load_ui_settings": "load_ui_settings",
    "_build_client_creation_context": "build_client_creation_context",
    "_get_experiment_folder_name": "get_experiment_folder_name",
    "_get_database_type": "get_database_type",
    "_get_experiment_folder": "get_experiment_folder",
}
BLUEPRINTS = {
    "y_web.routes.social._blueprint": {"main": "main"},
    "_blueprint": {"clientsr": "clients", "experiments": "experiments"},
}
ROUTE_MODULES = {  # old core module -> module name inside ysocial_platform/routes
    "y_web.routes.social.dating": "social_dating",
    "y_web.routes.social.dating_participant": "social_dating_participant",
}


def resolve_relative(node, relmod_base):
    return ("." * node.level) + (node.module or "")


def rewrite(text, kind):
    """kind: 'lib' (ysocial_platform/dating) or 'route' (ysocial_platform/routes)."""
    tree = ast.parse(text)
    lines = text.split("\n")
    edits = []
    dating_prefix = "." if kind == "lib" else ".."
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = ("." * node.level) + (node.module or "")
        names = node.names
        new = None
        indent = " " * node.col_offset

        def fmt(m, ns):
            parts = []
            for a in ns:
                n = NAME_MAP.get(a.name, a.name)
                parts.append(
                    n
                    if (n == a.name and not a.asname)
                    else (f"{n} as {a.asname}" if a.asname else f"{n} as {a.name}")
                )
            return f"{indent}from {m} import " + ", ".join(parts)

        if mod == "y_web" and [a.name for a in names] == ["db"]:
            new = f"{indent}from y_web.sdk.models import db"
        elif mod == "y_web.src.dating" or mod.startswith("y_web.src.dating."):
            sub = mod[len("y_web.src.dating") :]
            new = fmt(dating_prefix + sub, names)
        elif mod in ROUTE_MODULES:
            new = fmt("." + ROUTE_MODULES[mod], names)
        elif mod in BLUEPRINTS:
            outs = []
            for a in names:
                bp = BLUEPRINTS[mod][a.name]
                outs.append(f'{a.asname or a.name} = blueprint("{bp}")')
            new = (
                indent
                + "from y_web.sdk.routes import blueprint\n"
                + "\n".join(indent + o for o in outs)
            )
        elif mod in MODULE_MAP:
            new = fmt(MODULE_MAP[mod], names)
        elif mod == "._helpers":
            new = fmt("y_web.sdk.web", names)
        elif mod == "._crud":
            new = fmt("y_web.sdk.web", names)
        elif mod.startswith("y_web.") or mod == "y_web":
            if mod in ("y_web.sdk",):
                continue
            print("UNMAPPED", mod, [a.name for a in names], file=sys.stderr)
            continue
        elif node.level:
            print("UNMAPPED REL", mod, file=sys.stderr)
            continue
        if new is not None:
            edits.append((node.lineno, node.end_lineno, new))
    for lo, hi, new in sorted(edits, reverse=True):
        lines[lo - 1 : hi] = new.split("\n")
    out = "\n".join(lines)
    out = out.replace("y_web.src.dating", "ysocial_platform.dating").replace(
        "y_web/src/dating", "ysocial_platform/dating"
    )
    return out


def move(src_rel, dst_rel, kind):
    src = SRC / src_rel
    dst = DST / dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(rewrite(src.read_text("utf-8"), kind), "utf-8")
    subprocess.run(["git", "rm", "-q", str(src)], check=True, cwd=SRC)


if __name__ == "__main__":
    for f in sorted(glob.glob(str(SRC / "y_web/src/dating/*.py"))):
        move(os.path.relpath(f, SRC), "dating/" + os.path.basename(f), "lib")
    routes = {
        "y_web/routes/social/dating.py": "social_dating.py",
        "y_web/routes/social/dating_participant.py": "social_dating_participant.py",
        "y_web/routes/admin/sub/clients/_dating.py": "clients_dating.py",
        "y_web/routes/admin/sub/experiments/_dating.py": "experiments_dating.py",
        "y_web/routes/admin/sub/experiments/_dating_analytics.py": "experiments_dating_analytics.py",
        "y_web/routes/admin/sub/experiments/_dating_participants.py": "experiments_dating_participants.py",
        "y_web/routes/admin/sub/experiments/_dating_prompts.py": "experiments_dating_prompts.py",
    }
    for s, d in routes.items():
        move(s, "routes/" + d, "route")
