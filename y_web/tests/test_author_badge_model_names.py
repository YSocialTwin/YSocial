from types import SimpleNamespace as U

from y_web.routes.social.helpers import get_author_type_badge
from y_web.src.data_access.posts import _author_type_badge


def test_badge_agents_with_model_name_types():
    for fn in (get_author_type_badge, _author_type_badge):
        for t in ("qwen3:4b-instruct", "llama3.2:latest", "agent", "", "comic_relief"):
            assert str(fn(U(user_type=t))) == "AI Agent", t
        for t in ("user", None):
            assert str(fn(U(user_type=t))) == "Human", t
