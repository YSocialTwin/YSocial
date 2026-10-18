"""Build ysocial-avatars.tar.gz from the tracked avatar images.

Upload the result as the release asset referenced by DEFAULT_AVATARS_URL
(release tag ``avatars-v1``).
Usage: python scripts/packaging/make_avatars_archive.py [OUT.tar.gz]
"""
import sys
import tarfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "y_web/static/assets/img/users"
EXT = (".png", ".jpg", ".jpeg", ".webp")


def main(out="ysocial-avatars.tar.gz"):
    files = sorted(p for p in SRC.iterdir() if p.suffix.lower() in EXT)
    with tarfile.open(out, "w:gz") as tar:
        for p in files:
            tar.add(p, arcname=p.name)
    print(f"{len(files)} images -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
