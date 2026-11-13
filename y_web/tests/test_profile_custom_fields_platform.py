"""Custom fields of other platforms stay off the profile pages of a platform."""

from y_web.src.agents.custom_features import platform_agnostic_custom_features


def test_namespaced_fields_of_other_platforms_are_hidden():
    features = {
        "hobby": "chess",
        "appearance.hair": "red",
        "dating.latent.selectivity": 0.4,
        "dating.preferences.age": "25-35",
    }
    assert platform_agnostic_custom_features(features) == {
        "hobby": "chess",
        "appearance.hair": "red",
    }
    assert platform_agnostic_custom_features(None) == {}
