from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple, TypeVar

TPost = TypeVar("TPost")


def stable_uniform_0_1(*parts: object, salt: str = "forum-hot-longtail-v1") -> float:
    """
    Deterministic pseudo-random uniform in [0, 1) derived from input parts.

    Intended to be stable per viewer+round+post (so refresh doesn't reshuffle),
    while changing as the simulation progresses.
    """
    key = salt + "|" + "|".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    x = int.from_bytes(digest[:8], "big", signed=False)
    return x / float(2**64)


def base_hot_score(
    net_score: int, post_round: int, *, round_decay: float = 12.0
) -> float:
    """
    Match the current forum Hot base used in `reddit/service.py`:
      log10(abs(net)+1) + sign(net) * (post_round / round_decay)
    """
    if net_score > 0:
        sign = 1.0
    elif net_score < 0:
        sign = -1.0
    else:
        sign = 0.0
    return math.log10(abs(net_score) + 1.0) + sign * (
        float(post_round) / float(round_decay)
    )


def longtail_boost(
    likes: int,
    dislikes: int,
    *,
    u01: float,
    vote_thresh1: int = 3,
    vote_thresh2: int = 8,
    j1: float = 0.45,
    j2: float = 0.20,
) -> float:
    """
    Small exploration boost for low-vote posts, scaled by a seeded uniform.

    - votes <= vote_thresh1 => boost in [0, j1)
    - votes <= vote_thresh2 => boost in [0, j2)
    - otherwise => 0
    """
    total_votes = int(likes) + int(dislikes)
    if total_votes <= vote_thresh1:
        return float(u01) * float(j1)
    if total_votes <= vote_thresh2:
        return float(u01) * float(j2)
    return 0.0


@dataclass(frozen=True)
class RankedPost:
    score: float
    post: object


def rank_posts_longtail(
    posts: Iterable[TPost],
    reaction_map: Dict[int, Tuple[int, int]],
    *,
    viewer_id: int,
    current_round_id: int,
    round_decay: float = 12.0,
    vote_thresh1: int = 3,
    vote_thresh2: int = 8,
    j1: float = 0.45,
    j2: float = 0.20,
) -> List[TPost]:
    """
    Rank candidate posts by (base_hot + longtail_boost), tie-breaking by post.id.

    Expects each post to have `.id` (int) and `.round` (int).
    """
    ranked: List[Tuple[float, int, TPost]] = []
    for p in posts:
        post_id = int(getattr(p, "id"))
        post_round = int(getattr(p, "round"))
        likes, dislikes = reaction_map.get(post_id, (0, 0))
        net = int(likes) - int(dislikes)
        base = base_hot_score(net, post_round, round_decay=round_decay)
        u = stable_uniform_0_1(viewer_id, current_round_id, post_id)
        boost = longtail_boost(
            likes,
            dislikes,
            u01=u,
            vote_thresh1=vote_thresh1,
            vote_thresh2=vote_thresh2,
            j1=j1,
            j2=j2,
        )
        ranked.append((base + boost, post_id, p))

    ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [p for _, _, p in ranked]
