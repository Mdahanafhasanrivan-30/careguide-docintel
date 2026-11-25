"""Reciprocal rank fusion: merge ranked lists without comparing their scores. Pure."""
from collections.abc import Hashable, Sequence

RRF_K = 60   # the usual constant; it stops the very first places from dominating


def rrf_merge(*rankings: Sequence[Hashable], k: int = RRF_K) -> list[tuple[Hashable, float]]:
    """Each list is ids, best first. An id gets 1 / (k + rank) from every list it is in.
    Keyword scores (ts_rank) and vector similarity use different scales, so we use only the order."""
    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)