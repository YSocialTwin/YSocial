#!/usr/bin/env python3
"""Declare in the plugin registry that the platforms of platform API 1.6 need YSocial 4.1.0.

Adds ``"min_ysocial_version": "4.1.0"`` to the built-in entries that miss it (idempotent). Changes only the
registry checkout; it does not commit. After it, in this order:

    cd plugin-registry && git add builtin.json && git commit -m "Built-in: min_ysocial_version 4.1.0 per le piattaforme API 1.6"
    cd .. && python scripts/packaging/sync_builtin_plugins.py --source plugin-registry   # regenerates the core copy
    git add y_web/src/external_runtime/builtin_plugins.json && git commit -m "Built-in: copia aggiornata dal registro"

Usage: scripts/release/registry_min_version.py [--registry plugin-registry] [--version 4.1.0] [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

# the platform repositories written for platform API 1.6 (a core older than 4.1.0 refuses them)
PLATFORM_KEYS = (
    "microblogging_server",
    "forum_server",
    "photo_sharing",
    "instant_messaging",
    "dating",
    "forum_hpc",
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--registry", default="plugin-registry")
    ap.add_argument("--version", default="4.1.0")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    path = Path(args.registry) / "builtin.json"
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    changed = []
    for entry in data["plugins"]:
        if (
            entry["key"] in PLATFORM_KEYS
            and entry.get("min_ysocial_version") != args.version
        ):
            entry["min_ysocial_version"] = args.version
            changed.append(entry["key"])
    missing = [k for k in PLATFORM_KEYS if k not in {e["key"] for e in data["plugins"]}]
    if missing:
        print("not in the registry:", ", ".join(missing), file=sys.stderr)
        return 1
    if not changed:
        print("nothing to change")
        return 0
    print("min_ysocial_version", args.version, "->", ", ".join(changed))
    if not args.dry_run:
        indent = 2
        path.write_text(
            json.dumps(data, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
