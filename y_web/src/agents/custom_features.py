"""Helpers for structured agent custom features stored in the dashboard DB."""

from __future__ import annotations

import json
from typing import Iterable

from y_web import db
from y_web.src.models import Agent_Custom_Feature, OpinionGroup


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def encode_opinion_feature(
    *,
    group_name: str,
    opinion_value: float | None,
    stubborn: bool = False,
) -> str:
    return json.dumps(
        {
            "group_name": str(group_name).strip(),
            "opinion_value": None if opinion_value is None else float(opinion_value),
            "stubborn": bool(stubborn),
        }
    )


def decode_opinion_feature(raw_value) -> dict:
    if raw_value in (None, ""):
        return {"group_name": "", "opinion_value": None, "stubborn": False}
    try:
        payload = json.loads(raw_value)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "group_name": str(payload.get("group_name") or "").strip(),
        "opinion_value": (
            None
            if payload.get("opinion_value") in (None, "")
            else float(payload.get("opinion_value"))
        ),
        "stubborn": _truthy(payload.get("stubborn")),
    }


def replace_agent_custom_features(agent_id: int, feature_entries: list[dict]) -> None:
    Agent_Custom_Feature.query.filter_by(agent_id=int(agent_id)).delete()
    for entry in feature_entries:
        feature_type = str(entry.get("feature_type") or "").strip().lower()
        key = str(entry.get("key") or "").strip()
        if feature_type not in {"custom", "interest", "opinion"} or not key:
            continue
        db.session.add(
            Agent_Custom_Feature(
                agent_id=int(agent_id),
                feature_type=feature_type,
                key=key,
                value=(
                    None
                    if entry.get("value") in (None, "")
                    else str(entry.get("value"))
                ),
            )
        )


def delete_agent_custom_features(agent_id: int) -> None:
    Agent_Custom_Feature.query.filter_by(agent_id=int(agent_id)).delete()


def summarize_agent_custom_features(agent_id: int) -> dict:
    rows = (
        Agent_Custom_Feature.query.filter_by(agent_id=int(agent_id))
        .order_by(Agent_Custom_Feature.id.asc())
        .all()
    )
    interests: list[str] = []
    opinions: dict[str, float] = {}
    opinion_groups: dict[str, str] = {}
    stubborn_topics: dict[str, bool] = {}
    custom_features: dict[str, str] = {}

    for row in rows:
        if row.feature_type == "interest":
            if row.key not in interests:
                interests.append(row.key)
            continue
        if row.feature_type == "opinion":
            decoded = decode_opinion_feature(row.value)
            if decoded["group_name"]:
                opinion_groups[row.key] = decoded["group_name"]
            if decoded["opinion_value"] is not None:
                opinions[row.key] = float(decoded["opinion_value"])
            if decoded["stubborn"]:
                stubborn_topics[row.key] = True
            if row.key not in interests:
                interests.append(row.key)
            continue
        if row.feature_type == "custom":
            custom_features[row.key] = "" if row.value is None else str(row.value)

    return {
        "interests": interests,
        "opinions": opinions,
        "opinion_groups": opinion_groups,
        "stubborn_topics": stubborn_topics,
        "custom_features": custom_features,
        "rows": rows,
    }


def summarize_agent_custom_features_bulk(agent_ids: Iterable[int]) -> dict[int, dict]:
    normalized_ids = [int(agent_id) for agent_id in agent_ids if agent_id is not None]
    if not normalized_ids:
        return {}
    rows = (
        Agent_Custom_Feature.query.filter(
            Agent_Custom_Feature.agent_id.in_(normalized_ids)
        )
        .order_by(Agent_Custom_Feature.agent_id.asc(), Agent_Custom_Feature.id.asc())
        .all()
    )
    grouped: dict[int, list[Agent_Custom_Feature]] = {}
    for row in rows:
        grouped.setdefault(int(row.agent_id), []).append(row)
    result = {}
    for agent_id in normalized_ids:
        if agent_id not in grouped:
            result[int(agent_id)] = {
                "interests": [],
                "opinions": {},
                "opinion_groups": {},
                "stubborn_topics": {},
                "custom_features": {},
                "rows": [],
            }
            continue
        interests: list[str] = []
        opinions: dict[str, float] = {}
        opinion_groups: dict[str, str] = {}
        stubborn_topics: dict[str, bool] = {}
        custom_features: dict[str, str] = {}
        for row in grouped[agent_id]:
            if row.feature_type == "interest":
                if row.key not in interests:
                    interests.append(row.key)
            elif row.feature_type == "opinion":
                decoded = decode_opinion_feature(row.value)
                if decoded["group_name"]:
                    opinion_groups[row.key] = decoded["group_name"]
                if decoded["opinion_value"] is not None:
                    opinions[row.key] = float(decoded["opinion_value"])
                if decoded["stubborn"]:
                    stubborn_topics[row.key] = True
                if row.key not in interests:
                    interests.append(row.key)
            elif row.feature_type == "custom":
                custom_features[row.key] = "" if row.value is None else str(row.value)
        result[int(agent_id)] = {
            "interests": interests,
            "opinions": opinions,
            "opinion_groups": opinion_groups,
            "stubborn_topics": stubborn_topics,
            "custom_features": custom_features,
            "rows": grouped[agent_id],
        }
    return result


def opinion_group_by_name() -> dict[str, OpinionGroup]:
    return {
        str(group.name).strip(): group
        for group in OpinionGroup.query.order_by(OpinionGroup.lower_bound.asc()).all()
    }


def opinion_group_for_value(opinion_value) -> OpinionGroup | None:
    if opinion_value in (None, ""):
        return None
    try:
        numeric = float(opinion_value)
    except (TypeError, ValueError):
        return None
    groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound.asc()).all()
    for index, group in enumerate(groups):
        lower = float(group.lower_bound)
        upper = float(group.upper_bound)
        if index == len(groups) - 1:
            if lower <= numeric <= upper:
                return group
        elif lower <= numeric < upper:
            return group
    return None


def feature_entries_from_population_agent_payload(agent_payload: dict) -> list[dict]:
    interest_names = []
    raw_interests = agent_payload.get("interests")
    if isinstance(raw_interests, list):
        if raw_interests and isinstance(raw_interests[0], list):
            interest_names = [
                str(item).strip() for item in raw_interests[0] if str(item).strip()
            ]
        else:
            interest_names = [
                str(item).strip() for item in raw_interests if str(item).strip()
            ]

    entries: list[dict] = [
        {"feature_type": "interest", "key": interest_name, "value": ""}
        for interest_name in interest_names
    ]

    stubborn_topics = agent_payload.get("stubborn_topics") or {}
    opinions = agent_payload.get("opinions") or {}
    if isinstance(opinions, dict):
        for topic_name, opinion_payload in opinions.items():
            key = str(topic_name).strip()
            if not key:
                continue
            opinion_value = None
            group_name = ""
            stubborn = _truthy(stubborn_topics.get(key))
            if isinstance(opinion_payload, dict):
                opinion_value = opinion_payload.get(
                    "value", opinion_payload.get("opinion")
                )
                group_name = str(
                    opinion_payload.get("group")
                    or opinion_payload.get("group_name")
                    or ""
                ).strip()
                stubborn = stubborn or _truthy(opinion_payload.get("stubborn"))
            else:
                opinion_value = opinion_payload
            if not group_name:
                matched_group = opinion_group_for_value(opinion_value)
                group_name = str(matched_group.name).strip() if matched_group else ""
            entries.append(
                {
                    "feature_type": "opinion",
                    "key": key,
                    "value": encode_opinion_feature(
                        group_name=group_name,
                        opinion_value=(
                            None
                            if opinion_value in (None, "")
                            else float(opinion_value)
                        ),
                        stubborn=stubborn,
                    ),
                }
            )

    custom_features = agent_payload.get("custom_features") or {}
    if isinstance(custom_features, dict):
        for key, value in custom_features.items():
            key_str = str(key).strip()
            if not key_str:
                continue
            entries.append(
                {
                    "feature_type": "custom",
                    "key": key_str,
                    "value": "" if value is None else str(value),
                }
            )

    return entries
