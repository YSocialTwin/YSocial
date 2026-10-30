"""Layout of the dating settings pages: every setting has one place and one label."""

import pytest

from y_web.src.dating import client_config as dcc
from y_web.src.dating import server_settings as srv
from y_web.src.dating import settings_ui as ui
from y_web.src.system.path_utils import get_external_repo_dir

REPO = get_external_repo_dir("YDating")
pytestmark = pytest.mark.skipif(
    not REPO or not __import__("os").path.isdir(REPO), reason="YDating not installed"
)


@pytest.mark.parametrize(
    "fields,sections",
    [
        (lambda: srv.form_fields(REPO), ui.SERVER_SECTIONS),
        (lambda: dcc.form_fields(REPO), ui.CLIENT_SECTIONS),
    ],
)
def test_every_setting_is_placed_and_labelled(fields, sections):
    fs = fields()
    layout = ui.layout(fs, sections)
    assert "other" not in [s["id"] for s in layout]
    placed = [i["f"].path for s in layout for b in s["blocks"] for i in b["fields"]]
    assert sorted(placed) == sorted(f.path for f in fs)
    assert not [p for p in placed if p not in ui.LABELS]


def test_a_setting_is_on_one_page_only():
    a = {f.path for f in srv.form_fields(REPO)}
    b = {f.path for f in dcc.form_fields(REPO)}
    shared = a & b
    # the same key may exist in both schemas (logging.*, stress_reward.*, lifecycle.*) with a different meaning
    for path in shared:
        assert path in ui.LABELS


def test_switch_off_marks_section_inactive():
    layout = ui.layout(dcc.form_fields(REPO), ui.CLIENT_SECTIONS, {"memory": False})
    assert next(s for s in layout if s["id"] == "memory")["inactive"]
    layout = ui.layout(dcc.form_fields(REPO), ui.CLIENT_SECTIONS, {"memory": True})
    assert not next(s for s in layout if s["id"] == "memory")["inactive"]


def test_sections_render():
    import jinja2

    from y_web.tests.test_dating_settings import ROOT

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "y_web" / "templates"))
    )
    env.globals["_"] = lambda s, **kw: s
    layout = ui.layout(dcc.form_fields(REPO), ui.CLIENT_SECTIONS, {"memory": False})
    values = dcc.values_for_form(REPO)
    tpl = env.from_string(
        "{% from 'admin/_dating_fields.html' import dating_sections %}"
        "{{ dating_sections(sections, values, 7) }}"
    )
    html = tpl.render(sections=layout, values=values)
    assert 'id="sec-llm"' in html and 'id="sec-memory"' in html
    assert "/admin/experiment_details/7" in html  # memory section is off
    assert "adv__profile_generation__images__background" in html


def test_remaining_days_for_a_restart():
    f = dcc.remaining_days
    assert f(3, -1, -1, 24) == 3  # never ran
    assert f(3, 1, 10, 24) == 3  # stopped inside day 1: day 1 runs again
    assert f(3, 2, 24, 24) == 1  # day 2 finished: day 3 is left
    assert f(3, 3, 24, 24) == 0  # everything done
    assert f(-1, 5, 3, 24) == -1  # until stopped
    assert f(5, 3, 24, 24) == 2  # extended from 3 to 5 after day 3


def test_apply_form_keeps_what_the_form_does_not_carry():
    cfg = dcc.build_client_config(
        REPO,
        name="c",
        population_file="p.json",
        days=2,
        server_config={},
        memory_enabled=True,
        language="en",
        form={},
    )
    merged = dcc.apply_form(REPO, cfg, {"adv__swipe__w_attr": "0.9"})
    assert merged["swipe"]["w_attr"] == 0.9
    assert merged["client_name"] == "c" and merged["num_days"] == 2
    assert merged["memory"]["enabled"] is True
