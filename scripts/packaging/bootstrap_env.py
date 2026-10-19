"""Create the managed YSocial runtime (E3): uv-managed Python 3.12 + venv + wheel.

Usage:
    python scripts/packaging/bootstrap_env.py --home DIR --wheel ysocial.whl \
        [--uv PATH] [--wheelhouse DIR]

With --wheelhouse the install is fully offline (--no-index --find-links).
Layout: <home>/runtime/{python,venv}; the venv provides `bin/ysocial`.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PYTHON_VERSION = "3.12"


def run(cmd, env=None):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), check=True, env=env)


TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def bootstrap(
    home,
    wheel,
    uv="uv",
    wheelhouse=None,
    torch_cpu=True,
    toxicity=False,
    constraints=None,
):
    home = Path(home)
    runtime = home / "runtime"
    venv = runtime / "venv"
    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=str(runtime / "python"))
    if wheelhouse:
        env["UV_PYTHON_DOWNLOADS"] = "manual"
    t0 = time.time()
    run([uv, "python", "install", PYTHON_VERSION], env)
    # --seed: plugins are installed with `python -m pip` (see external_runtime)
    run([uv, "venv", "--seed", "--python", PYTHON_VERSION, venv], env)
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    cmd = [uv, "pip", "install", "--python", py]
    if constraints:
        # Same pins the project is tested with; kept for later plugin installs.
        shutil.copyfile(constraints, runtime / "constraints.txt")
        cmd += ["--constraint", runtime / "constraints.txt"]
    if wheelhouse:
        cmd += ["--no-index", "--find-links", wheelhouse]
    elif torch_cpu and toxicity:
        # detoxify -> torch: the default Linux/Windows wheels bundle CUDA (GBs)
        cmd += [
            "--extra-index-url",
            TORCH_CPU_INDEX,
            "--index-strategy",
            "unsafe-best-match",
        ]
    # optional extra: Detoxify (+ torch). Off by default, chosen in the installer.
    target = (
        f"ysocial[toxicity] @ {Path(wheel).resolve().as_uri()}" if toxicity else wheel
    )
    run(cmd + [target], env)
    print(f"bootstrap done in {time.time() - t0:.1f}s")
    return py


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--wheel", required=True)
    ap.add_argument("--uv", default=shutil.which("uv") or "uv")
    ap.add_argument("--wheelhouse")
    ap.add_argument("--no-torch-cpu", action="store_true")
    ap.add_argument("--constraints", help="pinned versions (requirements.lock)")
    ap.add_argument(
        "--with-toxicity",
        action="store_true",
        help="install the optional toxicity extra (detoxify + torch)",
    )
    a = ap.parse_args()
    bootstrap(
        a.home,
        a.wheel,
        a.uv,
        a.wheelhouse,
        not a.no_torch_cpu,
        a.with_toxicity,
        a.constraints,
    )
