import pytest
pytestmark = pytest.mark.unit

from y_web import db
from y_web.routes.admin.sub.agents import _ensure_interest_topics_exist
from y_web.routes.admin.sub.clients._crud import _export_adhoc_population_json
from y_web.src.agents.custom_features import (
    feature_entries_from_population_agent_payload,
    replace_agent_custom_features,
    summarize_agent_custom_features,
)
from y_web.src.models import (
    ActivityProfile,
    Agent,
    Agent_Population,
    OpinionGroup,
    Population,
    Topic_List,
)


def test_structured_agent_features_round_trip(app):
    with app.app_context():
        agent = Agent(name="Agent One", ag_type=None)
        db.session.add(agent)
        db.session.commit()

        replace_agent_custom_features(
            agent.id,
            [
                {"feature_type": "interest", "key": "Climate", "value": ""},
                {
                    "feature_type": "opinion",
                    "key": "Climate",
                    "value": '{"group_name": "Supportive", "opinion_value": 0.8, "stubborn": true}',
                },
                {"feature_type": "custom", "key": "Class", "value": "Mage"},
            ],
        )
        db.session.commit()

        summary = summarize_agent_custom_features(agent.id)

        assert summary["interests"] == ["Climate"]
        assert summary["opinions"] == {"Climate": 0.8}
        assert summary["opinion_groups"] == {"Climate": "Supportive"}
        assert summary["stubborn_topics"] == {"Climate": True}
        assert summary["custom_features"] == {"Class": "Mage"}


def test_export_adhoc_population_json_includes_structured_features(app):
    with app.app_context():
        profile = ActivityProfile(name="Always On", hours="0,1,2")
        population = Population(name="Pop One", descr="desc", pop_type="hello_world")
        agent = Agent(name="hello_agent", ag_type="hello_world", activity_profile=1)
        db.session.add(profile)
        db.session.add(population)
        db.session.add(agent)
        db.session.commit()
        db.session.add(Agent_Population(agent_id=agent.id, population_id=population.id))
        replace_agent_custom_features(
            agent.id,
            [
                {"feature_type": "interest", "key": "Climate", "value": ""},
                {
                    "feature_type": "opinion",
                    "key": "Climate",
                    "value": '{"group_name": "Supportive", "opinion_value": 0.8, "stubborn": true}',
                },
                {"feature_type": "custom", "key": "Class", "value": "Mage"},
            ],
        )
        db.session.commit()

        payload = _export_adhoc_population_json(
            population,
            {"agent_type": "hello_world"},
            owner="owner",
        )

        agent_payload = payload["agents"][0]
        assert agent_payload["interests"] == [["Climate"], 1]
        assert agent_payload["opinions"] == {"Climate": 0.8}
        assert agent_payload["stubborn_topics"] == {"Climate": True}
        assert agent_payload["custom_features"] == {"Class": "Mage"}


def test_feature_entries_from_population_agent_payload_supports_opinion_and_custom_fields(
    app,
):
    with app.app_context():
        db.session.add(
            OpinionGroup(name="Supportive", lower_bound=0.7, upper_bound=0.9)
        )
        db.session.commit()

        entries = feature_entries_from_population_agent_payload(
            {
                "interests": [["Climate"], 1],
                "opinions": {"Climate": 0.8},
                "stubborn_topics": {"Climate": True},
                "custom_features": {"Class": "Mage"},
            }
        )

        by_type = {
            (entry["feature_type"], entry["key"]): entry["value"] for entry in entries
        }
        assert ("interest", "Climate") in by_type
        assert ("custom", "Class") in by_type
        assert '"group_name": "Supportive"' in by_type[("opinion", "Climate")]
        assert '"stubborn": true' in by_type[("opinion", "Climate")]


def test_ensure_interest_topics_exist_creates_missing_topics_case_insensitively(app):
    with app.app_context():
        db.session.add(Topic_List(name="Climate"))
        db.session.commit()

        _ensure_interest_topics_exist(
            [
                {"feature_type": "interest", "key": "Climate", "value": ""},
                {"feature_type": "interest", "key": "  New Topic  ", "value": ""},
                {"feature_type": "interest", "key": "new topic", "value": ""},
            ]
        )
        db.session.commit()

        topics = [
            topic.name
            for topic in Topic_List.query.order_by(Topic_List.name.asc()).all()
        ]
        assert topics == ["Climate", "New Topic"]
