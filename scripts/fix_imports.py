"""
Fix misplaced 'from sqlalchemy import select/func' lines that got inserted
inside multi-line import blocks. Moves them to the correct top-level position.
"""

import re
import sys
from pathlib import Path

SA_IMPORT_RE = re.compile(r"^from sqlalchemy import ([^\n]+)\n", re.MULTILINE)


def fix_file(path):
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)

    # Find all sqlalchemy import lines and their indices
    sa_lines = []
    inside_paren = 0
    good_sa_lines = set()
    bad_sa_indices = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track paren depth (for multi-line imports)
        before = inside_paren
        inside_paren += line.count("(") - line.count(")")

        if stripped.startswith("from sqlalchemy import"):
            if before > 0:
                # This line is inside a parenthesized block = BAD placement
                bad_sa_indices.append(i)
            else:
                good_sa_lines.add(i)

    if not bad_sa_indices:
        return False  # nothing to fix

    # Collect the names from bad lines
    extra_names = []
    for i in bad_sa_indices:
        m = re.match(r"from sqlalchemy import (.+)", lines[i].strip())
        if m:
            extra_names.extend([n.strip() for n in m.group(1).split(",")])

    # Remove bad lines
    new_lines = [l for i, l in enumerate(lines) if i not in bad_sa_indices]
    src = "".join(new_lines)

    # Merge extra_names into existing sqlalchemy import or add new line
    if re.search(r"^from sqlalchemy import", src, re.MULTILINE):

        def merge(m):
            existing = [n.strip() for n in m.group(1).split(",")]
            combined = sorted(set(existing + extra_names))
            return f'from sqlalchemy import {", ".join(combined)}'

        src = re.sub(
            r"^from sqlalchemy import ([^\n]+)", merge, src, count=1, flags=re.MULTILINE
        )
    else:
        names = sorted(set(extra_names))
        import_line = f'from sqlalchemy import {", ".join(names)}\n'
        lines2 = src.splitlines(keepends=True)
        insert = 0
        paren = 0
        for i, l in enumerate(lines2):
            paren += l.count("(") - l.count(")")
            if paren == 0 and (l.startswith("from ") or l.startswith("import ")):
                insert = i + 1
        lines2.insert(insert, import_line)
        src = "".join(lines2)

    path.write_text(src, encoding="utf-8")
    print(f"Fixed: {path} (moved {len(bad_sa_indices)} misplaced import line(s))")
    return True


def main():
    args = sys.argv[1:]
    targets = [Path(a) for a in args] if args else [Path("y_web")]
    paths = []
    for t in targets:
        paths.extend(t.rglob("*.py") if t.is_dir() else [t])
    paths = [p for p in paths if "__pycache__" not in str(p)]
    n = sum(1 for p in paths if fix_file(p))
    print(f"Fixed {n} files.")


if __name__ == "__main__":
    main()
