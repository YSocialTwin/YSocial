"""pyflakes-style guard: the forum interaction routes must not reference undefined names."""
import pytest

pyflakes = pytest.importorskip("pyflakes.api")
from pyflakes.reporter import Reporter  # noqa: E402
import io  # noqa: E402
import pathlib  # noqa: E402

pytestmark = pytest.mark.unit

FILES = ["y_web/routes/interactions/forum.py"]


@pytest.mark.parametrize("rel", FILES)
def test_no_undefined_names(rel):
    path = pathlib.Path(__file__).resolve().parents[2] / rel
    out = io.StringIO()
    pyflakes.check(path.read_text(encoding="utf-8"), rel, Reporter(out, out))
    bad = [l for l in out.getvalue().splitlines() if "undefined name" in l]
    assert not bad, "\n".join(bad)
