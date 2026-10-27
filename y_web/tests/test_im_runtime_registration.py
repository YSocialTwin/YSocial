"""YInstantMessaging is registered like the other simulation runtimes (plan, Phase 3)."""

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def test_instant_messaging_spec_is_a_private_official_runtime():
    from y_web.src.external_runtime import registry

    spec = registry.runtime_spec("instant_messaging")
    assert spec.github_repo == "YSocialTwin/YInstantMessaging"
    assert spec.path.name == "YInstantMessaging"
    assert spec.category == "simulation_runtimes"
    assert spec.group == "instant_messaging"
    assert spec.is_private is True
    assert spec.validate_import == "yinstantmessaging"
    assert tuple(spec.validate_entrypoints) == ("run_server.py", "run_client.py", "requirements.txt")


def test_instant_messaging_group_is_listed_after_photo_sharing():
    from y_web.src.external_runtime import registry

    keys = [g[0] for g in registry.grouped_runtime_specs()]
    assert keys.index("instant_messaging") == keys.index("photo_sharing") + 1


def test_active_instant_messaging_experiments_block_runtime_mutation(monkeypatch):
    from y_web.routes.admin.sub.experiments import _external_runtimes as er

    seen = {}

    class _Query:
        def filter(self, *conds):
            seen.setdefault("filters", []).append(conds)
            return self

        def all(self):
            return []

    fake = MagicMock()
    fake.query = _Query()
    monkeypatch.setattr(er, "Exps", fake)
    assert er._runtime_group_active_experiments("instant_messaging") == []
    assert len(seen["filters"]) == 3  # not remote, platform, running or active
