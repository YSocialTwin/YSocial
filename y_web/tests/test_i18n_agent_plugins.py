"""Ad hoc agent pages: manifest text comes from the agent plugin's catalog (phase 5 follow-up)."""

import pytest
from flask import Flask

import y_web.i18n as i18n
from y_web.routes.admin.sub.agents import _plugin_agent_specs
from y_web.routes.admin.sub.clients._crud import _adhoc_agent_specs


@pytest.fixture
def agents_app():
    flask_app = Flask("y_web")
    flask_app.config.update(
        TESTING=True, SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it")
    )
    i18n.init_i18n(flask_app)
    return flask_app


def _by_type(specs):
    return {s["agent_type"]: s for s in specs}


@pytest.mark.parametrize("loader", [_plugin_agent_specs, _adhoc_agent_specs])
def test_agent_specs_follow_the_interface_language(agents_app, loader):
    with agents_app.test_request_context("/", headers={"Accept-Language": "en"}):
        english = _by_type(loader())
    with agents_app.test_request_context("/", headers={"Accept-Language": "it"}):
        italian = _by_type(loader())
    if "stress_attacker" not in english:
        pytest.skip("agent plugin not installed")
    en, it = english["stress_attacker"], italian["stress_attacker"]
    # identity never depends on the language
    assert en["slug"] == it["slug"] and en["accepted_slugs"] == it["accepted_slugs"]
    assert it["display_name_en"] == "Stress Attacker"
    assert it["description"] != en["description"] and it["description"].startswith(
        "Iniettore"
    )


def test_adhoc_parameter_labels_and_prompt_keys(agents_app):
    with agents_app.test_request_context("/", headers={"Accept-Language": "it"}):
        spec = _by_type(_adhoc_agent_specs()).get("propaganda")
    if spec is None:
        pytest.skip("agent plugin not installed")
    labels = {p.get("label") for p in spec["client_parameters"]}
    assert (
        "Budget giornaliero" in labels
        or "Numero massimo di bersagli simultanei" in labels
    )
    # prompt text is an LLM prompt: it is never translated; the page matches on the English title
    for template in spec["prompt_templates"]:
        assert template["title_key"] in {
            "Opening Propaganda System Prompt",
            "Reply Propaganda System Prompt",
        }
        assert template["body"].startswith("You ")


@pytest.mark.parametrize(
    "msgid, expected",
    [
        ("Open Agent Builder", "Apri il Builder di agenti"),
        ("Available Agents", "Agenti disponibili"),
        ("Forum Only", "Solo forum"),
        ("Not assigned", "Non assegnato"),
        ("%(n)s populations", "%(n)s popolazioni"),
    ],
)
def test_agents_dashboard_strings_are_translated(agents_app, msgid, expected):
    with agents_app.test_request_context("/", headers={"Accept-Language": "it"}):
        assert i18n.gettext(msgid) == expected


def test_recommender_descriptions_follow_the_interface_language(agents_app):
    from y_web.routes.social.helpers import _RECSYS_DESCRIPTIONS

    english = _RECSYS_DESCRIPTIONS["ReverseChronoPopularity"]
    with agents_app.test_request_context("/", headers={"Accept-Language": "it"}):
        italian = i18n.gettext(english)
    assert italian != english and italian.startswith("Post di altri utenti")


def test_plugin_sidebar_texts_are_translated(agents_app):
    """Sidebar group, items and section headings come from the plugin's own catalog."""
    from y_web.src.external_runtime.plugin_i18n import domain_for_repo, localize_text

    if not domain_for_repo("training_modules"):
        pytest.skip("training plugin not installed")
    with agents_app.test_request_context("/", headers={"Accept-Language": "it"}):
        assert localize_text("training_modules", "Training") == "Formazione"
        assert localize_text("training_modules", "Modules") == "Moduli"
        assert localize_text("training_modules", "Design") == "Progettazione"
        assert localize_text("training_modules", "Results") == "Risultati"


def test_admin_sidebar_label_is_short_in_italian(agents_app):
    with agents_app.test_request_context("/", headers={"Accept-Language": "it"}):
        assert i18n.gettext("Admin") == "Admin"
