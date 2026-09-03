"""
SQLAlchemy 2.x query migration script.
Converts legacy Model.query.* patterns to the SA2 select() API.
Only handles simple single-line patterns that are safe to automate.
"""
import re, sys
from pathlib import Path

MODEL = r'([A-Za-z_][A-Za-z0-9_.]*)'
ARGS  = r'([^()]*(?:\([^()]*\)[^()]*)*)'

PATTERNS = [
    (re.compile(rf'{MODEL}\.query\.filter_by\({ARGS}\)\.all\(\)'),
     lambda m: f'db.session.scalars(select({m.group(1)}).filter_by({m.group(2)})).all()'),
    (re.compile(rf'{MODEL}\.query\.filter_by\({ARGS}\)\.first\(\)'),
     lambda m: f'db.session.scalars(select({m.group(1)}).filter_by({m.group(2)})).first()'),
    (re.compile(rf'{MODEL}\.query\.filter_by\({ARGS}\)\.one_or_none\(\)'),
     lambda m: f'db.session.scalars(select({m.group(1)}).filter_by({m.group(2)})).one_or_none()'),
    (re.compile(rf'{MODEL}\.query\.filter_by\({ARGS}\)\.one\(\)'),
     lambda m: f'db.session.scalars(select({m.group(1)}).filter_by({m.group(2)})).one()'),
    (re.compile(rf'{MODEL}\.query\.filter_by\({ARGS}\)\.count\(\)'),
     lambda m: f'db.session.scalar(select(func.count()).select_from({m.group(1)}).filter_by({m.group(2)}))'),
    (re.compile(rf'{MODEL}\.query\.all\(\)'),
     lambda m: f'db.session.scalars(select({m.group(1)})).all()'),
    (re.compile(rf'{MODEL}\.query\.first\(\)'),
     lambda m: f'db.session.scalars(select({m.group(1)})).first()'),
    (re.compile(rf'{MODEL}\.query\.count\(\)'),
     lambda m: f'db.session.scalar(select(func.count()).select_from({m.group(1)}))'),
]

def ensure_select_import(src):
    if re.search(r'from sqlalchemy import[^\n]*\bselect\b', src):
        return src
    needs_func = 'func.count()' in src
    if 'from sqlalchemy import' in src:
        def add_names(m):
            names = [x.strip() for x in m.group(1).split(',')]
            if 'select' not in names: names.append('select')
            if needs_func and 'func' not in names: names.append('func')
            return 'from sqlalchemy import ' + ', '.join(sorted(set(names)))
        return re.sub(r'from sqlalchemy import ([^\n]+)', add_names, src, count=1)
    else:
        extra = 'from sqlalchemy import func, select\n' if needs_func else 'from sqlalchemy import select\n'
        lines = src.splitlines(keepends=True)
        insert = 0
        for i, l in enumerate(lines):
            if l.startswith('from ') or l.startswith('import '): insert = i + 1
        lines.insert(insert, extra)
        return ''.join(lines)

def migrate_file(path, dry_run=False):
    src = path.read_text(encoding='utf-8')
    n_total = 0
    for pattern, repl in PATTERNS:
        new, n = pattern.subn(repl, src)
        n_total += n
        src = new
    if n_total == 0:
        return 0
    src = ensure_select_import(src)
    if dry_run:
        print(f'[dry] {path}: {n_total}')
    else:
        path.write_text(src, encoding='utf-8')
        print(f'{path}: {n_total}')
    return n_total

def main():
    args = sys.argv[1:]
    dry_run = '--dry-run' in args
    args = [a for a in args if a != '--dry-run']
    targets = [Path(a) for a in args] if args else [Path('y_web')]
    paths = []
    for t in targets:
        paths.extend(t.rglob('*.py') if t.is_dir() else [t])
    paths = [p for p in paths if '__pycache__' not in str(p)]
    total, nfiles = 0, 0
    for p in sorted(paths):
        n = migrate_file(p, dry_run)
        if n: total += n; nfiles += 1
    print(f'\nTotal: {total} replacements in {nfiles} files.')

if __name__ == '__main__': main()
