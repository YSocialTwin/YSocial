"""The statistics toggle of the Annotations box follows the annotation add-on as soon as it is switched, with no reload."""
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "admin" / "frontend_settings.html"


def test_saving_the_annotation_module_updates_the_statistics_toggle_at_once():
    html = TEMPLATE.read_text(encoding="utf-8")
    save = html[html.index("edu-save-btn').addEventListener('click'"):]
    ok_branch = save[save.index("if (data.ok)"):save.index("} else {")]
    assert "moduleId === 'post_annotation'" in ok_branch and "syncAnnotationStatsAvailability(enabled)" in ok_branch
