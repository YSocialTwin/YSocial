"""
Regression tests for the redesigned "Post & Comment Annotation" admin
config box (Admin -> Frontend Settings -> EducatYon).

Background: the box is generic, shared infrastructure -- the manifest at
external/EducatYon/meta/registry.json declares each module's
`parameter_sections` / `parameters`, and `renderEducatyonModules()` in
frontend_settings.html renders whatever it's given. Before this change the
result was a flat wall of ~20 stacked rows with no visual grouping, no
description text, and no relationship between fields that only make sense
together (e.g. "Opinion scale" was shown even with topic annotation off,
and an entire "Toxicity" section -- which has no parameter of its own --
silently vanished instead of explaining where toxicity is actually
configured).

The redesign adds a `depends_on` convention to the manifest schema (a
section or a single parameter can gate its visibility on another
parameter's live value) and teaches the generic renderer to: group
sections into a bordered card with a header + description, collapse an
all-boolean section into a compact chip row instead of stacked rows, keep
a parameter-less section visible as an info line when it has a
description, and hide/reveal sections and rows live as the admin edits.

These are static-analysis tests (matching this repo's
`test_microblog_follow_links.py` / `__file__`-relative-path convention)
plus one live-discovery check confirming `depends_on` actually survives
the real manifest-loading pipeline unmodified. The rendering LOGIC itself
(chip-row layout, live show/hide, string_list textarea parsing) was
verified separately via a jsdom harness run directly against this
session's copy of frontend_settings.html (no permanent JS test infra
exists in this repo, matching the EducatYon post_annotation frontend's
own established verification approach).
"""
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

REGISTRY_JSON = (
    _REPO_ROOT / "external" / "EducatYon" / "meta" / "registry.json"
)
FRONTEND_SETTINGS_HTML = (
    _REPO_ROOT / "y_web" / "templates" / "admin" / "frontend_settings.html"
)


def _post_annotation_manifest():
    payload = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    return next(
        m for m in payload["frontend_plugins"] if m["module_id"] == "post_annotation"
    )


def test_dimension_gated_sections_declare_depends_on():
    manifest = _post_annotation_manifest()
    sections_by_key = {s["key"]: s for s in manifest["parameter_sections"]}

    expected = {
        "topics": "enable_topic_annotation",
        "opinion": "enable_topic_annotation",
        "sentiment": "enable_sentiment_annotation",
        "emotions": "enable_emotion_annotation",
        "toxicity": "enable_toxicity_annotation",
    }
    for key, gate in expected.items():
        assert key in sections_by_key, f"section {key!r} missing from manifest"
        assert sections_by_key[key].get("depends_on") == gate, (
            f"section {key!r} should depend on {gate!r}"
        )

    # Scope/dimensions/limits/display are the always-relevant, top-level
    # sections -- they must NOT be gated behind anything.
    for key in ("scope", "dimensions", "limits", "display"):
        assert "depends_on" not in sections_by_key[key], (
            f"section {key!r} should always be visible"
        )


def test_toxicity_section_has_no_parameters_but_keeps_its_description():
    """
    Toxicity is configured via the platform-wide toxicity_levels
    vocabulary, not a parameter here -- this section exists purely to
    explain that, so it must have a description and (unlike every other
    section) zero bound parameters.
    """
    manifest = _post_annotation_manifest()
    toxicity = next(
        s for s in manifest["parameter_sections"] if s["key"] == "toxicity"
    )
    assert toxicity.get("description")
    bound = [p for p in manifest["parameters"] if p.get("section") == "toxicity"]
    assert bound == []


def test_dependent_parameters_declare_depends_on():
    manifest = _post_annotation_manifest()
    params_by_name = {p["name"]: p for p in manifest["parameters"]}

    assert params_by_name["opinion_scale"]["depends_on"] == "enable_opinion_annotation"
    assert params_by_name["max_topics_per_annotation"]["depends_on"] == "allow_multi_topic"
    assert params_by_name["max_emotions_per_annotation"]["depends_on"] == "allow_multi_emotion"
    assert params_by_name["custom_topics"]["depends_on"] == {
        "param": "topic_source",
        "equals": "custom",
    }


def test_registry_json_is_well_formed_after_edits():
    # A hand-edited JSON manifest is an easy place to introduce a trailing
    # comma or an unclosed brace -- catch that here rather than at
    # request time in the admin panel.
    json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))


def test_discover_frontend_modules_passes_depends_on_through_unmodified():
    """
    educatyon_settings_get() (the admin panel's data source) forwards
    parameter_sections/parameters straight from discover_frontend_modules()
    with no filtering -- so proving depends_on survives THAT call is
    sufficient to know the admin endpoint will see it too.
    """
    import sys

    sys.path.insert(0, str(_REPO_ROOT))
    from y_web.src.external_runtime import frontend_plugins

    modules = frontend_plugins.discover_frontend_modules("educatyon")
    manifest = next(m for m in modules if m["module_id"] == "post_annotation")

    sections_by_key = {s["key"]: s for s in manifest["parameter_sections"]}
    assert sections_by_key["sentiment"]["depends_on"] == "enable_sentiment_annotation"

    params_by_name = {p["name"]: p for p in manifest["parameters"]}
    assert params_by_name["opinion_scale"]["depends_on"] == "enable_opinion_annotation"


def test_admin_panel_renders_sections_as_bordered_groups_with_chip_rows():
    template = FRONTEND_SETTINGS_HTML.read_text(encoding="utf-8")

    # CSS for the new structured layout.
    assert ".edu-param-section {" in template
    assert ".edu-param-section-header {" in template
    assert ".edu-param-section-desc {" in template
    assert ".edu-bool-chip-row {" in template
    assert ".edu-bool-chip {" in template

    # JS: dependency gating helpers + live re-sync wiring.
    assert "function _eduDependsMet(" in template
    assert "function _eduSyncDependants(" in template
    assert "_eduSyncDependants(card)" in template
    assert "configurePanel.addEventListener('change'" in template

    # An all-boolean section renders as a chip row instead of stacked rows.
    assert "edu-bool-chip-row" in template
    assert "params.every(function (p) { return p.type === 'bool'; })" in template

    # A parameter-less-but-described section is kept (info-only), not
    # silently dropped -- this was the old behavior's actual bug.
    assert "s.description;" in template or "|| s.description" in template


def test_string_list_control_is_a_textarea_split_on_comma_or_newline():
    template = FRONTEND_SETTINGS_HTML.read_text(encoding="utf-8")
    assert "<textarea id=\"' + id + '\"" in template
    # The 28-entry default emotion list was previously a single-line
    # <input>, which made it painful to read or edit.
    assert "'<input type=\"text\" id=\"' + id + '\" value=\"' + joined" not in template
    assert "split(/[,\\n]+/)" in template
