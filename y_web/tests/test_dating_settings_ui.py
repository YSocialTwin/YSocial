"""Layout of the dating settings pages: every setting has one place and one label."""

import os

import pytest

from y_web.src.dating import client_config as dcc
from y_web.src.dating import server_settings as srv
from y_web.src.dating import settings_ui as ui
from y_web.src.system.path_utils import get_external_repo_dir

REPO = get_external_repo_dir("YDating")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not REPO or not os.path.isdir(REPO), reason="YDating not installed"
    ),
]


@pytest.mark.parametrize(
    "fields,sections",
    [
        (lambda: srv.form_fields(REPO), ui.SERVER_SECTIONS),
        (lambda: dcc.form_fields(REPO), ui.CLIENT_SECTIONS),
    ],
)
def test_every_setting_is_placed_and_labelled(fields, sections):
    fs = fields()
    layout = ui.layout(
        fs, sections, {"memory": True, "stress_reward": True, "toxicity": True}
    )
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


def test_a_component_that_is_off_is_not_shown():
    fields = dcc.form_fields(REPO)
    off = ui.layout(fields, ui.CLIENT_SECTIONS, {"memory": False})
    shown = {i["f"].path for sec in off for b in sec["blocks"] for i in b["fields"]}
    assert "memory" not in [x["id"] for x in off]
    assert not [
        p for p in shown if p.startswith(("memory.", "stress_reward.", "annotations."))
    ]
    assert "other" not in [x["id"] for x in off]
    on = ui.layout(fields, ui.CLIENT_SECTIONS, {"memory": True})
    assert "memory" in [x["id"] for x in on]


def test_settings_that_need_a_model_are_hidden_without_llm_agents():
    fields = dcc.form_fields(REPO)
    layout = ui.layout(fields, ui.CLIENT_SECTIONS, llm_enabled=False)
    shown = {i["f"].path for sec in layout for b in sec["blocks"] for i in b["fields"]}
    assert "llm" not in [x["id"] for x in layout]
    for path in ("llm.model", "swipe.mode", "conversation.text_source", "swipe.llm_vision",
                 "profile_generation.enabled"):  # fmt: skip
        assert path not in shown
    assert (
        "profile_generation.images.enabled" in shown
    )  # drawing the photos is its own choice
    assert "swipe.w_attr" in shown
    with_llm = ui.layout(fields, ui.CLIENT_SECTIONS, llm_enabled=True)
    assert [x["id"] for x in with_llm][:3] == [
        "llm",
        "images",
        "recommender",
    ]  # the image model follows


def test_the_defaults_follow_the_llm_switch():
    on = dcc.mode_defaults(True, True)
    assert on["swipe"]["mode"] == "llm" and on["conversation"]["text_source"] == "llm"
    assert (
        on["profile_generation"]["enabled"]
        and on["profile_generation"]["images"]["enabled"]
    )
    assert (
        dcc.mode_defaults(True, False)["profile_generation"]["images"]["enabled"]
        is False
    )
    off = dcc.mode_defaults(False)
    assert off["swipe"]["mode"] == "rule" and off["llm"]["backend"] == "stub"
    assert off["conversation"]["text_source"] == "template"
    assert not off["profile_generation"]["enabled"]


def test_sections_render():
    import jinja2

    from y_web.tests.test_dating_settings import ROOT

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "y_web" / "templates"))
    )
    env.globals["_"] = lambda s, **kw: s
    layout = ui.layout(
        dcc.form_fields(REPO),
        ui.CLIENT_SECTIONS,
        {"memory": False},
        {"match_recsys": ["", "random", "hybrid"]},
    )
    values = dcc.values_for_form(REPO, None, True, False)
    values["recsys_default"] = "hybrid"
    tpl = env.from_string(
        "{% from 'admin/_dating_fields.html' import dating_sections %}"
        "{{ dating_sections(sections, values, 7) }}"
    )
    html = tpl.render(sections=layout, values=values)
    assert 'id="sec-llm"' in html and 'id="sec-images"' in html
    assert 'id="sec-memory"' not in html  # memory is off: not shown at all
    assert "adv__profile_generation__images__background" in html
    # the language model block of the other platforms: address with Fetch, model list, vision model with Fetch
    assert "data-fetch-models" in html and "data-fetch-vision" in html
    assert "dating_llm_model" in html and 'name="adv__llm__backend"' in html
    # the look of the photos and the recommender
    assert "Photorealistic human faces" in html and "Fantasy cartoon characters" in html
    assert "data-recsys" in html and "Same as the experiment" in html


def _env():
    import jinja2

    from y_web.tests.test_dating_settings import ROOT

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "y_web" / "templates"))
    )
    env.globals["_"] = lambda s, **kw: s
    return env


def _widgets(fields):
    return {f.path: ui.widget_of(f) for f in fields}


def test_the_client_page_has_no_server_setting():
    """The client page shows settings of the client schema only; the names it shares with the server schema are
    the three that mean something of their own in each (logs of the process, seed, namespace).
    """
    client = {f.path for f in dcc.form_fields(REPO)}
    server = {f.path for f in srv.form_fields(REPO)}
    layout = ui.layout(dcc.form_fields(REPO), ui.CLIENT_SECTIONS)
    shown = {i["f"].path for s in layout for b in s["blocks"] for i in b["fields"]}
    assert shown <= client
    assert shown & server <= {"logging.enable_console_log", "namespace", "seed"}
    # nothing of the rules of the platform is offered on the client page
    for prefix in ("conversations.", "human.", "matching.", "archetypes."):
        assert not [p for p in shown if p.startswith(prefix)]


def test_settings_use_the_widgets_of_the_other_pages():
    client = _widgets(dcc.form_fields(REPO))
    server = _widgets(srv.form_fields(REPO))
    for key in ui.IMPORTANCE:
        assert client[key] == "importance"
    assert client["activity.hourly_activity"] == "hourly"
    assert client["swipe.mode"] == "segmented"
    assert client["conversation.enabled"] == "toggle"
    assert client["conversation.check_probability"] == "slider"
    assert client["llm.temperature"] == "number"
    assert server["conversations.opener_genders"] == "taglist"
    assert "bool" not in {
        f.kind for f in dcc.form_fields(REPO) if client[f.path] != "toggle"
    }


def test_advanced_settings_are_marked_and_the_rest_is_not():
    layout = ui.layout(dcc.form_fields(REPO), ui.CLIENT_SECTIONS)
    items = {i["f"].path: i for s in layout for b in s["blocks"] for i in b["fields"]}
    assert items["llm.timeout_seconds"]["advanced"]
    assert items["swipe.noise_std"]["advanced"]
    assert not items["swipe.w_attr"]["advanced"]
    assert not items["llm.model"]["advanced"]
    runtime = next(s for s in layout if s["id"] == "runtime")
    assert runtime["advanced_only"]
    assert not next(s for s in layout if s["id"] == "swipe")["advanced_only"]


def test_a_box_posts_only_its_own_settings():
    layout = ui.layout(dcc.form_fields(REPO), ui.CLIENT_SECTIONS)
    values = dcc.values_for_form(REPO)
    tpl = _env().from_string(
        "{% from 'admin/_dating_fields.html' import dating_box %}"
        "{{ dating_box(s, values, 7, '/admin/update_dating_client/3', False) }}"
    )
    swipe = next(s for s in layout if s["id"] == "swipe")
    html = tpl.render(s=swipe, values=values)
    assert 'id="box-swipe"' in html and 'action="/admin/update_dating_client/3"' in html
    assert html.count("<form") == 1
    assert "dating-importance" in html and "adv__swipe__w_attr" in html
    assert "adv__llm__model" not in html
    activity = next(s for s in layout if s["id"] == "activity")
    html = tpl.render(s=activity, values=values)
    assert "data-hourly" in html and "adv__activity__hourly_activity" in html
    assert "adv__activity__session_probability" in html and "data-dating-slider" in html


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


def test_people_are_always_welcome():
    from y_web.src.dating.experiment_config import generate_dating_server_config

    cfg = generate_dating_server_config("e", "db", "/tmp", seed=1)
    assert cfg["human"]["enabled"] is True
    off = {"human": {"enabled": False, "max_humans": 3}}
    assert srv.ensure_humans(off) and off["human"] == {"enabled": True, "max_humans": 3}
    assert not srv.ensure_humans(off)
    assert "human.enabled" not in [f.path for f in srv.form_fields(REPO)]


def test_a_restarted_client_runs_what_is_left(app, tmp_path):
    import json

    from y_web import db
    from y_web.src.hpc.client import _set_dating_run_length
    from y_web.src.models import Client, Client_Execution

    path = tmp_path / "client_c-p.json"
    path.write_text(
        json.dumps({"client_name": "c", "num_days": 3, "num_slots_per_day": 24})
    )
    with app.app_context():
        cli = Client(name="c", id_exp=1, population_id=1, days=3, status=0)
        db.session.add(cli)
        db.session.commit()
        ex = Client_Execution(client_id=cli.id, last_active_day=-1, last_active_hour=-1)
        db.session.add(ex)
        db.session.commit()

        _set_dating_run_length(str(path), cli)
        assert (
            json.loads(path.read_text())["num_days"] == 3
        )  # first start: the whole length

        ex.last_active_day, ex.last_active_hour = 2, 24  # day 2 finished
        db.session.commit()
        _set_dating_run_length(str(path), cli)
        assert json.loads(path.read_text())["num_days"] == 1

        cli.days = 5  # extended by two days
        db.session.commit()
        _set_dating_run_length(str(path), cli)
        assert json.loads(path.read_text())["num_days"] == 3

        ex.last_active_day, ex.last_active_hour = 5, 24  # everything done
        db.session.commit()
        with pytest.raises(RuntimeError):
            _set_dating_run_length(str(path), cli)


def test_advanced_parameters_sit_in_a_closed_panel():
    import jinja2

    from y_web.tests.test_dating_settings import ROOT

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "y_web" / "templates"))
    )
    env.globals["_"] = lambda s, **kw: s
    layout = ui.layout(
        dcc.form_fields(REPO),
        ui.CLIENT_SECTIONS,
        {"memory": True},
        {"match_recsys": ["", "random"]},
        llm_enabled=True,
    )
    values = dcc.values_for_form(REPO, None, True, False)
    values["recsys_default"] = "random"
    tpl = env.from_string(
        "{% from 'admin/_dating_fields.html' import dating_sections %}"
        "{{ dating_sections(sections, values, 7) }}"
    )
    html = tpl.render(sections=layout, values=values)
    assert '<details class="dating-advanced-panel">' in html
    assert "<details open" not in html
    assert "dating-show-advanced" not in html and "data-advanced" not in html


def test_the_experiment_settings_page_is_one_form_with_tabs():
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "templates"
        / "admin"
        / "dating_settings.html"
    ).read_text(encoding="utf-8")
    assert source.count("<form ") == 1  # one Save for the whole page
    for tab in ("recommender", "rules", "chats"):
        assert f'data-panel="{tab}"' in source
    assert 'id="dating-recsys-side"' in source and "data-recsys-info" in source


def test_the_image_model_is_a_choice_of_small_models_or_any_id():
    import jinja2

    from y_web.tests.test_dating_settings import ROOT

    f = next(x for x in dcc.form_fields(REPO) if x.path == ui.DIFFUSION_MODEL)
    item = ui.item_for(f)
    assert item["widget"] == "diffusion_model" and not item["advanced"]
    ids = [m for m, _ in item["diffusion_models"]]
    assert ids[0] == "segmind/tiny-sd" and "stabilityai/sd-turbo" in ids
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "y_web" / "templates"))
    )
    env.globals["_"] = lambda s, **kw: s
    tpl = env.from_string(
        "{% from 'admin/_dating_fields.html' import dating_control %}"
        "{{ dating_control(item, values) }}"
    )
    known = tpl.render(item=item, values={f.path: "segmind/tiny-sd"})
    assert "data-diffusion-select" in known and "hidden" in known
    other = tpl.render(item=item, values={f.path: "someone/other"})
    assert 'value="someone/other"' in other and "hidden" not in other


def test_the_distance_filter_is_an_off_switch_of_the_experiment():
    f = next(
        x
        for x in srv.common_fields(str(REPO))
        if x.path == "matching.common.distance_filter"
    )
    assert f.default is False
    item = ui.item_for(f)
    assert item["widget"] == "toggle" and not item["advanced"]
    assert ui.label_of(f.path) == "Only show profiles within the distance"
