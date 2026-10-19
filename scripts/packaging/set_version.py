#!/usr/bin/env python3
"""Stamp one release version into every file that carries it.

Used by the release workflow so that a tag ``v4.1.0`` produces a wheel, installers and a
Docker image all named/versioned 4.1.0, whatever the files in the tagged commit say.

    python scripts/packaging/set_version.py v4.1.0
    python scripts/packaging/set_version.py 4.1.0 --root /path/to/repo

Files: ``VERSION`` (the wheel version), ``installer/src-tauri/tauri.conf.json``,
``installer/src-tauri/Cargo.toml`` and the ``ysocial-installer`` entry of ``Cargo.lock``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 4.1.0, 4.1.0-rc1, 4.1.0-beta.2 (optional leading "v" is stripped)
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")


def normalize(raw: str) -> str:
    version = raw.strip()
    if version[:1] in {"v", "V"}:
        version = version[1:]
    if not VERSION_RE.match(version):
        raise ValueError(
            f"{raw!r} is not a release version (expected X.Y.Z or X.Y.Z-suffix, e.g. v4.1.0)"
        )
    return version


def _replace_once(path: Path, pattern: str, repl: str, flags: int = 0) -> None:
    text = path.read_text(encoding="utf-8")
    new, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"version field not found in {path}")
    path.write_text(new, encoding="utf-8")


def set_version(root: Path, version: str) -> list[str]:
    changed = []
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    changed.append("VERSION")

    tauri = root / "installer/src-tauri/tauri.conf.json"
    _replace_once(tauri, r'("version"\s*:\s*")[^"]*(")', rf"\g<1>{version}\g<2>")
    changed.append(str(tauri.relative_to(root)))

    cargo = root / "installer/src-tauri/Cargo.toml"
    _replace_once(
        cargo, r'^(version\s*=\s*")[^"]*(")', rf"\g<1>{version}\g<2>", re.MULTILINE
    )
    changed.append(str(cargo.relative_to(root)))

    lock = root / "installer/src-tauri/Cargo.lock"
    if lock.exists():
        _replace_once(
            lock,
            r'(name = "ysocial-installer"\nversion = ")[^"]*(")',
            rf"\g<1>{version}\g<2>",
        )
        changed.append(str(lock.relative_to(root)))
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="release version or tag, e.g. v4.1.0")
    parser.add_argument("--root", default=Path(__file__).resolve().parents[2], type=Path)
    args = parser.parse_args(argv)
    try:
        version = normalize(args.version)
        files = set_version(args.root, version)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(version)
    for name in files:
        print(f"  stamped {name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
