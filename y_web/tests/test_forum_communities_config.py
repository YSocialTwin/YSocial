"""The ``communities`` section of the forum client configurations: opt-in, off by default, validated by YForum."""

import pytest

from y_web.src.forum import communities
from y_web.src.forum.client_config import ForumClientFormError, build_client_config, parse_client_form
from y_web.tests.test_forum_client_config import _build, schemas  # noqa: F401


def test_nothing_is_written_when_both_actions_are_off():
    assert communities.config_section(communities.parse_form({})) is None
    values = parse_client_form({})
    assert "communities" not in _build(values)


def test_the_form_values_become_the_section():
    values = communities.parse_form(
        {
            "communities_creation": "on",
            "communities_creation_probability": "0.2",
            "communities_max_topics": "30",
            "communities_crosspost": "on",
            "communities_max_per_post": "2",
        }
    )
    assert communities.config_section(values) == {
        "creation": {"enabled": True, "probability": 0.2, "max_topics": 30},
        "crosspost": {"enabled": True, "probability": 0.15, "max_per_post": 2},
    }


@pytest.mark.parametrize(
    "form",
    [
        {"communities_creation_probability": "2"},
        {"communities_max_topics": "-1"},
        {"communities_max_per_post": "0"},
        {"communities_crosspost_probability": "x"},
    ],
)
def test_out_of_range_values_are_refused(form):
    with pytest.raises(communities.CommunitiesFormError):
        communities.parse_form(form)
    with pytest.raises(ForumClientFormError):
        parse_client_form(form)


def test_the_hpc_client_config_carries_the_section_and_yforum_accepts_it(schemas):  # noqa: F811
    values = parse_client_form({"communities_creation": "on", "communities_crosspost": "on"})
    config = _build(values)
    assert config["communities"]["creation"]["enabled"] is True
    out = schemas(config, "config/client_config")  # YForum's strict schema accepts the section
    assert out["communities"]["crosspost"]["enabled"] is True
