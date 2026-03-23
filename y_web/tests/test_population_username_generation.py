from y_web.src.agents.population import _generate_unique_name
import pytest
pytestmark = pytest.mark.unit



class FakeForum:
    def user_name(self):
        return "Jane.OConnor-Smith"

    def first_name_male(self):
        return "John"

    def first_name_female(self):
        return "Jane"

    def first_name(self):
        return "Alex"

    def last_name(self):
        return "O'Connor-Smith"

    def name_male(self):
        return "John O'Connor-Smith"

    def name_female(self):
        return "Jane O'Connor-Smith"


def test_forum_username_generation_uses_reddit_style_handles():
    fake = FakeForum()
    name = _generate_unique_name(fake, "female", set(), username_type="forum")
    assert name == "jane_oconnor_smith"


def test_microblogging_username_generation_keeps_legacy_path():
    fake = FakeForum()
    name = _generate_unique_name(fake, "female", set(), username_type="microblogging")
    assert name == "JaneO'Connor-Smith"
