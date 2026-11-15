"""The recommender systems of the people of the frontend are implemented by the platforms, not by the core.

Every platform that has people on its frontend carries its own copy of the recommenders (``ysocial_platform/recsys``)
and hands it over as ``provider.human_recsys``; the core only asks for it.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = ROOT / "external"
#: platform -> (repository, whether it ranks the feed itself)
PLATFORMS = {
    "YServer": True,
    "YSimulator": True,
    "YServerReddit": True,
    "YForum": True,
    "YPhotoSharing": False,
}
MODE_NAMES = re.compile(
    r"ReverseChrono|HybridLinearRanker|CollaborativeUserUser|ContentBasedFeatures|"
    r"SimilarUsersReactions|CommonInterests|FilterBubble"
)
#: the catalogue rows of the modes shipped with YSocial are data of the migrations, not code
DATA_OF_THE_CATALOGUE = ("y_web/migrations/", "y_web/alembic/", "y_web/db_init/")
#: declared residual: the default values of the settings page of the personalised feed (the page itself is shared)
DECLARED_RESIDUAL = ("y_web/src/experiment/frontend_defaults.py",)


def test_the_core_carries_no_recommender_implementation():
    assert not (ROOT / "y_web" / "src" / "recsys").exists()
    offenders = []
    for path in (ROOT / "y_web").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if (
            relative.startswith("y_web/tests/")
            or relative.startswith(DATA_OF_THE_CATALOGUE)
            or relative in DECLARED_RESIDUAL
        ):
            continue
        if MODE_NAMES.search(path.read_text(encoding="utf-8")):
            offenders.append(relative)
    assert offenders == []


@pytest.mark.parametrize("repo", sorted(PLATFORMS))
def test_each_platform_carries_its_own_recommenders(repo):
    package = EXTERNAL / repo / "ysocial_platform" / "recsys"
    if not (EXTERNAL / repo / "ysocial_platform" / "provider.py").is_file():
        pytest.skip(f"{repo} is not installed")
    assert (package / "__init__.py").is_file()
    assert (package / "follow_recsys.py").is_file()
    assert (package / "modes.py").is_file()
    assert (package / "content_recsys.py").is_file() is PLATFORMS[repo]
    for path in (EXTERNAL / repo / "ysocial_platform").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "y_web.src.recsys" not in text, path


@pytest.mark.parametrize("repo", sorted(PLATFORMS))
def test_the_provider_hands_them_to_the_core(repo):
    from y_web.platforms import registry
    from y_web.sdk import HumanRecsysTraits

    providers = [p for p in registry.all_providers() if p.server_label == repo]
    if not providers:
        pytest.skip(f"{repo} is not installed")
    recsys = providers[0].human_recsys
    assert isinstance(recsys, HumanRecsysTraits)
    assert recsys.normalize("rc") == "ReverseChrono"
    assert recsys.is_supported("ReverseChrono") and not recsys.is_supported("nope")
    assert recsys.describe("ReverseChrono")
    assert recsys.suggested_users is not None
    assert (recsys.suggested_posts is not None) is PLATFORMS[repo]
