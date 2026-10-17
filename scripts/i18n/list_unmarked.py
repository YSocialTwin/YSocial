"""List the unmarked user-visible strings of the given templates.

python scripts/i18n/list_unmarked.py y_web/templates/admin/foo.html ...
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit_strings import JINJA, TextCollector, read  # noqa: E402
from scan_unmarked import load_exceptions  # noqa: E402

ex = load_exceptions()
for p in sys.argv[1:]:
    t = TextCollector()
    t.feed(JINJA.sub("", read(Path(p))))
    rest = [x for x in t.texts + t.attrs if x not in ex]
    print("== %s (%d)" % (p, len(rest)))
    for x in rest:
        print("   ", repr(x)[:200])
