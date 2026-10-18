"""The trending card prefixes '#' itself: a stored hashtag that already carries it must not show '##'."""
import jinja2
import pathlib
import pytest

pytestmark = pytest.mark.unit

TPL = pathlib.Path(__file__).resolve().parents[1] / "templates" / "microblogging" / "components" / "sidebar_ranked_list_card.html"


def _render(items, prefix="#"):
    env = jinja2.Environment(autoescape=True)
    return env.from_string(TPL.read_text(encoding="utf-8")).render(
        exp_id=1, ranked_card_items=items, ranked_card_href_prefix="hashtag_posts",
        ranked_card_label_key="hashtag", ranked_card_meta_label="mentions", ranked_card_prefix=prefix,
        ranked_card_title="t", ranked_card_subtitle="s", ranked_card_empty="e",
    )


def test_stored_with_and_without_hash_show_a_single_hash():
    html = _render([
        {"id": 1, "hashtag": "#repubblica", "count": 1},
        {"id": 2, "hashtag": "DelPiero", "count": 1},
    ])
    assert ">#repubblica<" in html and ">#DelPiero<" in html
    assert "##" not in html


def test_without_prefix_the_label_is_untouched():
    html = _render([{"id": 1, "hashtag": "#x", "count": 1}], prefix="")
    assert ">#x<" in html
