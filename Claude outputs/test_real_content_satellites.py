"""Structural (pure, no db_exp) checks on real_content.py's hardcoded
satellite-table mapping (Fase 8). The actual delete/update operations
need a live db_exp session and YSimulator's own models, so they are
exercised end-to-end in
y_web/tests/test_scenario_design_fase8_real_content.py (skips cleanly in
this sandbox, same as every other real-DB integration test this phase);
this file only guards against the one mistake that *is* catchable
without a database: the two hardcoded lists drifting apart, in length or
in per-row shape, from each other or from RealContentError's own
contract.
"""
from modules.scenario_editor.backend.real_content import (
    RealContentError,
    _HPC_SATELLITES,
    _STANDARD_SATELLITES,
)


def test_standard_and_hpc_satellite_lists_have_the_same_length():
    assert len(_STANDARD_SATELLITES) == len(_HPC_SATELLITES)


def test_every_satellite_entry_is_a_two_tuple_of_strings():
    for entries in (_STANDARD_SATELLITES, _HPC_SATELLITES):
        for entry in entries:
            assert len(entry) == 2
            model_name, fk_column = entry
            assert isinstance(model_name, str) and model_name
            assert isinstance(fk_column, str) and fk_column


def test_standard_and_hpc_satellite_lists_have_no_duplicate_model_names():
    for entries in (_STANDARD_SATELLITES, _HPC_SATELLITES):
        names = [model_name for model_name, _fk in entries]
        assert len(names) == len(set(names))


def test_reported_uses_to_post_everywhere_not_post_id():
    # Reported references a post via `to_post` (a reported *post*), not
    # `post_id` -- the one satellite whose FK column name differs from
    # the rest, in both families alike. A typo here would silently no-op
    # every cascade-delete's Reported cleanup.
    for entries in (_STANDARD_SATELLITES, _HPC_SATELLITES):
        by_name = dict(entries)
        assert by_name["Reported"] == "to_post"


def test_agent_opinion_uses_id_post_everywhere_not_post_id():
    for entries in (_STANDARD_SATELLITES, _HPC_SATELLITES):
        by_name = dict(entries)
        assert by_name["Agent_Opinion"] == "id_post"


def test_real_content_error_defaults_to_not_found_style_status():
    exc = RealContentError("post_not_found", "nope")
    assert exc.code == "post_not_found"
    assert exc.message == "nope"
    assert exc.http_status == 404


def test_real_content_error_accepts_explicit_http_status():
    exc = RealContentError("post_has_descendants", "has replies", http_status=409)
    assert exc.http_status == 409
