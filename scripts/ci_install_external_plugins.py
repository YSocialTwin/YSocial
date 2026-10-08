"""Clone the external plugin suites listed in external/plugins.json.

``external/`` is gitignored: each developer clones the suites they need
manually (see ``external/README.md``), so a fresh CI checkout never has
them. Several test suites intentionally exercise the real repos rather
than a mock (see test_backend_plugins_registry.py's docstring), so CI
needs them cloned before pytest runs.
"""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_DIR = REPO_ROOT / "external"


def main() -> None:
    plugins = json.loads((EXTERNAL_DIR / "plugins.json").read_text())["plugins"]
    for plugin in plugins:
        url = plugin["repository_url"]
        name = url.rstrip("/").rsplit("/", 1)[-1]
        dest = EXTERNAL_DIR / name
        if dest.exists():
            print(f"skip {name}: already present")
            continue
        print(f"cloning {name} from {url}")
        subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True)


if __name__ == "__main__":
    main()
