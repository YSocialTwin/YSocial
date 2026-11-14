"""The two repositories that serve the forum share a platform key and nothing else."""

import re
from pathlib import Path

import pytest

EXTERNAL = Path(__file__).resolve().parents[2] / "external"
PAIR = ("YServerReddit", "YForum")


def _sources(repo):
    return sorted((EXTERNAL / repo / "ysocial_platform").rglob("*.py"))


@pytest.mark.parametrize("repo,other", [PAIR, PAIR[::-1]])
def test_a_forum_repository_does_not_name_the_other(repo, other):
    if not (EXTERNAL / repo / "ysocial_platform").is_dir():
        pytest.skip(f"{repo} is not installed")
    pattern = re.compile(rf"\b{other}\b")
    named = [
        f"{path.relative_to(EXTERNAL)}:{number}"
        for path in _sources(repo)
        for number, line in enumerate(path.read_text("utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert not named, named


def test_the_two_forum_providers_are_variants_not_dependencies():
    from y_web.platforms import registry

    variants = registry.variants("forum")
    if len(variants) < 2:
        pytest.skip("both forum repositories are needed")
    assert {v.provider_id for v in variants} == {"forum", "ysocial_server_reddit"}
    # each has its own library: neither is imported through the other
    libraries = {v.provider_id: v.library_package for v in variants}
    assert len(set(libraries.values())) == 2
