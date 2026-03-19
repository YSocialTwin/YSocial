from y_web.utils.y_client_process_runner import _get_client_archetypes


class DummyClient:
    pass


class ClientWithArchetypes:
    agent_archetypes = {
        "enabled": True,
        "distribution": {"validator": 1.0},
        "transitions": {},
    }


def test_get_client_archetypes_defaults_to_disabled():
    assert _get_client_archetypes(DummyClient()) == {
        "enabled": False,
        "distribution": {},
        "transitions": {},
    }


def test_get_client_archetypes_preserves_existing_config():
    assert (
        _get_client_archetypes(ClientWithArchetypes())
        == ClientWithArchetypes.agent_archetypes
    )
