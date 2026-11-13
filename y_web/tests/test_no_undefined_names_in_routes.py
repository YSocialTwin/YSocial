"""pyflakes-style guard: the forum interaction routes must not reference undefined names."""

import pytest

pyflakes = pytest.importorskip("pyflakes.api")
import io  # noqa: E402
import pathlib  # noqa: E402

from pyflakes.reporter import Reporter  # noqa: E402

from y_web.tests._platform_repos import requires_platform  # noqa: E402

pytestmark = pytest.mark.unit

FILES = ["external/YForum/ysocial_platform/routes/interactions_forum.py"]


@pytest.mark.parametrize(
    "rel", [pytest.param(f, marks=requires_platform("YForum")) for f in FILES]
)
def test_no_undefined_names(rel):
    path = pathlib.Path(__file__).resolve().parents[2] / rel
    out = io.StringIO()
    pyflakes.check(path.read_text(encoding="utf-8"), rel, Reporter(out, out))
    bad = [l for l in out.getvalue().splitlines() if "undefined name" in l]
    assert not bad, "\n".join(bad)
